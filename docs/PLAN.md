# Pawprint-Local — 5 Günlük Plan

**Teslim:** 17 Ağustos · **Ana makine:** Windows · **UI:** CLI → son gün Streamlit
**Kural:** Her günün sonunda çalışan bir şey olacak. Hiçbir gün yarım özellikle kapanmayacak.

---

## SDK notu (önemli)

Microsoft Learn'deki `from foundry_local import FoundryLocalManager` örnekleri **legacy SDK**'ya ait.
Kurulu olan `foundry-local-sdk==1.2.4` farklı bir API kullanıyor. Doğrusu:

```python
from foundry_local_sdk import Configuration, FoundryLocalManager
from foundry_local_sdk.logging_helper import LogLevel

FoundryLocalManager.initialize(Configuration(app_name="pawprint-local", log_level=LogLevel.WARNING))
manager = FoundryLocalManager.instance          # singleton — ikinci kez initialize edilemez

model = manager.catalog.get_model("phi-3.5-mini")   # None dönebilir
model.download(progress_callback=fn)                # cache'te yoksa
model.load()

chat = model.get_chat_client()
chat.settings.max_tokens = 512
chat.settings.temperature = 0.2
resp = chat.complete_chat([{"role": "system", ...}, {"role": "user", ...}])
resp.choices[0].message.content

emb = model.get_embedding_client()
resp = emb.generate_embeddings(["metin1", "metin2"])   # batch
resp.data[i].embedding                                 # list[float]

model.unload()
```

Diğer faydalı çağrılar: `manager.catalog.list_models()`, `get_cached_models()`,
`manager.discover_eps()`, `manager.download_and_register_eps()`,
`chat.complete_streaming_chat(messages)`.

`foundry_local_core` paketi native DLL'i (23 MB) kendi içinde taşıyor — yani
`winget install Microsoft.FoundryLocal` **zorunlu değil**, sadece `foundry` CLI aracını verir.
SDK tek başına yeterli.

**Singleton tuzağı:** `FoundryLocalManager.initialize()` ikinci kez çağrılırsa exception atar.
Streamlit'te `@st.cache_resource` ile sarmalamak şart, yoksa her rerun'da patlar.

---

## Gün 0 — 12 Ağustos, bu akşam ✅ büyük ölçüde bitti

- [x] venv (Python 3.12.10) + paketler
- [x] `scripts/check_env.py` — teşhis aracı
- [x] `scripts/hello_pet.py` — smoke test, doğru API ile
- [ ] `hello_pet.py` başarıyla cevap döndürüyor
- [ ] Katalogdan chat + embedding model alias'ları doğrulandı

**Kabul kriteri:** `python scripts\hello_pet.py` yerel modelden bir cümle yazdırıyor.

---

## Gün 1 — 13 Ağustos Perşembe · Veri katmanı

**Hedef:** Belgeler → chunk → embedding → SQLite.

### Sabah

- **Bilgi tabanı:** `data/docs/` altına 6–10 kısa evcil hayvan sağlığı belgesi (.md).
  Aşı takvimi, sık görülen semptomlar, beslenme, acil durum işaretleri, ilaç dozları, bakım rutinleri.
  Tek dil seç, karıştırma. Belge seçmeye 20 dakikadan fazla harcama — pipeline önemli, içerik değil.
- **`src/config.py`** — model alias'ları, DB yolu, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `SIM_THRESHOLD`.
- **`src/chunking.py`** — paragraf sınırından böl, ~300–500 kelime, %10–15 overlap.
  Her chunk'a `source` ve `chunk_index` iliştir.
- **`src/db.py`** — şema:
  ```sql
  CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL,      -- np.float32 .tobytes()
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX idx_source ON chunks(source);
  ```
  Embedding'i JSON değil **BLOB** sakla (`np.frombuffer` ile oku). Hem hızlı hem küçük.

### Öğleden sonra

- **`src/foundry.py`** — SDK'yı tek yerde sarmala: manager'ı bir kez initialize eden, chat ve
  embedding client'ı döndüren modül. Singleton problemini burada çöz. Diğer tüm modüller
  SDK'yı doğrudan import etmesin — yedek plana geçmek gerekirse tek dosya değişir.
- **`src/embeddings.py`** — `embed_texts(list[str]) -> np.ndarray`. `generate_embeddings()` ile
  10–20'lik batch'ler halinde.
- **`src/ingest.py`** — `python -m src.ingest [--rebuild]`. `data/docs/` tara → chunk'la → embed et → yaz.
- **Doğrula:** `sqlite3 pawprint.db "SELECT COUNT(*), COUNT(DISTINCT source) FROM chunks;"`

**Kabul kriteri:** Ingest sıfırdan çalışıyor, tekrar çalıştırınca duplicate oluşmuyor.

---

## Gün 2 — 14 Ağustos Cuma · Uçtan uca ilk cevap ⚠️ en kritik gün

### Sabah

- **`src/retrieve.py`** — `get_top_chunks(query, k=3)`:
  sorguyu embed et → tüm vektörleri çek (`np.vstack`) → normalize edip tek `matmul` ile
  cosine similarity (döngü yazma) → top-K'yı skorlarıyla döndür.
- **Elle test:** Cevabının hangi belgede olduğunu bildiğin 5 soru sor. Doğru chunk gelmiyorsa
  chunk boyutunu ayarla. Buraya 1 saat harcamaya değer — sonraki her şeyin kalitesini bu belirliyor.

### Öğleden sonra

- **`src/llm.py`** — `chat(system, user) -> str`, `foundry.py` üzerinden.
- **`src/rag.py`** — `answer(question) -> Answer(text, sources, latency)`. Retrieve → prompt → generate.
- İlk system prompt (kaba olsun, yarın cilalanacak):
  ```
  You are a pet health assistant. Answer ONLY using the context below.
  If the context does not contain the answer, say exactly:
  "I don't have that information in my documents."
  Never give a diagnosis. Recommend seeing a veterinarian for anything urgent.
  Context:
  {chunks}
  ```
- **`src/cli.py`** — input döngüsü, `/exit`.

**Kabul kriteri:** `python -m src.cli` → soru → kaynak gösteren cevap. Güzel olması gerekmiyor, **çalışması** gerekiyor.

> Gün sonunda uçtan uca cevap alamadıysan Gün 3'ün sabahını buna ayır ve Streamlit'i plandan çıkar.

---

## Gün 3 — 15 Ağustos Cumartesi · Kalite ve sağlamlık

### Sabah — Prompt

- En az 3 system prompt varyantı dene, aynı 5 soruyu her birinde çalıştır,
  sonuçları `docs/prompt-iterations.md`'ye **o anda** yaz. Rapordaki "design decisions"
  bölümünün hammaddesi bu — sonradan hatırlamaya çalışma.
- **Kaynak gösterimi:** cevabın altına `Sources: dosya1.md, dosya3.md`. Prompt'a güvenme, kodda ekle.
- **"Bilmiyorum" testi:** belgelerde olmayan 5 soru. Uyduruyorsa top-K'yı düşür, prompt'taki kısıtı sertleştir.
- **Similarity eşiği:** en iyi skor eşiğin (örn. 0.35) altındaysa modele hiç gitme, direkt fallback dön.
- **Sağlık uyarısı:** veteriner tavsiyesi yerine geçmediğini belirten bir not her cevaba eklensin.
  Konu evcil hayvan sağlığı — bu hem doğru davranış hem sunumda artı puan.

### Öğleden sonra — Sağlamlaştırma

- Boş girdi, tek karakter, çok uzun soru, boş DB — hiçbiri çökmesin.
- Latency ölç, CLI'da `[2.1s]` göster.
- CLI komutları: `/sources`, `/reset`, `/help`.
- Sorgu embedding cache'i.
- `print` → `logging`.

---

## Gün 4 — 16 Ağustos Pazar · Test, ölçüm, dokümantasyon

### Sabah

- **`tests/test_chunking.py`, `tests/test_retrieve.py`** — 8–10 anlamlı pytest testi.
  Retrieval testinde küçük sahte DB kur.
- **`tests/eval_questions.json`** — 20 soru: 14 cevaplanabilir + 6 cevaplanamaz, her biri için beklenen kaynak.
- **`tests/run_eval.py`** — tabloyu üret:

  | metrik | değer |
  |---|---|
  | Retrieval accuracy (doğru kaynak top-3'te) | ?/14 |
  | Doğru "bilmiyorum" | ?/6 |
  | Ortalama latency | ?s |
  | p95 latency | ?s |

- Sonuçları `docs/EVALUATION.md`'ye yaz. **Kötü sonuçları da yaz.**
  "Chunk boyutunu 500'den 300'e düşürünce retrieval 9/14'ten 12/14'e çıktı" — projenin en değerli cümlesi bu.

### Öğleden sonra

- **README.md:** ne yapar, mimari, sıfırdan kurulum (kopyala-yapıştır çalışacak şekilde), kullanım, limitasyonlar.
- **docs/ARCHITECTURE.md:** veri akışı, şema, neden SQLite, neden brute-force similarity, ölçeklenince ne değişir.
- **docs/REPORT.md:** problem, yaklaşım, tasarım kararları, değerlendirme, çıkarılan dersler.

**Kabul kriteri:** `pytest` yeşil. Repoyu başka klasöre klonla, README'yi harfiyen takip et, çalışsın.

---

## Gün 5 — 17 Ağustos Pazartesi · Teslim

### Sabah — Streamlit

`src/app.py`, sadece `rag.answer()` sarmalar, **yeni mantık yok**:
soru girişi · cevap · `st.expander` içinde kaynak chunk'lar (demoda RAG'ın çalıştığını gösteren şey bu) ·
yan panelde top-K kaydırıcısı, latency, chunk sayısı · `@st.cache_resource` ile model yükleme.

> Saat 12:00'de Streamlit çalışmıyorsa **bırak**. CLI ile teslim et, README'de "future work" yaz.

### Öğleden sonra

- **Demo senaryosu — 4 soru, bu sırayla:**
  1. Tek belgeden cevaplanan basit soru
  2. İki belgeden bilgi birleştiren
  3. Belgelerde olmayan → "bilmiyorum" (en etkileyici olanı)
  4. Kaynak gösterimini vurgulayan

  İki kez prova et. İlk sorguda model yükleme gecikmesi var — demodan önce bir kez ısıt.
- Sunum: problem → mimari → demo → değerlendirme → dersler. 6–8 slayt.
- Temizlik: `pawprint.db` ve `venv/` repoda olmasın, `pip freeze > requirements.txt`, `git tag v1.0`.

---

## Genel kurallar

**Düşerse bunlar düşecek:** vektör DB eklentisi, multi-turn hafıza, model karşılaştırması,
PDF parsing, async, Docker. Hiçbiri teslim için gerekli değil.

**Her gün 21:00:** günün işi commit'lenip push'lanmış olacak. Yarım iş branch'te kalsın, `main` her zaman çalışsın.

**30 dakika kuralı:** bir hataya 30 dakikadan fazla takıldıysan geçici çözümle devam et,
`docs/KNOWN_ISSUES.md`'ye yaz, Gün 4'te dön.

**Yedek plan:** Foundry Local bir noktada çökerse `src/foundry.py` arkasındaki arayüzü
Ollama veya sentence-transformers ile doldur. Bu yüzden o dosya ince ve tek sorumluluklu olmalı.
