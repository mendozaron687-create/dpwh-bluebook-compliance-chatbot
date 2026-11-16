# DPWH Blue Book compliance chatbot (prototype)

The ontology decides; the LLM only fixes grammar.

Pipeline (no n8n): question -> entity extraction -> SPARQL over the ProtÃ©gÃ© ontology (rdflib, `retrieval.py`)
-> the ontology's SWRL rules (`../ontology/dpwh_bluebook_rules.owl`) are run by the Pellet reasoner (full SWRL incl. math built-ins; `reasoner.py`) to check the submitted value against each retrieved limit (`verify.py` prepares the inputs; verdict + citation)
-> `google/gemini-2.5-flash-lite` rewrites the drafted sentence for grammar only (`chat.py`). A rewrite that changes
any number is discarded and the drafted sentence is shown instead. The "LLM-only" mode (no ontology) exists only as the
thesis comparison baseline.

## Setup
- `pip install -r requirements.txt` (`jdk4py` supplies the Java runtime Pellet needs; Protégé's bundled Java 11 is too old).
- Put `OPENROUTER_API_KEY=...` in `chatbot/.env` (git-ignored). Rotate the key if it was ever shared.
- Environment variables: `PRIMARY_MODEL` (default `google/gemini-2.5-flash-lite`), `COMPARISON_MODELS` (comma separated, LLM-only).

## Run
```
cd chatbot
uvicorn app:app --port 8000   # UI at http://localhost:8000: Chat, Provisions (add rows, rebuild ontology), Evaluation
python chat.py                # terminal chat ('!' prefix = LLM-only)
python build_data.py          # data/temp_provisions.csv -> ontology/dpwh_bluebook_data.owl (open in ProtÃ©gÃ©)
python evaluate.py --ragas    # scenarios -> metrics, paired t-test, RAGAS-style scores in results/
```

## Data
`data/temp_provisions.csv` and `data/temp_scenarios.csv` are PLACEHOLDERS in DPWH style. Their values are not verified Blue Book content. Replace them with the adviser-verified encoding (same columns); the 2013 PDF is a scan and needs OCR first.

## Mapping to the thesis
- Objective 1: `ontology/` (schema, data, rules) built and edited in ProtÃ©gÃ©.
- Objective 2: `retrieval.py`, `verify.py`, `chat.py`, `app.py`.
- Objective 3: `evaluate.py --ragas` (faithfulness, answer relevance, context relevance vs Table 3.2).
- Objective 4: `evaluate.py` (accuracy, precision, recall, F1 vs 0.80, response time, paired t-test).


