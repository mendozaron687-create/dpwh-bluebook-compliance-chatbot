"""Runtime SWRL reasoning with Pellet (full SWRL support, including math built-ins).

The SWRL rules come from ontology/dpwh_bluebook_rules.owl. For a submitted value, small temporary individuals
(a limit with one bound, and a TestResult carrying the measured value in the limit's unit) are added to an
in-memory copy of the schema + rules, Pellet is run, and the inferred hasComplianceOutcome decides the verdict.
Java comes from the jdk4py package (Pellet needs Java 17+; Protege bundles Java 11).
"""
import re
import threading

import jdk4py
import owlready2
from owlready2 import World, destroy_entity, sync_reasoner_pellet

from config import RULES_OWL, SCHEMA_OWL

owlready2.JAVA_EXE = str(jdk4py.JAVA)

SCHEMA_IRI = "http://www.example.org/dpwh-bluebook"
FACTS_IRI = "http://www.example.org/dpwh-bluebook-answer#"
# Which rule a violated bound corresponds to; the rules themselves are in the OWL file.
BOUND_RULE = {"min": "BelowMinimum", "max": "AboveMaximum"}


class PelletRuleReasoner:
    def __init__(self, use_rules=True):
        self.lock = threading.Lock()
        self.world = World()
        with open(SCHEMA_OWL, "rb") as f:
            self.schema = self.world.get_ontology(SCHEMA_IRI).load(fileobj=f)
        if use_rules:
            self.rules = self.world.get_ontology(str(RULES_OWL)).load()
        self.facts = self.world.get_ontology(FACTS_IRI)
        self.facts.imported_ontologies.append(self.schema)
        self.rule_names = [r.name for r in self.world.rules()] if use_rules else []

    def check(self, items):
        """items: [{"min": float|None, "max": float|None, "unit": str, "value": float}].

        Returns one set of violated rule names (BelowMinimum / AboveMaximum) per item, as inferred by Pellet.
        """
        S = self.schema
        with self.lock, self.facts:
            created, probes = [], []
            units = {}
            for i, item in enumerate(items):
                key = re.sub(r"\W+", "_", item["unit"]) or "none"
                if key not in units:
                    units[key] = S.MeasurementUnit(f"U_{key}")
                    units[key].unitSymbol = item["unit"]
                    created.append(units[key])
                for bound in ("min", "max"):
                    if item.get(bound) is None:
                        continue
                    lim = S.AcceptanceCriterion(f"L{i}_{bound}")
                    lim.hasUnit = units[key]
                    if bound == "min":
                        lim.hasMinimumValue = float(item[bound])
                    else:
                        lim.hasMaximumValue = float(item[bound])
                    res = S.TestResult(f"R{i}_{bound}")
                    res.measuredValue = float(item["value"])
                    res.evaluatesLimit = [lim]
                    res.hasUnit = units[key]
                    created += [lim, res]
                    probes.append((i, bound, res))
            try:
                if self.rule_names:
                    sync_reasoner_pellet(self.world, infer_property_values=True,
                                         infer_data_property_values=True, debug=0)
                violated = [set() for _ in items]
                for i, bound, res in probes:
                    if any(o.name == "NonCompliant" for o in res.hasComplianceOutcome):
                        violated[i].add(BOUND_RULE[bound])
            finally:
                for entity in created:
                    destroy_entity(entity)
            return violated
