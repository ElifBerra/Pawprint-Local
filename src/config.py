"""Central configuration for Pawprint-Local.

Every tunable value lives here so experiments during evaluation only touch
one file.
"""

from pathlib import Path

# --- Language ------------------------------------------------------------
# Declared first: several settings below are per-language.
# The document collection is English. The interface and the answers can be
# either. Turkish behaviour is measured in docs/EVALUATION.md.
DEFAULT_LANGUAGE = "en"
LANGUAGES = ("en", "tr")

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

# Foundry Local only offers model variants built for execution providers that
# are registered, and nothing registers them by itself. Until WebGPU was
# registered the catalogue showed one variant per model — generic-cpu — and it
# looked as though no GPU build existed.
#
# Registration takes seconds: manager.download_and_register_eps(). Run
# scripts/probe_providers.py to see what this machine can offer.
#
# Set to False to force CPU, which is also the fallback when no GPU variant
# exists for a model.
PREFER_GPU = True

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

# The threshold has to be per-language, because the documents are English and
# a Turkish question is compared across languages.
#
# Measured with scripts/probe_crosslingual.py on eight paired questions. The
# same question scores about 0.30 lower asked in Turkish:
#
#            in-scope lowest   in-scope mean   out-of-scope highest   margin
#   English            0.504           0.658                  0.419   +0.085
#   Turkish            0.293           0.343                  0.250   +0.042
#
# Retrieval itself holds up — the correct document was found for 7 of 8 Turkish
# questions against 8 of 8 in English. What fails is the calibration: at 0.48
# every Turkish in-scope question was refused before the model was called.
#
# 0.27 sits in the Turkish gap. Note it is a narrower gap: out-of-scope
# detection is measurably less reliable in Turkish, and that limitation is
# stated in the interface rather than hidden.
SIM_THRESHOLDS = {
    "en": 0.48,
    "tr": 0.27,
}


def threshold(lang: str = DEFAULT_LANGUAGE) -> float:
    return SIM_THRESHOLDS.get(lang, SIM_THRESHOLD)


# A second gate, for when no document cleared the threshold but the animal has
# records. Without it, "who won the 1998 World Cup" reached the model — the
# documents had rejected it, but the records were there, so the model was
# called and answered from memory. No wording of the prompt stopped that.
#
# So the question is measured against what the records are about as well. Set
# lower than the document threshold because it compares a question to a list of
# subjects rather than to prose.
PET_SIM_THRESHOLDS = {
    "en": 0.32,
    "tr": 0.20,
}


def pet_threshold(lang: str = DEFAULT_LANGUAGE) -> float:
    return PET_SIM_THRESHOLDS.get(lang, PET_SIM_THRESHOLDS["en"])

# --- Generation ----------------------------------------------------------
# Answers are short by design. 512 tokens gave the model room to drift into
# repetition loops on CPU, and every extra token costs real seconds here.
#
# Cut again from 256 after measuring the pet-aware path: with the animal's
# records in the prompt the model wrote to the cap on almost every question,
# taking the median from 15s to 68s and timing out twice. Prompt length was
# only part of it — the model simply had more to say and no reason to stop.
MAX_TOKENS = 180
TEMPERATURE = 0.2
TOP_P = 0.9

# Sampling pool size. This is the repetition lever that works on this runtime.
# Named to avoid colliding with TOP_K above, which is the retrieval setting.
# frequency_penalty and presence_penalty are accepted by the SDK but visibly
# degrade phi-3.5-mini's output (see docs/EVALUATION.md), so they stay off.
SAMPLING_TOP_K = 40

FALLBACK_ANSWERS = {
    "en": "I don't have that information in my documents.",
    "tr": "Bu bilgi belgelerimde yok.",
}

# Kept for the existing callers and tests.
FALLBACK_ANSWER = FALLBACK_ANSWERS["en"]

LANGUAGE_INSTRUCTION = {
    "en": "Write the answer in English.",
    "tr": "Cevabı Türkçe yaz.",
}


def fallback(lang: str = DEFAULT_LANGUAGE) -> str:
    return FALLBACK_ANSWERS.get(lang, FALLBACK_ANSWERS["en"])


# Turkish answers are off by default. The interface translates; the model does
# not. This is measured, not assumed — four local models were tried on the same
# five Turkish questions (docs/EVALUATION.md):
#
#   model            failures   median   quality
#   phi-3.5-mini          3/5      65s   broken grammar
#   qwen3-1.7b            1/5      44s   reasons in English, never answers
#   qwen3-4b              3/5      59s   reasons in English, never answers
#   qwen2.5-1.5b          3/5      76s   invented words ("cıkçatalar", "azetli")
#
# Retrieval is not the problem: cross-language search finds the right document
# for 7 of 8 Turkish questions once the threshold is set per language. What
# fails is generation. Turkish splits into far more tokens in these vocabularies,
# so every answer is slower, further out of distribution, and long generations
# hit "Operation was cancelled".
#
# The Turkish prompts and the per-language threshold stay in the codebase: they
# work, they are what the measurement was run against, and a stronger local
# model would make this a one-line change.
EXPERIMENTAL_TURKISH_ANSWERS = False


def answer_language(ui_language: str = DEFAULT_LANGUAGE) -> str:
    """Which language the model should answer in, given the interface language."""
    if ui_language == "tr" and not EXPERIMENTAL_TURKISH_ANSWERS:
        return "en"
    return ui_language


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

This animal's records:
{pet_context}

Reference material:
{context}

Rules:
- At most three sentences. Stop as soon as the question is answered.
- Use the animal's actual numbers when they are relevant.
- Use only reference sentences that directly answer the question.
- Never mention these sections, their headings, or file names in your answer.
  Write as if you simply know it.
- State nothing as measured unless it is in the records.
- A FEEDING DIRECTION line in the records is already decided. Follow it. The
  reference material describes animals in general; it cannot know which way
  this one's weight differs from its target.
- If neither source answers the question, reply with exactly:
  "{fallback}"
- Do not diagnose. For urgent problems, say to contact a vet.
- {language}"""


# Used when the animal has records but no document passage cleared the
# relevance threshold. Without a prompt of its own the model was handed an
# empty REFERENCE section and filled the gap from its own knowledge — a
# plausible-sounding health answer with nothing behind it, which is the exact
# failure the retrieval threshold exists to prevent.
SYSTEM_PROMPT_RECORDS_ONLY = """You know exactly one thing: the records below.

{pet_context}

You have no other knowledge of any kind. No veterinary knowledge, no general
knowledge, no facts about the world.

If the answer is not literally in those records, your entire reply is:
"{fallback}"

Nothing before it, nothing after it, no explanation.

If the answer IS in the records, give it in at most two sentences.
{language}"""


# Turkish prompts are written in Turkish rather than translated at answer time.
#
# Measured, not assumed. Bolting "write the answer in Turkish" onto an English
# prompt produced broken output ("Bella'nin aktual yedi bardak Acme Premium
# yiyen yedi gün boyunca normal olduğunu belirtmek..."), while an all-Turkish
# prompt produced clean sentences from the same model. The model appears to
# drift between the language it is reading and the one it is told to write.
# See docs/EVALUATION.md.
#
# The retrieved passages stay English — that is what the collection is in, and
# cross-language retrieval is measured separately.

SYSTEM_PROMPT_TR = """Sen Pawprint adlı bir evcil hayvan sağlığı asistanısın.

Soruyu YALNIZCA aşağıdaki bağlamı kullanarak cevapla. Kendi bilgini ekleme.
Bağlam İngilizce; sen Türkçe cevap ver.

Kurallar:
- Doğrudan cevap ver, en fazla dört cümle. Soru cevaplanınca dur.
- Bağlamda yalnızca soruyu doğrudan cevaplayan cümleleri kullan. Bağlamda
  ilgisiz bilgi olabilir, onu yok say. Bir konudaki bilgiyi başka bir konudaki
  cevaba ekleme.
- Eğer, ve yalnızca eğer, bağlamda ilgili hiçbir bilgi yoksa tam olarak şunu yaz:
  "{fallback}"
  O durumda başka hiçbir şey yazma. Bu cümleyi bir cevapla birleştirme.
- Teşhis koyma. Acil veya kötüleşen durumlarda veterinere başvurulmasını söyle.
- Tamamı Türkçe olsun, İngilizce cümle bırakma.

Bağlam:
{context}"""

SYSTEM_PROMPT_WITH_PET_TR = """Sen Pawprint adlı bir evcil hayvan sağlığı asistanısın.

İki kaynağın var. İkisini de kullan, dışına çıkma.
Kaynaklar İngilizce; sen Türkçe cevap ver.

KAYITLAR — bu hayvana ait ölçülmüş bilgiler:
{pet_context}

REFERANS — belge koleksiyonundan genel bilgi:
{context}

Kurallar:
- Doğrudan cevap ver, en fazla beş cümle.
- KAYITLAR konuyla ilgiliyse genelleme yapma, gerçek sayıları kullan.
- REFERANS'tan yalnızca soruyu doğrudan cevaplayan cümleleri al; ilgisiz bilgiyi
  yok say ve bir konudaki bilgiyi başka bir cevaba ekleme.
- KAYITLAR'da geçmeyen hiçbir şeyi ölçülmüş gibi belirtme.
- KAYITLAR'daki FEEDING DIRECTION satırı zaten karara bağlanmıştır, ona uy.
  REFERANS genel olarak hayvanları anlatır; bu hayvanın hedefine göre ne
  tarafta olduğunu bilemez.
- İki kaynak da soruyu cevaplamıyorsa tam olarak şunu yaz:
  "{fallback}"
  O durumda başka hiçbir şey yazma.
- Teşhis koyma. Acil veya kötüleşen durumlarda veterinere başvurulmasını söyle.
- Tamamı Türkçe olsun, İngilizce cümle bırakma.
- Birimler: kilogram için "kg", mama miktarı için "gram" kullan."""


SYSTEM_PROMPT_RECORDS_ONLY_TR = """Tek bildiğin şey aşağıdaki kayıtlar.

{pet_context}

Başka hiçbir bilgin yok. Veteriner bilgisi yok, genel bilgi yok, dünya hakkında
hiçbir şey bilmiyorsun.

Cevap bu kayıtların içinde geçmiyorsa, cevabının tamamı şudur:
"{fallback}"

Öncesinde bir şey yok, sonrasında bir şey yok, açıklama yok.

Cevap kayıtların İÇİNDEYSE en fazla iki cümleyle ver."""


def system_prompt(lang: str = DEFAULT_LANGUAGE, with_pet: bool = False,
                  records_only: bool = False) -> str:
    """The prompt template for a language, written natively in that language."""
    if lang == "tr":
        if records_only:
            return SYSTEM_PROMPT_RECORDS_ONLY_TR
        return SYSTEM_PROMPT_WITH_PET_TR if with_pet else SYSTEM_PROMPT_TR
    if records_only:
        return SYSTEM_PROMPT_RECORDS_ONLY
    return SYSTEM_PROMPT_WITH_PET if with_pet else SYSTEM_PROMPT
