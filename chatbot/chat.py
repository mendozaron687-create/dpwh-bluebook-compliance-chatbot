"""Chat pipeline.

Ontology mode: question -> entity extraction -> SPARQL retrieval -> deterministic rule check (verify.py)
-> Gemini polishes the grammar of the drafted answer (it cannot change verdict, numbers, or citations).
LLM-only mode (comparison baseline): the model answers from its own knowledge.
"""
import json
import re
import sys
import time
from dataclasses import dataclass, field

import llm
from config import PRIMARY_MODEL
from retrieval import OntologyRetriever
from verify import decide

VERDICTS = {"compliant", "non_compliant", "insufficient_information", "informational"}

POLISH_SYSTEM = (
    "You are a copy editor. Rewrite the DRAFT into clear, natural, grammatically correct English of one to "
    "three sentences. Do not change the verdict, any number, unit, Item number, volume, or sub-item, and do "
    "not add or remove facts. Reply with the rewritten text only."
)

BASELINE_SYSTEM = (
    "You are an assistant that answers questions about compliance with the DPWH Standard Specifications "
    "(Blue Book) of the Philippines using your own knowledge. Decide whether the described case complies. "
    "If you cannot tell, answer insufficient_information. Cite the Blue Book Item number if you know it.\n"
    'Reply with only a JSON object: {"verdict": "compliant | non_compliant | insufficient_information | '
    'informational", "answer": "<short explanation>", "citations": ["Item <no>, Volume <no> (<year>)"]}. '
    "Use informational for questions that ask for a requirement rather than a compliance decision."
)

NUM = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Answer:
    question: str
    verdict: str
    answer: str
    citations: list
    context: str
    model: str
    seconds: float
    raw: str = ""
    entities: dict = field(default_factory=dict)
    draft: str = ""
    checks: list = field(default_factory=list)
    polished: bool = False


def parse_reply(text):
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in VERDICTS:
        verdict = "insufficient_information"
    cites = data.get("citations") or []
    return verdict, str(data.get("answer", text)).strip(), [str(c) for c in cites]


def polish(draft, model):
    """Returns (text, was_polished). Falls back to the draft if the rewrite changes any number."""
    try:
        text, _ = llm.chat(model, [{"role": "system", "content": POLISH_SYSTEM},
                                   {"role": "user", "content": f"DRAFT:\n{draft}"}], max_tokens=300)
    except RuntimeError:
        return draft, False
    text = text.strip()
    if text and sorted(NUM.findall(text)) == sorted(NUM.findall(draft)):
        return text, True
    return draft, False


class ComplianceChatbot:
    def __init__(self):
        self.retriever = OntologyRetriever()

    def ask(self, question, model=PRIMARY_MODEL, use_ontology=True, history=None):
        if not use_ontology:
            raw, seconds = llm.chat(model, [{"role": "system", "content": BASELINE_SYSTEM},
                                            {"role": "user", "content": question}])
            verdict, answer, cites = parse_reply(raw)
            return Answer(question, verdict, answer, cites, "", model, seconds, raw)

        start = time.perf_counter()
        ret = self.retriever.retrieve(question)
        effective = question
        if not ret.facts and history:
            # follow-up such as "20.7 mpa?": borrow the material from the previous user messages
            for prev in reversed(history[-3:]):
                combined = f"{question} {prev}"
                candidate = self.retriever.retrieve(combined)
                if candidate.facts:
                    ret, effective = candidate, combined
                    break
        decision = decide(effective, ret)
        text, polished = polish(decision.draft, model)
        seconds = time.perf_counter() - start
        context = ret.context()
        if decision.checks:
            context += "\n\nRule check: " + "; ".join(decision.checks)
        return Answer(question, decision.verdict, text, decision.citations, context, model, seconds,
                      entities=ret.entities, draft=decision.draft, checks=decision.checks, polished=polished)


def main():
    bot = ComplianceChatbot()
    print(f"DPWH compliance chatbot ({PRIMARY_MODEL} polishes grammar only). 'exit' quits; '!' prefix = LLM-only.")
    while True:
        try:
            q = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "quit", ""}:
            break
        baseline = q.startswith("!")
        a = bot.ask(q.lstrip("!").strip(), use_ontology=not baseline)
        print(f"\n[{a.verdict}] {a.answer}")
        if a.citations:
            print("Sources: " + "; ".join(a.citations))
        print(f"({a.seconds:.1f}s, {'LLM-only' if baseline else 'ontology rules + grammar polish'})")


if __name__ == "__main__":
    sys.exit(main())
