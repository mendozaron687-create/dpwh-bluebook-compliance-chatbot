"""Runs HermiT (bundled with Owlready2) on the ontology using the JRE shipped with Protege.

Reports inconsistent ontologies and unsatisfiable classes. Run: python run_reasoner.py [file.owl]
"""
import sys
from pathlib import Path

import owlready2
from owlready2 import default_world, get_ontology, sync_reasoner_hermit

HERE = Path(__file__).parent
owlready2.JAVA_EXE = str(HERE.parent / "Protege-5.6.9" / "jre" / "bin" / "java.exe")

path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "dpwh_bluebook.owl"
if path.name != "dpwh_bluebook.owl":
    # resolve the schema import from the local file (no network)
    with open(HERE / "dpwh_bluebook.owl", "rb") as schema_file:
        get_ontology("http://www.example.org/dpwh-bluebook").load(fileobj=schema_file)
onto = get_ontology(str(path.resolve())).load()

with onto:
    sync_reasoner_hermit(infer_property_values=False)

unsat = list(default_world.inconsistent_classes())
print(f"Classes: {len(list(onto.classes()))}")
print(f"Unsatisfiable classes: {unsat if unsat else 'none'}")
print("Consistent: yes" if not unsat else "Consistent: NO")
