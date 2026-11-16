"""Builds dpwh_bluebook_rules_demo.owl: the two SWRL rules plus synthetic test results, to show the rules fire.

All individuals are TEST_ data, not Blue Book content. Run: python build_rules_demo.py
Then open the file in Protege > SWRLTab > OWL+SWRL->Drools, Run Drools, Drools->OWL. Do not save the result.
(Pellet via Owlready2 needs Java 17; Protege bundles Java 11, so HermiT/Drools in Protege is used instead.)
Expected: TEST_Strength_Low and TEST_Slump_High get NonCompliant; the rest get no outcome.
"""
from pathlib import Path

from owlready2 import Imp, get_ontology

HERE = Path(__file__).parent
DEMO_IRI = "http://www.example.org/dpwh-bluebook-rules-demo#"

CASES = [
    # name, limit kind, limit value, measured value, unit, expected outcome
    ("TEST_Strength_Low", "min", 20.7, 19.5, "MPa", "NonCompliant"),
    ("TEST_Strength_Equal", "min", 20.7, 20.7, "MPa", None),
    ("TEST_Strength_High", "min", 20.7, 22.0, "MPa", None),
    ("TEST_Slump_High", "max", 75.0, 90.0, "mm", "NonCompliant"),
    ("TEST_Slump_Equal", "max", 75.0, 75.0, "mm", None),
    ("TEST_Slump_Low", "max", 75.0, 60.0, "mm", None),
    ("TEST_Unit_Mismatch", "min", 20.7, 5.0, "psi", None),
]


def build():
    with open(HERE / "dpwh_bluebook.owl", "rb") as f:
        schema = get_ontology("http://www.example.org/dpwh-bluebook").load(fileobj=f)
    demo = get_ontology(DEMO_IRI)
    demo.imported_ontologies.append(schema)
    S = schema
    with demo:
        units = {}
        for case in CASES:
            name, kind, limit_value, value, unit, _ = case
            if unit not in units:
                u = S.MeasurementUnit("TEST_Unit_" + unit)
                u.unitSymbol = unit
                units[unit] = u
            limit_unit = units["MPa"] if unit == "psi" else units[unit]
            lim = S.AcceptanceCriterion(name + "_limit")
            lim.hasUnit = limit_unit
            if kind == "min":
                lim.hasMinimumValue = limit_value
            else:
                lim.hasMaximumValue = limit_value
            res = S.TestResult(name)
            res.measuredValue = value
            res.evaluatesLimit = [lim]
            res.hasUnit = units[unit]

        rules = {
            "BelowMinimum": ("TestResult(?r), evaluatesLimit(?r, ?l), measuredValue(?r, ?v), "
                             "hasMinimumValue(?l, ?m), hasUnit(?r, ?u), hasUnit(?l, ?u), "
                             "lessThan(?v, ?m) -> hasComplianceOutcome(?r, NonCompliant)"),
            "AboveMaximum": ("TestResult(?r), evaluatesLimit(?r, ?l), measuredValue(?r, ?v), "
                             "hasMaximumValue(?l, ?x), hasUnit(?r, ?u), hasUnit(?l, ?u), "
                             "greaterThan(?v, ?x) -> hasComplianceOutcome(?r, NonCompliant)"),
        }
        for rname, text in rules.items():
            Imp(rname).set_as_rule(text, namespaces=[schema, demo])
    demo.save(file=str(HERE / "dpwh_bluebook_rules_demo.owl"), format="rdfxml")
    print("Wrote dpwh_bluebook_rules_demo.owl with", len(CASES), "synthetic test results")


if __name__ == "__main__":
    build()
