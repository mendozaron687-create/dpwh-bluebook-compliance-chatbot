"""Checks that the Pellet SWRL reasoner decides the verdicts.

1. Cross-validation: Pellet reproduces the outcomes Protege's Drools engine gave on the demo ontology.
2. Dependence: with the rules removed from the ontology the chatbot can no longer flag a violation.
3. End to end: boundary and clear cases through the chatbot pipeline (no LLM call).
Run: python test_swrl.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "ontology"))
from build_rules_demo import CASES  # noqa: E402

from reasoner import PelletRuleReasoner  # noqa: E402
from retrieval import OntologyRetriever  # noqa: E402
from verify import decide  # noqa: E402

# Outcomes observed in Protege (SWRLTab, Drools) for ontology/dpwh_bluebook_rules_demo.owl
PROTEGE_RESULTS = {
    "TEST_Strength_Low": True, "TEST_Strength_Equal": False, "TEST_Strength_High": False,
    "TEST_Slump_High": True, "TEST_Slump_Equal": False, "TEST_Slump_Low": False, "TEST_Unit_Mismatch": False,
}


def cross_validate(reasoner):
    items = []
    for name, kind, limit_value, value, unit, _ in CASES:
        # the unit-mismatch case is excluded by retrieval before reasoning, as in the chatbot
        items.append({"min": limit_value if kind == "min" else None, "max": limit_value if kind == "max" else None,
                      "unit": unit if unit != "psi" else "MPa", "value": value})
    results = reasoner.check(items)
    for (name, *_), fired in zip(CASES, results):
        expected = PROTEGE_RESULTS[name]
        if name == "TEST_Unit_Mismatch":
            continue
        assert bool(fired) == expected, f"{name}: Pellet={bool(fired)}, Protege={expected}"
    print(f"OK: Pellet matches Protege/Drools on {len(CASES) - 1} demo cases (unit mismatch is handled in retrieval)")


def depends_on_rules(reasoner):
    q = "Class A structural concrete for a bridge has a 28-day compressive strength of 19.5 MPa (Vol II)."
    r = OntologyRetriever(reasoner=reasoner)
    assert decide(q, r.retrieve(q)).verdict == "non_compliant"
    no_rules = OntologyRetriever(reasoner=PelletRuleReasoner(use_rules=False))
    assert decide(q, no_rules.retrieve(q)).verdict == "compliant"
    print("OK: without the SWRL rules the violation disappears, so the rules decide the verdict")


def end_to_end(reasoner):
    r = OntologyRetriever(reasoner=reasoner)
    cases = [
        ("Class A bridge concrete (Vol II) 28-day compressive strength of 19.5 MPa.", "non_compliant"),
        ("Class A bridge concrete (Vol II) 28-day compressive strength of exactly 20.7 MPa.", "compliant"),
        ("Class A bridge concrete shows a slump of 90 mm.", "non_compliant"),
        ("Class A bridge concrete shows a slump of 75 mm.", "compliant"),
        ("Aggregate subbase material tested a soaked CBR of exactly 25 percent.", "compliant"),
        ("Class A structural concrete has a 28-day strength of 20.8 MPa.", "insufficient_information"),
    ]
    for q, expected in cases:
        got = decide(q, r.retrieve(q)).verdict
        assert got == expected, f"{q!r}: {got} != {expected}"
    print(f"OK: {len(cases)} end-to-end verdicts as expected")


if __name__ == "__main__":
    shared = PelletRuleReasoner()
    cross_validate(shared)
    depends_on_rules(shared)
    end_to_end(shared)
