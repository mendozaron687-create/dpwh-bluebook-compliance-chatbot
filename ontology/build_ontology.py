"""Builds the DPWH Blue Book ontology schema (TBox) with Owlready2.

Output: dpwh_bluebook.owl (RDF/XML, opens in Protege 5.6.x) and dpwh_bluebook.ttl.
Only the schema, scope individuals, and SWRL rules are generated here. Blue Book
provisions are added later as individuals from the verified encoding CSV.
"""
import types
from pathlib import Path

from owlready2 import (
    AllDisjoint,
    DataProperty,
    FunctionalProperty,
    Imp,
    ObjectProperty,
    Thing,
    get_ontology,
)

HERE = Path(__file__).parent
IRI = "http://www.example.org/dpwh-bluebook#"

onto = get_ontology(IRI)

SCOPE_NOTE = (
    "Scope: DPWH Standard Specifications Vol. II (2013) and Vol. III (2019, buildings and "
    "flood control/drainage), covering QA/QC, materials, workmanship, and testing."
)

# name: (parent, comment)
CLASSES = {
    # Document structure / provenance
    "Volume": ("Thing", "A volume of the DPWH Standard Specifications. Carries the edition year."),
    "BlueBookItem": ("Thing", "A numbered Item of the Blue Book (e.g. 'Item 311')."),
    "SubItem": ("Thing", "A sub-item, paragraph, or table of a Blue Book Item, used as the finest source locator."),
    # Domain concepts
    "PublicWorkType": ("Thing", "Type of public works covered by the study."),
    "ConstructionWork": ("Thing", "A construction activity or work item governed by an Item (e.g. pavement, structural concrete)."),
    "Material": ("Thing", "A construction material whose quality is specified. Subclasses are preliminary and are refined after document analysis."),
    "Aggregate": ("Material", "Preliminary category."),
    "CementitiousMaterial": ("Material", "Preliminary category: cement, fly ash, and similar."),
    "ConcreteMaterial": ("Material", "Preliminary category."),
    "BituminousMaterial": ("Material", "Preliminary category."),
    "SteelMaterial": ("Material", "Preliminary category."),
    "TimberMaterial": ("Material", "Preliminary category."),
    "MasonryMaterial": ("Material", "Preliminary category."),
    "PipeAndDrainageMaterial": ("Material", "Preliminary category."),
    "PaintAndCoatingMaterial": ("Material", "Preliminary category."),
    "GeosyntheticMaterial": ("Material", "Preliminary category."),
    "Admixture": ("Material", "Preliminary category."),
    "TestMethod": ("Thing", "A sampling or testing procedure (e.g. an AASHTO or ASTM method) cited by the Blue Book."),
    "ReferenceStandard": ("Thing", "An external standard referenced by the Blue Book (AASHTO, ASTM, PNS, etc.)."),
    "QualityParameter": ("Thing", "A measurable property that is specified or tested (e.g. compressive strength, slump)."),
    "MeasurementUnit": ("Thing", "A unit of measurement. Kept separate from numeric values."),
    "QualityControlActivity": ("Thing", "A QA/QC activity required by the specifications."),
    "SamplingActivity": ("QualityControlActivity", ""),
    "InspectionActivity": ("QualityControlActivity", ""),
    "TestingActivity": ("QualityControlActivity", ""),
    "SubmittalActivity": ("QualityControlActivity", "Submission of certificates, test reports, or samples."),
    # Specification content
    "Requirement": ("Thing", "A normative statement from the Blue Book."),
    "MaterialRequirement": ("Requirement", ""),
    "WorkmanshipRequirement": ("Requirement", ""),
    "TestingRequirement": ("Requirement", ""),
    "QualityControlRequirement": ("Requirement", ""),
    "QualityAssuranceRequirement": ("Requirement", ""),
    "QuantitativeLimit": ("Thing", "A numeric bound or exact value attached to a quality parameter."),
    "AcceptanceCriterion": ("QuantitativeLimit", "A limit that a test result must satisfy for acceptance."),
    "ToleranceValue": ("QuantitativeLimit", "An allowable deviation or tolerance."),
    "SpecificationLimit": ("QuantitativeLimit", "A limit on a material or work property that is not an acceptance test (e.g. gradation band, thickness)."),
    "TestingFrequency": ("Thing", "How often sampling or testing is required (e.g. 1 test per 150 cu.m)."),
    "ApplicabilityCondition": ("Thing", "A condition under which a requirement applies (class, grade, location, work type)."),
    # Compliance verification
    "TestResult": ("Thing", "A submitted or measured result to be checked against a limit. Not Blue Book content."),
    "ComplianceOutcome": ("Thing", "Verdict category assigned to a test result."),
}

# Top-level classes that are mutually disjoint.
DISJOINT_GROUP = [
    "Volume", "BlueBookItem", "SubItem", "PublicWorkType", "ConstructionWork", "Material",
    "TestMethod", "ReferenceStandard", "QualityParameter", "MeasurementUnit",
    "QualityControlActivity", "Requirement", "QuantitativeLimit", "TestingFrequency",
    "ApplicabilityCondition", "TestResult", "ComplianceOutcome",
]

# name: (kind, domain classes, range, characteristics, comment)
# kind: "obj" or a python datatype for data properties. Empty domain means unrestricted.
PROPERTIES = {
    # Provenance and structure
    "belongsToVolume": ("obj", ["BlueBookItem"], ["Volume"], ["functional"], "Volume containing the Item."),
    "isPartOfItem": ("obj", ["SubItem"], ["BlueBookItem"], ["functional"], "Item containing the sub-item."),
    "hasSourceItem": ("obj", [], ["BlueBookItem"], [], "Blue Book Item from which an encoded element was taken."),
    "hasSourceSubItem": ("obj", [], ["SubItem"], [], "Sub-item, paragraph, or table from which an encoded element was taken."),
    "crossReferencesItem": ("obj", ["Requirement", "BlueBookItem"], ["BlueBookItem"], [], "Cross-reference to another Item."),
    "volumeNumber": (str, ["Volume"], None, ["functional"], "Roman numeral of the volume, e.g. 'II'."),
    "editionYear": (int, ["Volume"], None, ["functional"], "Edition year of the volume."),
    "itemNumber": (str, ["BlueBookItem"], None, ["functional"], "Item number as printed, e.g. '311'."),
    "itemTitle": (str, ["BlueBookItem"], None, ["functional"], "Item title as printed."),
    "subItemDesignation": (str, ["SubItem"], None, ["functional"], "Paragraph or table designation, e.g. '311.3.2'."),
    "sourcePage": (int, [], None, [], "Page number in the source volume."),
    "verbatimText": (str, [], None, ["functional"], "Original wording from the Blue Book."),
    # Requirement relations
    "appliesToMaterial": ("obj", ["Requirement", "TestMethod"], ["Material"], [], "Material a requirement or test applies to."),
    "appliesToWork": ("obj", ["Requirement"], ["ConstructionWork"], [], "Construction work a requirement applies to."),
    "appliesToWorkType": ("obj", ["Requirement", "ConstructionWork"], ["PublicWorkType"], [], "Public work type in which this applies."),
    "requiresTestMethod": ("obj", ["Requirement"], ["TestMethod"], [], "Test method required by a requirement."),
    "requiresActivity": ("obj", ["Requirement"], ["QualityControlActivity"], [], "QA/QC activity required."),
    "hasApplicableTestMethod": ("obj", ["Material"], ["TestMethod"], [], "Test method applicable to a material."),
    "hasAcceptanceCriterion": ("obj", ["TestMethod", "Requirement"], ["AcceptanceCriterion"], [], "Acceptance criterion for a test or requirement."),
    "hasLimit": ("obj", ["Requirement"], ["QuantitativeLimit"], [], "Quantitative limit stated by a requirement."),
    "hasTolerance": ("obj", ["Requirement"], ["ToleranceValue"], [], "Tolerance stated by a requirement."),
    "hasTestingFrequency": ("obj", ["Requirement"], ["TestingFrequency"], [], "Required testing frequency."),
    "hasCondition": ("obj", ["Requirement", "QuantitativeLimit"], ["ApplicabilityCondition"], [], "Condition under which this applies."),
    "limitsParameter": ("obj", ["QuantitativeLimit"], ["QualityParameter"], ["functional"], "Parameter a limit constrains."),
    "measuresParameter": ("obj", ["TestMethod"], ["QualityParameter"], [], "Parameter measured by a test method."),
    "followsStandard": ("obj", ["TestMethod", "Material"], ["ReferenceStandard"], [], "External standard followed."),
    "hasUnit": ("obj", ["QuantitativeLimit", "TestResult", "TestingFrequency"], ["MeasurementUnit"], ["functional"], "Unit of measurement."),
    # Requirement and limit attributes
    "hasMinimumValue": (float, ["QuantitativeLimit"], None, ["functional"], "Inclusive lower bound."),
    "hasMaximumValue": (float, ["QuantitativeLimit"], None, ["functional"], "Inclusive upper bound."),
    "hasExactValue": (float, ["QuantitativeLimit"], None, ["functional"], "Required exact value."),
    "limitIsExclusive": (bool, ["QuantitativeLimit"], None, ["functional"], "True if the stated bounds are exclusive."),
    "normativeStrength": (str, ["Requirement"], None, ["functional"], "'shall', 'should', or 'may' as stated in the source."),
    "requirementText": (str, ["Requirement"], None, ["functional"], "Short statement of the requirement."),
    "conditionText": (str, ["ApplicabilityCondition"], None, ["functional"], "Condition as stated."),
    "applicableClassOrGrade": (str, ["ApplicabilityCondition", "Requirement"], None, [], "Class, grade, or type, e.g. 'Class A'."),
    "frequencyCount": (int, ["TestingFrequency"], None, ["functional"], "Number of tests or samples."),
    "frequencyQuantity": (float, ["TestingFrequency"], None, ["functional"], "Quantity of work covered per frequencyCount."),
    "frequencyQuantityUnit": (str, ["TestingFrequency"], None, ["functional"], "Unit of frequencyQuantity, e.g. 'cu.m'."),
    "curingAgeDays": (int, ["QuantitativeLimit", "Requirement"], None, [], "Age in days at which a limit applies."),
    "unitSymbol": (str, ["MeasurementUnit"], None, ["functional"], "Unit symbol, e.g. 'MPa'."),
    "parameterName": (str, ["QualityParameter"], None, ["functional"], "Parameter name."),
    "standardDesignation": (str, ["TestMethod", "ReferenceStandard"], None, ["functional"], "Designation, e.g. 'AASHTO T 119'."),
    # Compliance verification
    "evaluatesLimit": ("obj", ["TestResult"], ["QuantitativeLimit"], [], "Limit a result is checked against."),
    "hasComplianceOutcome": ("obj", ["TestResult"], ["ComplianceOutcome"], [], "Verdict for a result."),
    "measuredValue": (float, ["TestResult"], None, ["functional"], "Measured value."),
}

WORK_TYPES = ["Highway", "Bridge", "Airport", "Building", "FloodControlAndDrainage"]
OUTCOMES = ["Compliant", "NonCompliant", "InsufficientInformation"]
VOLUMES = [("VolumeII_2013", "II", 2013), ("VolumeIII_2019", "III", 2019)]

RULES = {
    "BelowMinimum": (
        "TestResult(?r), evaluatesLimit(?r, ?l), measuredValue(?r, ?v), "
        "hasMinimumValue(?l, ?m), hasUnit(?r, ?u), hasUnit(?l, ?u), "
        "lessThan(?v, ?m) -> hasComplianceOutcome(?r, NonCompliant)"
    ),
    "AboveMaximum": (
        "TestResult(?r), evaluatesLimit(?r, ?l), measuredValue(?r, ?v), "
        "hasMaximumValue(?l, ?x), hasUnit(?r, ?u), hasUnit(?l, ?u), "
        "greaterThan(?v, ?x) -> hasComplianceOutcome(?r, NonCompliant)"
    ),
}
RULE_COMMENT = (
    "Not Blue Book content: generic comparison of a result against a stated bound. "
    "Compliant is not inferred (open-world); it is decided at retrieval time."
)


def _union(classes):
    result = classes[0]
    for c in classes[1:]:
        result = result | c
    return result


def build():
    with onto:
        classes = {}
        for name, (parent, comment) in CLASSES.items():
            base = Thing if parent == "Thing" else classes[parent]
            cls = types.new_class(name, (base,))
            cls.label = [name]
            if comment:
                cls.comment = [comment]
            classes[name] = cls

        props = {}
        for name, (kind, domain, rng, chars, comment) in PROPERTIES.items():
            base = [ObjectProperty] if kind == "obj" else [DataProperty]
            if "functional" in chars:
                base.append(FunctionalProperty)
            prop = types.new_class(name, tuple(base))
            prop.label = [name]
            prop.comment = [comment]
            if domain:
                dom = [classes[c] for c in domain]
                prop.domain = [_union(dom)]
            prop.range = [classes[c] for c in rng] if kind == "obj" else [kind]
            props[name] = prop

        AllDisjoint([classes[c] for c in DISJOINT_GROUP])

        classes["SubItem"].is_a.append(props["isPartOfItem"].exactly(1, classes["BlueBookItem"]))
        classes["BlueBookItem"].is_a.append(props["belongsToVolume"].exactly(1, classes["Volume"]))

        for vid, roman, year in VOLUMES:
            ind = classes["Volume"](vid)
            ind.volumeNumber = roman
            ind.editionYear = year
            ind.label = [f"DPWH Standard Specifications Volume {roman} ({year})"]
        for wt in WORK_TYPES:
            classes["PublicWorkType"](wt).label = [wt]
        for oc in OUTCOMES:
            classes["ComplianceOutcome"](oc).label = [oc]

    # HermiT rejects SWRL built-in atoms (lessThan, greaterThan), so rules live in a
    # separate ontology that imports the core. Run them from Protege's SWRLTab (Drools engine).
    rules_onto = get_ontology(IRI.rstrip("#") + "-rules#")
    rules_onto.imported_ontologies.append(onto)
    with rules_onto:
        for rname, text in RULES.items():
            rule = Imp(rname)
            rule.set_as_rule(text, namespaces=[onto, rules_onto])
            rule.comment = [RULE_COMMENT]

    onto.metadata.label = ["DPWH Blue Book Quality Compliance Ontology"]
    onto.metadata.comment = [SCOPE_NOTE]
    owl_path = HERE / "dpwh_bluebook.owl"
    onto.save(file=str(owl_path), format="rdfxml")
    rules_path = HERE / "dpwh_bluebook_rules.owl"
    rules_onto.save(file=str(rules_path), format="rdfxml")

    from rdflib import Graph

    Graph().parse(str(owl_path), format="xml").serialize(str(HERE / "dpwh_bluebook.ttl"), format="turtle")
    print(f"Wrote {owl_path} ({len(CLASSES)} classes, {len(PROPERTIES)} properties)")
    print(f"Wrote {rules_path} ({len(RULES)} rules)")


if __name__ == "__main__":
    build()
