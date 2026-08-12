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
CHUNK_SIZE = 200
CHUNK_OVERLAP = 30

# --- Retrieval -----------------------------------------------------------
# How many chunks go into the prompt. Directly sets context length, which is
# the dominant cost on CPU. Raised back to 3 after heading-aware chunking made
# chunks small enough that 2 no longer covered a topic: "why does my dog have
# bad breath" matched the Breathing section of the emergency document and lost
# the dental one.
TOP_K = 3

# Cosine similarity below this means "not in our documents" — we skip the
# model entirely and return the fallback message.
# Smaller chunks carrying heading trails raised baseline similarity, so an
# out-of-scope question reached 0.275. Lowest in-scope score is 0.504, so 0.40
# sits between them with room on both sides.
SIM_THRESHOLD = 0.40

# --- Generation ----------------------------------------------------------
# Answers are short by design. 512 tokens gave the model room to drift into
# repetition loops on CPU, and every extra token costs real seconds here.
MAX_TOKENS = 256
TEMPERATURE = 0.2
TOP_P = 0.9

# Sampling pool size. This is the repetition lever that works on this runtime.
# Named to avoid colliding with TOP_K above, which is the retrieval setting.
# frequency_penalty and presence_penalty are accepted by the SDK but visibly
# degrade phi-3.5-mini's output (see docs/EVALUATION.md), so they stay off.
SAMPLING_TOP_K = 40

FALLBACK_ANSWER = "I don't have that information in my documents."

SYSTEM_PROMPT = """You are Pawprint, a pet health assistant.

Answer the question using ONLY the context below. Do not add outside knowledge.

Rules:
- Answer directly in at most four sentences. Stop when the question is answered.
- Use only the sentences in the context that directly answer the question. The
  context may contain unrelated material; ignore it. Never join a fact from one
  topic onto an answer about another.
- If, and only if, the context contains nothing relevant, reply with exactly:
  "{fallback}"
  Say nothing else in that case. Never combine that sentence with an answer.
- Do not diagnose. For urgent or worsening problems, say to contact a vet.

Context:
{context}"""
