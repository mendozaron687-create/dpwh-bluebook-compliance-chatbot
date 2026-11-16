# DPWH Blue Book Compliance Chatbot

Ontology-based decision-support prototype for verifying compliance with the DPWH Standard Specifications
(Blue Book). The **ontology decides**: the OWL 2 DL model holds the encoded provisions and their limits, and
the SWRL rules (run with the Pellet reasoner) flag violations. The large language model (`google/gemini-2.5-flash-lite`
via OpenRouter) is used **only to polish the grammar** of the drafted answer.

> Prototype status: the encoded provisions in `chatbot/data/` are placeholders in DPWH style. Their values are
> not verified Blue Book content and must not be cited.

## Run it on another PC

Requires Python 3.10+ and Git.

```powershell
git clone https://github.com/mendozaron687-create/dpwh-bluebook-compliance-chatbot.git
cd dpwh-bluebook-compliance-chatbot\chatbot
pip install -r requirements.txt
```

Create `chatbot\.env` with your own OpenRouter key (an existing key was used in development and should be rotated):

```
OPENROUTER_API_KEY=sk-or-v1-...
```

Then:

```powershell
python chat.py                 # terminal chat
python -m uvicorn app:app --port 8000   # web UI at http://localhost:8000
python test_swrl.py            # SWRL/Pellet checks (no API key needed)
python test_flexible.py        # loose-phrasing checks (no API key needed)
python evaluate.py --ragas     # full evaluation, writes chatbot/results/
```

`jdk4py` (in `requirements.txt`) supplies a Java runtime for Pellet; Protégé's bundled Java 11 is too old.

## Layout

| Path | Contents |
|---|---|
| `ontology/dpwh_bluebook.owl` | Schema: classes, properties, provenance (Volume/Item/SubItem), disjointness |
| `ontology/dpwh_bluebook_data.owl` | Encoded provisions (built from `chatbot/data/temp_provisions.csv`) |
| `ontology/dpwh_bluebook_rules.owl` | SWRL rules `BelowMinimum` and `AboveMaximum` |
| `ontology/dpwh_bluebook_rules_demo.owl` | Synthetic test results showing the rules fire |
| `chatbot/retrieval.py` | SPARQL retrieval + forgiving entity matching |
| `chatbot/reasoner.py` | Pellet SWRL reasoning (runtime decision engine) |
| `chatbot/verify.py` | Selects applicable limits, runs the rules, drafts the answer |
| `chatbot/app.py` | Web UI: chat with decision trace, provisions editor, evaluation runner |

See [chatbot/README.md](chatbot/README.md) for details, and `ontology/*.png` for Protégé/HermiT/SWRLTab evidence.

## Not included

- The 2013 Blue Book PDF (240 MB, over GitHub's file limit; it is also a scan that needs OCR).
- Thesis drafts.
- The Protégé application bundle (download from the Protégé site).
- `chatbot/.env` (API key) and generated `chatbot/results/`.
