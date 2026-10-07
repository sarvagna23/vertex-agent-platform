"""Central config. Every value comes from an environment variable (see .env.example)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional, env vars can come from the shell or Cloud Run
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")

# --- Google Cloud ---
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")  # Vertex AI region
BQ_LOCATION = os.environ.get("BQ_LOCATION", "US")  # must match the public dataset (US)
BQ_DATASET = os.environ.get("BQ_DATASET", "complaints")

# --- Table and model names inside the dataset ---
RAW_TABLE = "complaints_raw"
EMBEDDINGS_TABLE = "complaint_embeddings"
EMBEDDING_MODEL = "embedding_model"

# --- LLM ---
# Check the current Gemini model names in the Vertex AI docs before you run.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# --- Guardrails for the SQL tool ---
MAX_SQL_ROWS = int(os.environ.get("MAX_SQL_ROWS", "50"))
MAX_BYTES_BILLED = int(os.environ.get("MAX_BYTES_BILLED", str(1024**3)))  # 1 GB cap per query

# --- PII ---
USE_DLP = os.environ.get("USE_DLP", "false").lower() == "true"

# ADK reads these to route Gemini calls through Vertex AI instead of the public API.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
if PROJECT_ID:
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)


def fq(name: str) -> str:
    """Fully qualified BigQuery name for something in our dataset, e.g. proj.complaints.complaints_raw."""
    return f"{PROJECT_ID}.{BQ_DATASET}.{name}"
