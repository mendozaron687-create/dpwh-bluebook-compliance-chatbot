"""Compliance check: the SWRL rules in the ontology decide; this module only prepares the inputs.

The LLM is used afterwards only to polish the grammar. Python selects which limits apply (retrieval,
volume/work-type disambiguation, unit matching) and runs the ontology's SWRL rules with the Pellet reasoner.
"""
import re
from dataclasses import dataclass, field

UNIT_ALIASES = {"percent": "%", "pct": "%", "day": "days", "mpa": "mpa", "mm": "mm"}
NUMBER = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(%|[A-Za-z][A-Za-z/.]*)?")


def norm_unit(unit):
    u = (unit or "").lower().strip(". ")
    return UNIT_ALIASES.get(u, u)


def submitted_values(question):
    """(value, unit) pairs stated in the question, ignoring Item numbers, volumes, and edition years."""
    q = re.sub(r"\bitem\s+\w+", " ", question, flags=re.I)
    q = re.sub(r"\bvol(?:ume|\.)?\s*\w+", " ", q, flags=re.I)
    q = re.sub(r"\b(2013|2019)\b", " ", q)
    q = re.sub(r"\b([mkg])\s*[- ]\s*pa\b", r"\1pa", q, flags=re.I)  # "m pa", "M-Pa" -> "mpa"
    q = re.sub(r"\bcu\.?\s*m\b", "cu.m", q, flags=re.I)
    q = re.sub(r"\bsq\.?\s*m\b", "sq.m", q, flags=re.I)
    return [(float(m.group(1)), norm_unit(m.group(2))) for m in NUMBER.finditer(q)]


def citation(f):
    return f"Item {f['itemNo']}, Volume {f['volNo']} ({f['year']})"


def where(f):
    return f"{citation(f)}, sub-item {f.get('sub', 'n/a')}"


@dataclass
class Decision:
    verdict: str
    draft: str
    citations: list
    checks: list = field(default_factory=list)


def _insufficient(text):
    return Decision("insufficient_information", text, [])


def _informational(ret, facts):
    lines, cites = [], []
    for f in facts[:4]:
        if ret.want_testing and f.get("tmLabel"):
            line = f"{f.get('paramName', 'The requirement')} is tested by {f['tmLabel']}"
            line += f" ({f['std']})" if f.get("std") else ""
            if f.get("freqCount") is not None:
                line += f", at a frequency of {f['freqCount']} per {f['freqQty']:g} {f['freqUnit']}"
            lines.append(f"{line} ({where(f)}).")
        else:
            lines.append(f"{f['text']} ({where(f)}).")
        cites.append(citation(f))
    return Decision("informational", " ".join(lines), sorted(set(cites)))


def _options(facts, limit=6):
    seen, out = set(), []
    for f in facts:
        key = (f.get("paramName"), f.get("unit"))
        if key[0] and key not in seen:
            seen.add(key)
            out.append(f"{key[0]} ({key[1]})" if key[1] else key[0])
    return ", ".join(out[:limit])


def _encoded_items(ret, limit=8):
    titles = []
    for s in ret.suggestions:
        if s["item"] not in titles:
            titles.append(s["item"])
    return ", ".join(titles[:limit])


def decide(question, ret):
    values = submitted_values(question)
    facts = ret.facts
    if not facts:
        if values:
            units = {u for _, u in values if u}
            fits = [s for s in ret.suggestions if norm_unit(s["unit"]) in units] or ret.suggestions
            names = ", ".join(dict.fromkeys(f"{s['item']} ({s['param']}, {s['unit']})" for s in fits[:6]))
            return _insufficient("I could not tell which material or work item this value refers to. Please name "
                                 f"it. Items I have limits for include: {names}.")
        return _insufficient("I could not find that material or item in the encoded Blue Book content. "
                             f"Items I currently cover include: {_encoded_items(ret)}.")
    if not values:
        wt = set(ret.entities.get("work_types", []))
        in_type = [f for f in facts if f.get("wt") in wt] if wt else []
        return _informational(ret, in_type or facts)

    limited = [f for f in facts if f.get("min") is not None or f.get("max") is not None]
    if not limited:
        return _insufficient("The retrieved provisions state no numeric limit to check the submitted value against.")

    evaluable = []
    for f in limited:
        unit = norm_unit(f.get("unit"))
        match = [v for v, u in values if u == unit] or ([v for v, u in values if u == ""] if len(values) == 1 else [])
        if match:
            evaluable.append((f, match[0]))
    if not evaluable:
        return _insufficient("None of the limits I found for this item use the unit you gave. Limits available: "
                             f"{_options(limited)}. Please give the value with its unit.")

    # the unit has already narrowed the candidates, so volume ambiguity only counts among them
    volumes = {f["volNo"] for f, _ in evaluable}
    if len(volumes) > 1:
        wt = set(ret.entities.get("work_types", []))
        by_type = [(f, v) for f, v in evaluable if f.get("wt") in wt]
        if by_type and len({f["volNo"] for f, _ in by_type}) == 1:
            evaluable = by_type
        else:
            names = " and ".join(f"Volume {v}" for v in sorted(volumes))
            return _insufficient(f"The limits differ between {names}. Please state which volume or type of work "
                                 "(for example bridge, building) applies.")
    if not ret.entities.get("parameters") and len({f.get("paramName") for f, _ in evaluable}) > 1:
        return _insufficient("Several limits could apply to that value: "
                             f"{_options([f for f, _ in evaluable])}. Please say which property it refers to.")

    for f, _ in evaluable:
        age = f.get("curing")
        stated_ages = [x for x, u in values if u == "days" and f.get("unit") != "days"]
        if age is not None and stated_ages and age not in stated_ages:
            return _insufficient(f"The limit for {f.get('paramName') or 'value'} applies at {age} days, but a "
                                 "different age was stated.")

    # One Pellet run decides all limits: the ontology's SWRL rules, not Python comparisons, flag violations.
    fired_per_fact = ret.check(evaluable)
    sentences, checks, cites, failed = [], [], [], False
    for (f, v), fired in zip(evaluable, fired_per_fact):
        unit = f.get("unit", "")
        name = f.get("paramName") or "value"
        for label, bound, rule in (("minimum", f.get("min"), "BelowMinimum"),
                                   ("maximum", f.get("max"), "AboveMaximum")):
            if bound is None:
                continue
            violated = rule in fired
            failed |= violated
            checks.append(f"SWRL rule {rule} (Pellet): {v:g} {unit} vs {label} {bound:g} {unit} -> "
                          f"{'FIRED (NonCompliant)' if violated else 'not fired (no violation)'} ({where(f)})")
            if not violated:
                sentences.append(f"The {name} of {v:g} {unit} meets the {label} of {bound:g} {unit} required by "
                                 f"{where(f)}.")
            else:
                word = "below the minimum" if label == "minimum" else "above the maximum"
                sentences.append(f"The {name} of {v:g} {unit} is {word} of {bound:g} {unit} required by "
                                 f"{where(f)}.")
        cites.append(citation(f))
    head = "Non-compliant. " if failed else "Compliant. "
    return Decision("non_compliant" if failed else "compliant", head + " ".join(sentences),
                    sorted(set(cites)), checks)
