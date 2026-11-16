"""Smoke test: schema loads and its provenance/limit structure supports SPARQL retrieval.

Uses synthetic TEST_ individuals with placeholder values; nothing here is Blue Book content.
Run: python test_ontology.py
"""
from pathlib import Path

from rdflib import RDF, Graph, Literal, Namespace
from rdflib.namespace import XSD

HERE = Path(__file__).parent
NS = Namespace("http://www.example.org/dpwh-bluebook#")

PREFIX = (
    "PREFIX : <http://www.example.org/dpwh-bluebook#>\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
)

# CQ: acceptance limits for a material with unit, source Item, and edition.
# rdf:type/rdfs:subClassOf* makes the query subclass-aware without a reasoner.
CQ_LIMITS = PREFIX + """
SELECT ?req ?min ?unitSym ?itemNo ?year WHERE {
  ?req rdf:type/rdfs:subClassOf* :Requirement ;
       :appliesToMaterial :TEST_Material ; :hasLimit ?lim ; :hasSourceItem ?item .
  ?lim :hasMinimumValue ?min ; :hasUnit ?u .
  ?u :unitSymbol ?unitSym .
  ?item :itemNumber ?itemNo ; :belongsToVolume ?vol .
  ?vol :editionYear ?year .
}"""

CQ_TESTS = PREFIX + "SELECT ?t WHERE { :TEST_Material :hasApplicableTestMethod ?t }"
REQUIREMENT_TYPES = PREFIX + "SELECT ?c WHERE { ?c rdfs:subClassOf* :Requirement }"


def build_test_graph():
    g = Graph().parse(str(HERE / "dpwh_bluebook.ttl"), format="turtle")
    item, unit, req, lim = (NS["TEST_Item"], NS["TEST_Unit"], NS["TEST_Req"], NS["TEST_Limit"])
    g.add((item, RDF.type, NS.BlueBookItem))
    g.add((item, NS.itemNumber, Literal("000")))
    g.add((item, NS.belongsToVolume, NS["VolumeII_2013"]))
    g.add((unit, RDF.type, NS.MeasurementUnit))
    g.add((unit, NS.unitSymbol, Literal("UNIT")))
    g.add((NS["TEST_Material"], RDF.type, NS.Material))
    g.add((NS["TEST_Method"], RDF.type, NS.TestMethod))
    g.add((NS["TEST_Material"], NS.hasApplicableTestMethod, NS["TEST_Method"]))
    g.add((req, RDF.type, NS.MaterialRequirement))
    g.add((req, NS.appliesToMaterial, NS["TEST_Material"]))
    g.add((req, NS.hasSourceItem, item))
    g.add((req, NS.hasLimit, lim))
    g.add((lim, RDF.type, NS.AcceptanceCriterion))
    g.add((lim, NS.hasMinimumValue, Literal(1.0, datatype=XSD.double)))
    g.add((lim, NS.hasUnit, unit))
    return g


def main():
    g = build_test_graph()
    rows = list(g.query(CQ_LIMITS))
    assert len(rows) == 1 and str(rows[0].year) == "2013", rows
    assert len(list(g.query(CQ_TESTS))) == 1
    assert len(list(g.query(REQUIREMENT_TYPES))) == 6
    print("OK: schema loads and SPARQL competency-query patterns return expected results.")


if __name__ == "__main__":
    main()
