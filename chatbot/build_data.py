"""Loads the provisions CSV into an OWL instance file that imports the Protege schema.

Output: ontology/dpwh_bluebook_data.owl. Open it in Protege (the catalog resolves the schema import)
to browse individuals. Run: python build_data.py
"""
import csv
import re

from owlready2 import get_ontology

from config import DATA_OWL, PROVISIONS_CSV, SCHEMA_OWL

DATA_IRI = "http://www.example.org/dpwh-bluebook-data#"
REQ_CLASS = {
    "material": "MaterialRequirement",
    "workmanship": "WorkmanshipRequirement",
    "testing": "TestingRequirement",
    "quality_control": "QualityControlRequirement",
    "quality_assurance": "QualityAssuranceRequirement",
}
LIMIT_CLASS = {
    "acceptance": "AcceptanceCriterion",
    "tolerance": "ToleranceValue",
    "specification": "SpecificationLimit",
}
WORK_TYPES = {"Highway", "Bridge", "Airport", "Building", "FloodControlAndDrainage"}


def slug(text):
    return re.sub(r"\W+", "_", text.strip()).strip("_")


def labels(text):
    return [t.strip() for t in text.split("|") if t.strip()]


def num(value):
    return float(value) if value.strip() else None


def build():
    schema = get_ontology(str(SCHEMA_OWL)).load()
    data = get_ontology(DATA_IRI)
    data.imported_ontologies.append(schema)
    S = schema
    cache = {}

    def get(cls, key, label=None):
        k = (cls.name, key)
        if k not in cache:
            with data:
                ind = cls(slug(key))
            ind.label = [label or key]
            cache[k] = ind
        return cache[k]

    with data:
        volumes = {v.volumeNumber: v for v in S.Volume.instances()}
        work_types = {w.name: w for w in S.PublicWorkType.instances()}
        with open(PROVISIONS_CSV, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            vol = volumes[r["volume"]]
            item = get(S.BlueBookItem, f"Item_{r['item_number']}_Vol{r['volume']}", f"Item {r['item_number']}")
            item.itemNumber = r["item_number"]
            item.itemTitle = r["item_title"]
            item.belongsToVolume = vol
            sub = get(S.SubItem, f"Sub_{r['sub_item']}_Vol{r['volume']}", r["sub_item"])
            sub.subItemDesignation = r["sub_item"]
            sub.isPartOfItem = item

            req = getattr(S, REQ_CLASS[r["requirement_type"]])(slug(r["provision_id"]))
            req.label = [r["provision_id"]]
            req.verbatimText = r["verbatim_text"]
            req.requirementText = r["verbatim_text"]
            req.normativeStrength = r["normative_strength"]
            req.sourcePage = [int(r["source_page"])]
            req.hasSourceItem = [item]
            req.hasSourceSubItem = [sub]
            if r["curing_age_days"]:
                req.curingAgeDays = [int(r["curing_age_days"])]
            if r["class_or_grade"]:
                req.applicableClassOrGrade = [r["class_or_grade"]]
            if r["applies_to_work_type"] in WORK_TYPES:
                req.appliesToWorkType = [work_types[r["applies_to_work_type"]]]
            req.comment = [r["notes"]] if r["notes"] else []

            materials = labels(r["material"])
            mat = get(S.Material, materials[0])
            mat.label = materials
            req.appliesToMaterial = [mat]

            param = None
            if r["parameter"]:
                names = labels(r["parameter"])
                param = get(S.QualityParameter, names[0])
                param.label = names
                param.parameterName = names[0]

            unit = None
            if r["unit"]:
                unit = get(S.MeasurementUnit, "unit_" + r["unit"], r["unit"])
                unit.unitSymbol = r["unit"]

            if r["limit_type"] and (r["min_value"] or r["max_value"]):
                lim = getattr(S, LIMIT_CLASS[r["limit_type"]])(slug(r["provision_id"]) + "_limit")
                lim.label = [f"Limit of {r['provision_id']}"]
                if r["min_value"]:
                    lim.hasMinimumValue = num(r["min_value"])
                if r["max_value"]:
                    lim.hasMaximumValue = num(r["max_value"])
                if param:
                    lim.limitsParameter = param
                if unit:
                    lim.hasUnit = unit
                req.hasLimit = [lim]
                if r["limit_type"] == "acceptance":
                    req.hasAcceptanceCriterion = [lim]
                if r["limit_type"] == "tolerance":
                    req.hasTolerance = [lim]

            if r["test_method"]:
                tm = get(S.TestMethod, f"{r['test_method']} {r['test_standard']}".strip(), r["test_method"])
                if r["test_standard"]:
                    std = get(S.ReferenceStandard, r["test_standard"])
                    std.standardDesignation = r["test_standard"]
                    tm.followsStandard = [std]
                    tm.standardDesignation = r["test_standard"]
                if param:
                    tm.measuresParameter = [param]
                tm.appliesToMaterial = [mat]
                mat.hasApplicableTestMethod.append(tm)
                req.requiresTestMethod = [tm]

            if r["frequency_count"]:
                fr = S.TestingFrequency(slug(r["provision_id"]) + "_frequency")
                fr.label = [f"{r['frequency_count']} per {r['frequency_quantity']} {r['frequency_quantity_unit']}"]
                fr.frequencyCount = int(r["frequency_count"])
                fr.frequencyQuantity = num(r["frequency_quantity"])
                fr.frequencyQuantityUnit = r["frequency_quantity_unit"]
                req.hasTestingFrequency = [fr]

    data.save(file=str(DATA_OWL), format="rdfxml")
    print(f"Wrote {DATA_OWL} from {len(rows)} provisions")


if __name__ == "__main__":
    build()
