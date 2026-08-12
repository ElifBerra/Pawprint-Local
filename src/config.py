"""Central configuration for Pawprint-Local.

Every tunable value lives here so experiments during evaluation only touch
one file.
"""

from pathlib import Path

# --- Paths ---------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "data" / "docs"
DB_PATH = ROOT_DIR / "pawprint.db"

# --- Foundry Local -------------------------------------------------------
APP_NAME = "pawprint-local"

# Aliases from the Foundry Local catalog.
# Verify with: python scripts/check_env.py
CHAT_MODEL_ALIAS = "phi-3.5-mini"
EMBEDDING_MODEL_ALIAS = "qwen3-embedding-0.6b"

# --- Chunking ------------------------------------------------------------
# Words, not characters. Tuned during evaluation (see docs/EVALUATION.md).
CHUNK_SIZE = 350
CHUNK_OVERLAP = 50

# --- Retrieval -----------------------------------------------------------
TOP_K = 3

# Cosine similarity below this means "not in our documents" — we skip the
# model entirely and return the fallback message.
SIM_THRESHOLD = 0.35

# --- Generation ----------------------------------------------------------
MAX_TOKENS = 512
TEMPERATURE = 0.2

FALLBACK_ANSWER = "I don't have that information in my documents."

SYSTEM_PROMPT = """You are Pawprint, a pet health assistant.

Answer ONLY using the context below. Do not use outside knowledge.
If the context does not contain the answer, reply with exactly:
"{fallback}"

Never give a diagnosis. For anything urgent or worsening, tell the user to
contact a veterinarian.

Context:
{context}"""
