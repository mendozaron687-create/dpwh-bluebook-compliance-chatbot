"""Loose-phrasing checks: the chat should work without exact wording (no LLM call, Pellet decides).
Run: python test_flexible.py
"""
from reasoner import PelletRuleReasoner
from retrieval import OntologyRetriever
from verify import decide

r = OntologyRetriever(reasoner=PelletRuleReasoner())

CASES = [
    # (question, expected verdict, text that must appear in the answer or "")
    ("Does 20.7 mpa acceptable on class a bridge", "compliant", "20.7"),
    ("Does 12 m pa acceptable on class a bridge", "non_compliant", "below the minimum"),
    ("is 19 mpa ok for class a bridge", "non_compliant", "below the minimum"),
    ("class a bridge 20.7mpa", "compliant", ""),
    ("slump 90 mm class a concrete bridge ok?", "non_compliant", "above the maximum"),
    ("Is 60mm slump fine for class a bridge concrete", "compliant", ""),
    ("subbase cbr 22%", "non_compliant", ""),
    ("is cbr 30 percent ok for base course", "non_compliant", ""),
    ("rebar 270 mpa grade 40", "non_compliant", ""),
    ("concerete pavment flexural 4.0 mpa", "non_compliant", ""),
    ("hollow blocks 3.5 MPa building", "non_compliant", ""),
    ("rcp absorption 11 percent drainage", "non_compliant", ""),
    ("curing 5 days bridge concrete", "non_compliant", ""),
    ("Class A concrete 20.8 MPa", "insufficient_information", "Volume"),
    ("is 20.7 mpa ok?", "insufficient_information", "name"),
    ("is 20 ok for class a bridge", "insufficient_information", "Limits available"),
    ("what is the slump limit for class a concrete bridge", "informational", ""),
    ("tell me about asphalt emulsion 40 seconds", "insufficient_information", ""),
]
bad = 0
for q, expected, must in CASES:
    d = decide(q, r.retrieve(q))
    ok = d.verdict == expected and must.lower() in d.draft.lower()
    bad += not ok
    print(("ok  " if ok else "FAIL"), q, "->", d.verdict, "|", d.draft[:110])
print("ALL OK" if not bad else f"{bad} FAILED")
