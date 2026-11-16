"""Evaluation harness for Phases 5-7.

  python evaluate.py              run all scenarios, compute classification metrics + paired t-test
  python evaluate.py --ragas      also compute RAGAS-style metrics (LLM judge) for the ontology condition
  python evaluate.py --limit 5    quick smoke run

Condition "ontology" = primary model + ontology retrieval. Conditions "llm_only:<model>" = no retrieval.
Positive class = non_compliant (thesis Phase 5). Every predicted verdict other than non_compliant counts
as "not flagged". Per-scenario correctness (predicted == expected) feeds the paired t-test.
"""
import argparse
import csv
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from scipy import stats

import llm
from chat import ComplianceChatbot
from config import (CLASSIFICATION_THRESHOLD, COMPARISON_MODELS, EMBEDDING_MODEL, PRIMARY_MODEL,
                    RAGAS_THRESHOLDS, RESULTS_DIR, SCENARIOS_CSV)


def load_scenarios(limit=None):
    with open(SCENARIOS_CSV, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return rows[:limit] if limit else rows


def run_condition(bot, scenarios, model, use_ontology, workers=4):
    def one(s):
        a = bot.ask(s["question"], model=model, use_ontology=use_ontology)
        cited = " ".join(a.citations)
        item_ok = (not s["expected_items"]) or any(
            re.search(rf"\bItem\s+{re.escape(i)}\b", cited, re.I) for i in s["expected_items"].split("|"))
        return {"id": s["id"], "expected": s["expected_verdict"], "predicted": a.verdict,
                "correct": int(a.verdict == s["expected_verdict"]), "citation_ok": int(item_ok),
                "seconds": a.seconds, "answer": a.answer, "citations": "; ".join(a.citations),
                "context": a.context, "question": s["question"]}
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, scenarios))


def classification_metrics(results):
    tp = sum(r["expected"] == "non_compliant" and r["predicted"] == "non_compliant" for r in results)
    fp = sum(r["expected"] != "non_compliant" and r["predicted"] == "non_compliant" for r in results)
    fn = sum(r["expected"] == "non_compliant" and r["predicted"] != "non_compliant" for r in results)
    tn = len(results) - tp - fp - fn
    acc = (tp + tn) / len(results)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    secs = [r["seconds"] for r in results]
    mean = sum(secs) / len(secs)
    sd = math.sqrt(sum((s - mean) ** 2 for s in secs) / (len(secs) - 1)) if len(secs) > 1 else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn, "accuracy": acc, "precision": prec, "recall": rec,
            "f1": f1, "time_mean_s": mean, "time_sd_s": sd,
            "citation_accuracy": sum(r["citation_ok"] for r in results) / len(results)}


def paired_t(primary, other):
    x = [r["correct"] for r in primary]
    y = [r["correct"] for r in other]
    if x == y:
        return {"t": float("nan"), "p": float("nan"), "df": len(x) - 1, "note": "identical scores"}
    t, p = stats.ttest_rel(x, y)
    return {"t": float(t), "p": float(p), "df": len(x) - 1, "note": ""}


# ---- RAGAS-style metrics (Es et al., 2024) with an LLM judge -------------------------------------

def _json(text):
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def _judge(prompt):
    text, _ = llm.chat(PRIMARY_MODEL, [{"role": "user", "content": prompt}], max_tokens=1200)
    return _json(text)


def faithfulness(question, answer, context):
    # The user's own submitted values are premises, so the question is shown to the judge with the context.
    data = _judge(
        "Split the ANSWER into atomic statements. For each, say whether it can be inferred from the CONTEXT "
        "or from the facts stated in the QUESTION. "
        'Return JSON: {"statements": [{"text": "...", "supported": true}]}.\n\n'
        f"QUESTION:\n{question}\n\nCONTEXT:\n{context}\n\nANSWER:\n{answer}")
    stmts = (data or {}).get("statements") or []
    return sum(bool(s.get("supported")) for s in stmts) / len(stmts) if stmts else float("nan")


def context_relevance(question, context):
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", context) if s.strip()]
    if not sents:
        return float("nan")
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sents))
    data = _judge(
        "Which numbered sentences of the CONTEXT are necessary to answer the QUESTION? "
        'Return JSON: {"necessary": [indices]}.\n\n'
        f"QUESTION: {question}\n\nCONTEXT:\n{numbered}")
    idx = {i for i in (data or {}).get("necessary", []) if isinstance(i, int) and 0 <= i < len(sents)}
    return len(idx) / len(sents)


def answer_relevance(question, answer, n=3):
    data = _judge(
        f"Write {n} different questions that the ANSWER below would be a direct answer to. "
        f'Return JSON: {{"questions": ["..."]}}.\n\nANSWER:\n{answer}')
    qs = ((data or {}).get("questions") or [])[:n]
    if not qs:
        return float("nan")
    vecs = llm.embed(EMBEDDING_MODEL, [question] + qs)
    q0 = vecs[0]

    def cos(a, b):
        return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))
    return sum(cos(q0, v) for v in vecs[1:]) / len(qs)


def ragas(results):
    def one(r):
        out = {"id": r["id"]}
        if not r["context"]:
            return {**out, "faithfulness": float("nan"), "context_relevance": float("nan"),
                    "answer_relevance": float("nan")}
        out["faithfulness"] = faithfulness(r["question"], r["answer"], r["context"])
        out["context_relevance"] = context_relevance(r["question"], r["context"])
        try:
            out["answer_relevance"] = answer_relevance(r["question"], r["answer"])
        except Exception as e:  # embeddings endpoint may be unavailable for the chosen model
            print(f"answer_relevance failed for {r['id']}: {e}")
            out["answer_relevance"] = float("nan")
        return out
    with ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(one, results))
    summary = {}
    for k in RAGAS_THRESHOLDS:
        vals = [r[k] for r in rows if not math.isnan(r[k])]
        summary[k] = sum(vals) / len(vals) if vals else float("nan")
    return rows, summary


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ragas", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    scenarios = load_scenarios(args.limit)
    bot = ComplianceChatbot()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(exist_ok=True)

    conditions = {f"ontology:{PRIMARY_MODEL}": (PRIMARY_MODEL, True)}
    for m in COMPARISON_MODELS:
        conditions[f"llm_only:{m}"] = (m, False)

    all_results = {}
    for name, (model, use_onto) in conditions.items():
        print(f"Running {name} on {len(scenarios)} scenarios...")
        # Pellet is single-instance, so run ontology scenarios one at a time to keep response times honest.
        all_results[name] = run_condition(bot, scenarios, model, use_onto, workers=1 if use_onto else 4)
        write_csv(RESULTS_DIR / f"{stamp}_{re.sub(r'[^A-Za-z0-9]+', '_', name)}.csv", all_results[name])

    primary_name = next(iter(conditions))
    report = ["# Evaluation report", f"Scenarios: {len(scenarios)}  (data file: {SCENARIOS_CSV.name})", "",
              "| Condition | Acc | Prec | Rec | F1 | Cite-Item | Time mean (s) | Time SD (s) | TP/FP/FN/TN |",
              "|---|---|---|---|---|---|---|---|---|"]
    for name, res in all_results.items():
        m = classification_metrics(res)
        report.append(f"| {name} | {m['accuracy']:.2f} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | "
                      f"{m['citation_accuracy']:.2f} | {m['time_mean_s']:.2f} | {m['time_sd_s']:.2f} | "
                      f"{m['TP']}/{m['FP']}/{m['FN']}/{m['TN']} |")
    report += ["", f"Benchmark for Acc/Prec/Rec/F1: >= {CLASSIFICATION_THRESHOLD:.2f}", "",
               "## Paired t-test on per-scenario correctness (primary vs comparison, alpha = 0.05)"]
    for name, res in all_results.items():
        if name == primary_name:
            continue
        t = paired_t(all_results[primary_name], res)
        report.append(f"- {primary_name} vs {name}: t = {t['t']:.3f}, p = {t['p']:.4f}, df = {t['df']} {t['note']}")

    if args.ragas:
        print("Computing RAGAS-style metrics...")
        rows, summary = ragas(all_results[primary_name])
        write_csv(RESULTS_DIR / f"{stamp}_ragas.csv", rows)
        report += ["", "## RAGAS-style metrics (ontology condition, LLM judge)",
                   "| Metric | Mean | Threshold | Pass |", "|---|---|---|---|"]
        for k, thr in RAGAS_THRESHOLDS.items():
            ok = "yes" if summary[k] >= thr else "no"
            report.append(f"| {k} | {summary[k]:.3f} | >= {thr} | {ok} |")

    wrong = [r for r in all_results[primary_name] if not r["correct"]]
    if wrong:
        report += ["", "## Misclassified in the ontology condition"]
        report += [f"- {r['id']}: expected {r['expected']}, got {r['predicted']} - {r['answer'][:150]}" for r in wrong]

    text = "\n".join(report)
    (RESULTS_DIR / f"{stamp}_report.md").write_text(text, encoding="utf-8")
    print("\n" + text)


if __name__ == "__main__":
    main()
