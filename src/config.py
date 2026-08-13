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
#
# Set from the 23-question evaluation, which separates cleanly:
#   answerable    0.548 .. 0.785
#   unanswerable  0.165 .. 0.427
# 0.48 sits in the gap with roughly equal margin on both sides. At the previous
# 0.40 the three in-domain-but-uncovered questions (puppy training, breed
# choice, neutering cost) scored 0.411-0.427 and reached the model, which
# declined correctly but only by its own judgement — and cost 15 seconds each.
SIM_THRESHOLD = 0.48

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

# --- Language ------------------------------------------------------------
# The document collection is English. The interface and the answers can be
# either. Turkish answer quality is measured in docs/EVALUATION.md.
DEFAULT_LANGUAGE = "en"
LANGUAGES = ("en", "tr")

FALLBACK_ANSWERS = {
    "en": "I don't have that information in my documents.",
    "tr": "Bu bilgi belgelerimde yok.",
}

# Kept for the existing callers and tests.
FALLBACK_ANSWER = FALLBACK_ANSWERS["en"]

LANGUAGE_INSTRUCTION = {
    "en": "Write the answer in English.",
    "tr": (
        "Cevabı Türkçe yaz. Kaynak belgeler İngilizce; bilgiyi Türkçeye çevirerek "
        "aktar, İngilizce cümle bırakma."
    ),
}


def fallback(lang: str = DEFAULT_LANGUAGE) -> str:
    return FALLBACK_ANSWERS.get(lang, FALLBACK_ANSWERS["en"])


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
- {language}

Context:
{context}"""

# Used when the question is about an animal we hold records for. The two
# sources are labelled and kept apart so the model does not attribute a
# general guideline to this specific animal, or the reverse.
SYSTEM_PROMPT_WITH_PET = """You are Pawprint, a pet health assistant.

You have two sources. Use both. Do not add anything from outside them.

RECORDS — measured facts about this specific animal:
{pet_context}

REFERENCE — general guidance from the document collection:
{context}

Rules:
- Answer directly in at most five sentences.
- When RECORDS are relevant, quote the actual numbers rather than generalising.
- From REFERENCE use only sentences that directly answer the question; ignore
  unrelated material and never join a fact from one topic onto another.
- Do not state anything as measured unless it appears in RECORDS.
- If neither source answers the question, reply with exactly:
  "{fallback}"
  Say nothing else in that case.
- Do not diagnose. For urgent or worsening problems, say to contact a vet.
- {language}"""
