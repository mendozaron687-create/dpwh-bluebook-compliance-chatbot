"""Paths and model settings. The API key is read from chatbot/.env or the environment."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ONTOLOGY_DIR = ROOT.parent / "ontology"
SCHEMA_OWL = ONTOLOGY_DIR / "dpwh_bluebook.owl"
DATA_OWL = ONTOLOGY_DIR / "dpwh_bluebook_data.owl"
RULES_OWL = ONTOLOGY_DIR / "dpwh_bluebook_rules.owl"
PROVISIONS_CSV = Path(os.getenv("PROVISIONS_CSV", ROOT / "data" / "temp_provisions.csv"))
SCENARIOS_CSV = Path(os.getenv("SCENARIOS_CSV", ROOT / "data" / "temp_scenarios.csv"))
RESULTS_DIR = ROOT / "results"


def _load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"

PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "google/gemini-2.5-flash-lite")
# Models answering without the ontology. Defaults to the primary model as an LLM-only baseline;
# add the thesis comparison models here, e.g. "openai/gpt-5.5,google/gemini-3.1-pro-preview".
COMPARISON_MODELS = [m for m in os.getenv("COMPARISON_MODELS", PRIMARY_MODEL).split(",") if m]
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")

# Table 3.2 and 3.3 thresholds
RAGAS_THRESHOLDS = {"answer_relevance": 0.78, "faithfulness": 0.95, "context_relevance": 0.70}
CLASSIFICATION_THRESHOLD = 0.80
