"""Ontology retrieval: extract entities from a question, run SPARQL, return cited context."""
import difflib
import re
from dataclasses import dataclass, field

from rdflib import Graph

from config import DATA_OWL, SCHEMA_OWL
from reasoner import PelletRuleReasoner

PREFIX = """
PREFIX : <http://www.example.org/dpwh-bluebook#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

ROMAN = {"1": "I", "2": "II", "3": "III", "i": "I", "ii": "II", "iii": "III"}
WORK_TYPE_WORDS = {
    "Highway": ["highway", "road", "pavement"],
    "Bridge": ["bridge"],
    "Airport": ["airport", "runway"],
    "Building": ["building"],
    "FloodControlAndDrainage": ["flood", "drainage"],
}

TESTING_WORDS = re.compile(r"\b(test methods?|what test|which test|frequency|how often|how many|sampl\w*|standards?)\b", re.I)

STOP = {"a", "an", "the", "of", "for", "in", "on", "and", "is", "it", "this", "that", "to", "with", "at", "by",
        "does", "do", "did", "can", "be", "are", "was", "ok", "okay", "acceptable", "comply", "complies",
        "compliant", "pass", "passes", "meet", "meets", "what", "which", "how", "i", "my", "our", "we", "if"}
GENERIC = {"concrete", "material", "materials", "course", "test", "strength", "value", "work", "works"}


def tokens(text):
    """Lower-case word set; 'class a' / 'grade 40' / 'type ii' stay together as one word."""
    t = re.sub(r"\b(class|grade|type)\s+([a-z0-9]+)\b", r"\1_\2", text.lower())
    return {w for w in re.findall(r"[a-z0-9_]+", t) if w not in STOP}


def same_word(a, b):
    if a == b or a.rstrip("s") == b.rstrip("s"):
        return True
    return len(a) > 4 and len(b) > 4 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.86


def covered(word, qtokens):
    return any(same_word(word, q) for q in qtokens)

LABELS_QUERY = PREFIX + """
SELECT ?e ?type ?label WHERE {
  VALUES ?type { :Material :QualityParameter }
  ?e rdf:type ?type ; rdfs:label ?label .
}"""

FACTS_QUERY = PREFIX + """
SELECT ?req ?reqLabel ?text ?strength ?page ?itemNo ?itemTitle ?volNo ?year ?sub ?matLabel ?wt ?paramName ?lim ?unitIri
       ?paramLabel ?min ?max ?unit ?limitType ?tmLabel ?std ?freqCount ?freqQty ?freqUnit ?curing ?grade ?note
WHERE {
  ?req rdf:type/rdfs:subClassOf* :Requirement ; rdfs:label ?reqLabel ; :verbatimText ?text ;
       :appliesToMaterial ?mat ; :hasSourceItem ?item .
  ?mat rdfs:label ?matLabel .
  ?item :itemNumber ?itemNo ; :itemTitle ?itemTitle ; :belongsToVolume ?vol .
  ?vol :volumeNumber ?volNo ; :editionYear ?year .
  OPTIONAL { ?req :normativeStrength ?strength }
  OPTIONAL { ?req :sourcePage ?page }
  OPTIONAL { ?req :hasSourceSubItem/:subItemDesignation ?sub }
  OPTIONAL { ?req :curingAgeDays ?curing }
  OPTIONAL { ?req :applicableClassOrGrade ?grade }
  OPTIONAL { ?req rdfs:comment ?note }
  OPTIONAL { ?req :appliesToWorkType ?wt }
  OPTIONAL {
    ?req :hasLimit ?lim .
    ?lim rdf:type ?limitType .
    FILTER(?limitType IN (:AcceptanceCriterion, :ToleranceValue, :SpecificationLimit))
    OPTIONAL { ?lim :hasMinimumValue ?min }
    OPTIONAL { ?lim :hasMaximumValue ?max }
    OPTIONAL { ?lim :hasUnit ?unitIri . ?unitIri :unitSymbol ?unit }
    OPTIONAL { ?lim :limitsParameter/rdfs:label ?paramLabel }
    OPTIONAL { ?lim :limitsParameter/:parameterName ?paramName }
  }
  OPTIONAL {
    ?req :requiresTestMethod ?tm . ?tm rdfs:label ?tmLabel .
    OPTIONAL { ?tm :standardDesignation ?std }
  }
  OPTIONAL { ?req :hasTestingFrequency ?fr .
    ?fr :frequencyCount ?freqCount ; :frequencyQuantity ?freqQty ; :frequencyQuantityUnit ?freqUnit }
}"""


@dataclass
class Retrieval:
    entities: dict
    facts: list = field(default_factory=list)
    want_testing: bool = False
    check: object = None  # callable([(fact, value)]) -> [set of SWRL rules fired], via Pellet
    suggestions: list = field(default_factory=list)  # encoded items/limits to offer when nothing matched

    def context(self):
        if not self.facts:
            return ""
        blocks = []
        for f in self.facts:
            lines = [
                f"[{f['reqLabel']}] Volume {f['volNo']} ({f['year']} edition), Item {f['itemNo']} - "
                f"{f['itemTitle']}, sub-item {f.get('sub', 'n/a')}, page {f.get('page', 'n/a')}",
                f"Requirement: {f['text']}",
            ]
            bounds = []
            if f.get("min") is not None:
                bounds.append(f"minimum {f['min']:g} {f.get('unit', '')}".strip())
            if f.get("max") is not None:
                bounds.append(f"maximum {f['max']:g} {f.get('unit', '')}".strip())
            if bounds:
                age = f" at {f['curing']} days" if f.get("curing") is not None else ""
                lines.append(f"Limit ({f['limitType']}, {f.get('paramLabel', 'value')}): " + "; ".join(bounds) + age)
            if self.want_testing:
                if f.get("tmLabel"):
                    lines.append(f"Test method: {f['tmLabel']}" + (f" ({f['std']})" if f.get("std") else ""))
                if f.get("freqCount") is not None:
                    lines.append(f"Testing frequency: {f['freqCount']} per {f['freqQty']:g} {f['freqUnit']}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)


class OntologyRetriever:
    def __init__(self, reasoner=None):
        self.graph = Graph()
        self.graph.parse(str(SCHEMA_OWL), format="xml")
        self.graph.parse(str(DATA_OWL), format="xml")
        self.materials = {}
        self.parameters = {}
        for row in self.graph.query(LABELS_QUERY):
            target = self.materials if str(row.type).endswith("Material") else self.parameters
            target.setdefault(str(row.e), set()).add(str(row.label).lower())
        self.rows = [{k: v.toPython() for k, v in r.asdict().items()} for r in self.graph.query(FACTS_QUERY)]
        self.reasoner = reasoner or PelletRuleReasoner()
        for r in self.rows:
            r["limitType"] = str(r.get("limitType", "")).rsplit("#", 1)[-1]
            r["wt"] = str(r.get("wt", "")).rsplit("#", 1)[-1]
            for k in ("min", "max"):
                if r.get(k) is not None:
                    # xsd:float in the OWL file carries float32 noise (20.7 -> 20.70000076)
                    r[k] = float(f"{float(r[k]):.6g}")

    def check_limits(self, pairs):
        """pairs: [(fact, submitted_value)]. Runs the ontology's SWRL rules with Pellet and returns, per pair,
        the set of rules that fired (BelowMinimum / AboveMaximum). The verdict comes only from the rules."""
        return self.reasoner.check([{"min": f.get("min"), "max": f.get("max"), "unit": f.get("unit", ""),
                                     "value": v} for f, v in pairs])

    def _best_label_match(self, labels, qtokens):
        """Best share of a label's words found in the question, and whether a distinctive word matched."""
        best = (0.0, False)
        for label in labels:
            ltokens = tokens(label)
            if not ltokens:
                continue
            hit = {t for t in ltokens if covered(t, qtokens)}
            score = (len(hit) / len(ltokens), bool(hit - GENERIC))
            best = max(best, score)
        return best

    def match_entities(self, catalog, qtokens, allow_partial, generic_ok=False):
        full, partial = set(), {}
        for iri, labels in catalog.items():
            score, distinctive = self._best_label_match(labels, qtokens)
            if score == 1.0:
                full.add(iri)
            elif allow_partial and score >= 0.5 and (distinctive or generic_ok):
                partial[iri] = score
        if full:
            return full
        if partial:
            top = max(partial.values())
            return {iri for iri, s in partial.items() if s == top}
        return set()

    def extract_entities(self, question):
        q = question.lower()
        qtokens = tokens(question)
        ents = {"materials": set(), "parameters": set(), "volume": None, "items": set(), "work_types": set()}
        # forgiving matching: partial names ("class a bridge" -> Class A concrete) and small typos are accepted
        ents["materials"] = self.match_entities(self.materials, qtokens, allow_partial=True)
        ents["parameters"] = self.match_entities(self.parameters, qtokens, allow_partial=False)
        m = re.search(r"\bvol(?:ume|\.)?\s*(iii|ii|i|[123])\b", q)
        if m:
            ents["volume"] = ROMAN[m.group(1)]
        elif re.search(r"\b2013\b", q):
            ents["volume"] = "II"
        elif re.search(r"\b2019\b", q):
            ents["volume"] = "III"
        for m in re.finditer(r"\bitem\s+([a-z]?\d+[a-z]?)\b", q):
            ents["items"].add(m.group(1).upper())
        for wt, words in WORK_TYPE_WORDS.items():
            if any(w in q for w in words):
                ents["work_types"].add(wt)
        if not ents["materials"] and not ents["items"] and ents["work_types"]:
            # only a work type and a generic word ("bridge concrete"): accept materials used in that work type
            in_type = {r["matLabel"].lower() for r in self.rows if r.get("wt") in ents["work_types"]}
            generic = self.match_entities(self.materials, qtokens, allow_partial=True, generic_ok=True)
            ents["materials"] = {iri for iri in generic if self.materials[iri] & in_type}
        return ents

    def retrieve(self, question):
        ents = self.extract_entities(question)
        rows = self.rows

        selected = []
        mat_labels = {l for iri in ents["materials"] for l in self.materials[iri]}
        for r in rows:
            if ents["items"] and r["itemNo"] not in ents["items"]:
                continue
            if mat_labels and r["matLabel"].lower() not in mat_labels:
                continue
            if not mat_labels and not ents["items"]:
                continue
            if ents["volume"] and r["volNo"] != ents["volume"]:
                continue
            selected.append(r)

        if ents["parameters"]:
            param_labels = {l for iri in ents["parameters"] for l in self.parameters[iri]}
            narrowed = [r for r in selected if r.get("paramLabel", "").lower() in param_labels]
            if narrowed:
                selected = narrowed

        seen, unique = set(), []
        for r in selected:
            key = r["reqLabel"]
            if key not in seen:
                seen.add(key)
                unique.append(r)
        public = {
            "materials": sorted(ents["materials"]),
            "parameters": sorted(ents["parameters"]),
            "volume": ents["volume"],
            "work_types": sorted(ents["work_types"]),
            "items": sorted(ents["items"]),
        }
        suggestions = []
        if not unique:
            seen_s = set()
            for r in rows:
                key = (r["itemTitle"], r.get("paramName"), r.get("unit"))
                if r.get("unit") and key not in seen_s:
                    seen_s.add(key)
                    suggestions.append({"item": r["itemTitle"], "param": r.get("paramName") or "value",
                                        "unit": r["unit"], "volume": r["volNo"]})
        return Retrieval(entities=public, facts=unique, want_testing=bool(TESTING_WORDS.search(question)),
                         check=self.check_limits, suggestions=suggestions)
