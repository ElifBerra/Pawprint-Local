# Mimari

Pawprint-Local, tamamen çevrimdışı çalışan bir evcil hayvan sağlığı asistanı.
İki bilgi kaynağını birleştiriyor: genel bir belge koleksiyonu ve tek bir
hayvanın kendi kayıtları. Hiçbir veri cihazdan çıkmıyor, hiçbir API anahtarı
yok, ağ kapalıyken de çalışıyor.

---

## 1. Sistem görünümü

```
┌──────────────────────────────────────────────────────────────────────┐
│                    KULLANICININ BİLGİSAYARI (%100 çevrimdışı)        │
│                                                                      │
│   ┌────────────────────────┐        ┌──────────────────────────┐     │
│   │  Tarayıcı (localhost)  │◄──────►│  FastAPI  (src/api.py)   │     │
│   │  web/ — HTML/CSS/JS    │  HTTP  │  + statik dosya sunumu   │     │
│   │  çerçeve yok, CDN yok  │  NDJSON│                          │     │
│   └────────────────────────┘        └────────────┬─────────────┘     │
│                                                  │                   │
│   ┌────────────────────────┐                     │                   │
│   │  CLI  (src/cli.py)     │─────────────────────┤                   │
│   │  Streamlit (app.py)    │                     │                   │
│   └────────────────────────┘                     │                   │
│                                                  ▼                   │
│   ┌──────────────────────────────────────────────────────────────┐   │
│   │                     UYGULAMA KATMANI                         │   │
│   │                                                              │   │
│   │   ┌──────────────┐   ┌──────────────┐   ┌────────────────┐   │   │
│   │   │  rag.py      │   │ insights.py  │   │  report.py     │   │   │
│   │   │  RAG hattı   │   │ kural motoru │   │  vet raporu    │   │   │
│   │   └──────┬───────┘   └──────┬───────┘   └───────┬────────┘   │   │
│   │          │                  │                   │            │   │
│   │   ┌──────▼───────┐   ┌──────▼─────────────────  ▼────────┐   │   │
│   │   │ retrieve.py  │   │  pet_context.py                   │   │   │
│   │   │ vektör arama │   │  kayıtları prompt metnine çevirir │   │   │
│   │   └──────┬───────┘   └──────┬────────────────────────────┘   │   │
│   │          │                  │                                │   │
│   │   ┌──────▼───────┐   ┌──────▼───────┐                        │   │
│   │   │embeddings.py │   │   llm.py     │                        │   │
│   │   └──────┬───────┘   └──────┬───────┘                        │   │
│   │          └────────┬─────────┘                                │   │
│   │              ┌────▼──────────┐                               │   │
│   │              │  foundry.py   │  SDK ile tek temas noktası    │   │
│   │              └────┬──────────┘                               │   │
│   └───────────────────┼──────────────────────────────────────────┘   │
│                       │                                              │
│        ┌──────────────┴───────────┐          ┌────────────────────┐  │
│        ▼                          ▼          ▼                    │  │
│   ┌─────────────────┐   ┌──────────────────────────────┐          │  │
│   │  SQLite         │   │  Microsoft Foundry Local     │          │  │
│   │  pawprint.db    │   │  ┌────────────────────────┐  │          │  │
│   │                 │   │  │ phi-3.5-mini (sohbet)  │  │          │  │
│   │ • chunks        │   │  ├────────────────────────┤  │          │  │
│   │ • pets          │   │  │ qwen3-embedding-0.6b   │  │          │  │
│   │ • weight_rec.   │   │  │ (1024 boyut)           │  │          │  │
│   │ • feeding_rec.  │   │  └────────────────────────┘  │          │  │
│   │ • stool_rec.    │   │  ONNX Runtime · CPU          │          │  │
│   └─────────────────┘   └──────────────────────────────┘          │  │
│                                                                   │  │
│   ✓ İnternet gerekmiyor   ✓ API anahtarı yok   ✓ Bulut yok        │  │
└───────────────────────────────────────────────────────────────────┴──┘
```

---

## 2. İki bilgi kaynağı

Projeyi bir belge arama kutusundan ayıran şey bu ayrım.

```
  GENEL BİLGİ                             BU HAYVANA ÖZEL
  data/docs/*.md                          SQLite kayıtları
  ────────────────                        ─────────────────
  "Yetişkin köpekler günde                "Bella 30.2 kg, hedef 28.0,
   iki öğün yer"                           2.5 bardak Acme Premium,
  "Çikolata teobromin içerir"              önerilen 2.0"
        │                                        │
        │ chunk'lanır, embed edilir              │ kural motorundan geçer
        │ vektör aramayla çekilir                │ metne dönüştürülür
        ▼                                        ▼
  ┌──────────────────────────────────────────────────────┐
  │              PROMPT (iki kaynak etiketli)            │
  │                                                      │
  │   RECORDS — bu hayvana ait ölçülmüş bilgiler         │
  │   REFERENCE — belge koleksiyonundan genel bilgi      │
  └──────────────────────────┬───────────────────────────┘
                             ▼
                   phi-3.5-mini (yerel)
                             ▼
   "Bella'nın porsiyonu 2.5 bardak, Acme Premium için
    önerilen 2.0. Son 3 haftada 0.8 kg almış. Kademeli
    azaltma ve haftalık tartım öneriliyor."
```

İki kaynak prompt'ta **ayrı etiketlerle** duruyor. Sebebi: model genel bir
kılavuzu bu hayvana ait ölçülmüş bir veriymiş gibi sunmasın. Prompt'ta açık
kural var: *"KAYITLAR'da geçmeyen hiçbir şeyi ölçülmüş gibi belirtme."*

---

## 3. RAG hattı

```
  Kullanıcı sorusu
        │
        ▼
  ┌─────────────────────────────────────────────┐
  │ 1. RETRIEVE                                 │
  │    embeddings.embed_one(soru)               │
  │    → 1024 boyutlu vektör                    │
  │                                             │
  │    retrieve.rank()                          │
  │    → tüm chunk'lar SQLite'tan okunur        │
  │    → L2 normalize + tek matmul              │
  │    → cosine similarity, en iyi 3            │
  └──────────────────┬──────────────────────────┘
                     │
              en yüksek skor ≥ eşik?
              (EN: 0.48 · TR: 0.27)
                     │
         ┌───────────┴────────────┐
      hayır                      evet
         │                        │
         ▼                        ▼
  ┌──────────────┐   ┌──────────────────────────────┐
  │ "Bu bilgi    │   │ 2. AUGMENT                   │
  │  belgelerimde│   │    prompt = sistem talimatı  │
  │  yok."       │   │           + KAYITLAR         │
  │              │   │           + REFERANS         │
  │ 0.5 saniye   │   │           + soru             │
  │ model hiç    │   └──────────────┬───────────────┘
  │ çağrılmaz    │                  ▼
  └──────────────┘   ┌──────────────────────────────┐
                     │ 3. GENERATE                  │
                     │    phi-3.5-mini, streaming   │
                     │    max 256 token             │
                     └──────────────┬───────────────┘
                                    ▼
                         Cevap + kaynak dosya adları
                         + kullanılan pasajlar (skorlarıyla)
```

**Eşik neden var.** Kapsam dışı soru modele hiç gitmiyor: hem doğru sonuç
(model uydurma şansı bulamıyor) hem hızlı (15 saniye yerine 0.5 saniye).
Eşik değerleri 23 soruluk değerlendirmeden ölçüldü, tahmin değil.

**Eşik neden dile göre farklı.** Koleksiyon İngilizce. Türkçe soru çapraz dilde
eşleşiyor ve aynı anlamdaki soru ~0.30 daha düşük skor alıyor. Tek eşik
kullanılırken Türkçe soruların 8/8'i haksız yere reddediliyordu.

---

## 4. Kural motoru — neden modele yazdırılmıyor

```
   Kayıtlar (SQLite)
        │
        ▼
  ┌────────────────────────────────────────────────┐
  │  insights.py — saf Python, model yok           │
  │                                                │
  │  • veri kalitesi   (ardışık tartımda %25+ fark)│
  │  • kilo artışı     (+ mama değişikliği ile     │
  │                     zaman örtüşmesi)           │
  │  • kilo kaybı      (vücut ağırlığının %5'i →   │
  │                     uyarı, veterinere yönlendir)│
  │  • porsiyon        (etiket kılavuzuyla fark)   │
  │  • hedef kilo      (üstünde / altında)         │
  │  • dışkı kalitesi  (30 günlük normal oranı)    │
  │  • eksik veri      (neyin değerlendirilemediği)│
  └────────────────────┬───────────────────────────┘
                       ▼
        Insight(level, title_tr, title_en,
                detail_tr, detail_en)
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   İçgörüler ekranı  Vet raporu   Prompt'a KAYITLAR
```

Bu bilinçli bir karar. Bu bulgular kullanıcının aksiyon alacağı uyarılar
üretiyor — *"porsiyonu azalt"*, *"veterinere göster"*. Böyle bir çıktının her
açılışta aynı olması gerekiyor. CPU'da çalışan 3 milyar parametreli bir model
bunu garanti edemez.

**İş bölümü:** aritmetiği kural yapar, model sadece cümle kurar.

İkinci bir faydası sonradan ortaya çıktı: bu katman modele bağlı olmadığı için
**Türkçesi kusursuz.** Modelin Türkçe üretemediğini ölçtükten sonra da içgörüler
ve vet raporu tamamen Türkçe kalabildi.

---

## 5. Veri modeli (SQLite)

Tek dosya: `pawprint.db`. İki bağımsız alan, aralarında join yok.

```
  BELGE KOLEKSİYONU                    HAYVAN KAYITLARI
  (ingest --rebuild ile yenilenir)     (kalıcı, kullanıcıya ait)

  ┌───────────────────────────┐        ┌──────────────────────────┐
  │ chunks                    │        │ pets                     │
  │───────────────────────────│        │──────────────────────────│
  │ id            INTEGER PK  │        │ id           INTEGER PK  │
  │ source        TEXT        │        │ name         TEXT        │
  │ chunk_index   INTEGER     │        │ species      TEXT        │
  │ content       TEXT        │        │ breed        TEXT        │
  │ embedding     BLOB ◄──────┼─┐      │ birth_date   TEXT        │
  │ created_at    TEXT        │ │      │ sex          TEXT        │
  │ UNIQUE(source,chunk_index)│ │      │ target_weight_kg REAL    │
  └───────────────────────────┘ │      │ owner_name   TEXT        │
                                │      └───────────┬──────────────┘
   float32 dizisi .tobytes()    │                  │ 1
   ile saklanır — JSON'dan      │                  │
   ~4 kat küçük ve okurken      │        ┌─────────┴──────────┐
   ayrıştırma yok. Retrieval    │        │ N                  │
   her soruda tabloyu tümüyle   │   ┌────▼──────────┐  ┌──────▼─────────┐
   okuduğu için bu fark önemli. │   │ weight_records│  │ feeding_records│
                                │   │───────────────│  │────────────────│
                                │   │ pet_id     FK │  │ pet_id      FK │
                                │   │ recorded_on   │  │ recorded_on    │
                                │   │ weight_kg     │  │ food_brand     │
                                │   │ UNIQUE(pet,   │  │ portion_cups   │
                                │   │        date)  │  │ meals_per_day  │
                                │   └───────────────┘  │ note           │
                                │                      └────────────────┘
                                │   ┌───────────────┐
                                │   │ stool_records │
                                │   │───────────────│
                                │   │ pet_id     FK │
                                │   │ recorded_on   │
                                │   │ quality       │
                                │   │ frequency     │
                                │   └───────────────┘
```

**İki alan neden ayrı.** Belge koleksiyonu `ingest --rebuild` ile silinip
yeniden kurulabilir; hayvan kayıtları kullanıcının verisi ve o işlemden
etkilenmemeli. Bu yüzden `db.py` (chunk'lar) ve `pets_db.py` (kayıtlar) ayrı
modüller, aynı bağlantıyı paylaşıyorlar ama şemaları bağımsız.

**Vektör araması neden SQL'de değil.** 44 chunk için tüm embedding'leri belleğe
alıp tek `matmul` yapmak bir milisaniyenin altında sürüyor. Vektör indeksi
(sqlite-vec vb.) bu ölçekte gereksiz karmaşıklık. Bu yaklaşım yaklaşık 10.000
chunk'a kadar taşır; ötesinde ANN indeksi gerekir.

---

## 6. Modül haritası

```
src/
├── config.py        Tüm ayarlar tek yerde. Dile göre eşikler, promptlar.
├── foundry.py       SDK ile TEK temas noktası. Singleton koruması, lazy
│                    yükleme, model cache. Yerel model değişirse burası değişir.
├── models.py        Ortak veri tipleri: Chunk, Retrieved, Answer, Pet,
│                    WeightRecord, FeedingRecord, StoolRecord, Insight
│
├── chunking.py      Başlık sınırlı bölme + başlık izi
├── embeddings.py    Metin → vektör, batch'li, L2 normalize
├── db.py            chunks tablosu
├── ingest.py        belgeler → chunk → embedding → SQLite
│
├── retrieve.py      Cosine similarity, top-K, alaka eşiği
├── llm.py           Sohbet istemcisi sarmalayıcı, streaming, <think> filtresi
├── rag.py           Hat: retrieve → augment → generate
├── pet_context.py   Kayıtları prompt metnine çevirir
│
├── pets_db.py       pets + kayıt tabloları
├── insights.py      Kural motoru
├── report.py        Vet raporu (veri + PDF)
│
├── api.py           FastAPI uçları
├── serve.py         Sunucu başlatıcı
├── cli.py           Terminal arayüzü
└── app.py           Streamlit (minimal alternatif)
```

**`foundry.py` neden var.** SDK'nın `FoundryLocalManager`'ı süreç genelinde
singleton; ikinci kez `initialize()` çağrılırsa hata veriyor. Streamlit her
etkileşimde script'i yeniden çalıştırdığı için bu korumanın merkezi bir yerde
olması şart. İkinci sebep: yerel çalışma zamanı değiştirilecekse (Ollama,
sentence-transformers) sadece bu dosya değişiyor.

---

## 7. Programın istediği teknolojiler nerede

| Beklenti | Nerede | Nasıl doğrulanır |
|---|---|---|
| Foundry Local ile çevrimdışı çıkarım | `src/foundry.py`, `src/llm.py` | `python scripts/check_env.py` |
| RAG (retrieve → augment → generate) | `src/rag.py` | `docs/eval-results.md` |
| Belge koleksiyonu | `data/docs/` — 6 belge, 44 chunk | `python -m src.ingest` |
| Embedding | `src/embeddings.py` — qwen3-embedding-0.6b, 1024 boyut | `python -m scripts.test_embeddings` |
| Vektör arama | `src/retrieve.py` — cosine similarity | `pytest tests/test_retrieve.py` |
| SQLite | `src/db.py`, `src/pets_db.py` | `pawprint.db` |
| Prompt mühendisliği | `src/config.py` — TR/EN, tek ve iki kaynaklı şablonlar | `docs/EVALUATION.md` |
| Soru-Cevap arayüzü | `web/`, `src/cli.py` | `python -m src.serve` |
| Tamamen çevrimdışı | Her yerde — CDN bile yok | Ağı kapatıp çalıştır |

---

## 8. Orijinal tasarımdan sapma

İlk planda **her sağlık kaydının embed edilip vektör aramayla "benzer geçmiş
dönemlerin" bulunması** vardı. Uygulanmadı. Gerekçe:

Sayısal kayıtları metne çevirip ("kilo 30.2 kg, Acme Premium, 2.5 bardak")
cosine benzerliğine bakmak, benzerliği **şablon kelimelere** bağlar; sayılara
değil. "30.2 kg" ile "29.4 kg" arasındaki fark embedding uzayında neredeyse
kaybolur, çünkü cümlelerin geri kalanı aynıdır. Embedding anlamsal benzerlik
için doğru araçtır; sayısal karşılaştırma için çıkarma işlemi doğru araçtır.

Yerine `insights.py` konuldu: aynı soruları (kilo artışı mama değişikliğiyle
örtüşüyor mu, porsiyon kılavuzun neresinde) **deterministik** olarak
cevaplıyor. Sonuç aynı, güvenilirliği daha yüksek.

Embedding ve vektör arama, ait olduğu yerde — **serbest metin belge
koleksiyonunda** — kullanılıyor ve orada ölçülmüş biçimde çalışıyor: 23 soruluk
değerlendirmede 17/17 doğru belge.

---

## 9. Ölçülmüş sınırlar

| Konu | Durum | Ayrıntı |
|---|---|---|
| Türkçe cevap üretimi | Kapalı | 5 model denendi, hiçbiri geçmedi — `docs/EVALUATION.md` |
| Çapraz dilli retrieval | Çalışıyor | Türkçe soru → İngilizce belge, 7/8 |
| Gecikme | 13.9s medyan | CPU, ısıtma sonrası |
| Kapsam dışı tespiti | 6/6 | Dördü alan içi ama belgelerde olmayan sorular |
| Ölçek | ~10.000 chunk | Ötesinde ANN indeksi gerekir |
| Çoklu hayvan | Şema hazır, arayüz tek hayvanlı | `pet_id` her kayıtta var |

---

## 10. Genişletme noktaları

Mimari şunlara hazır, hiçbiri yapılmadı:

- **Çoklu hayvan** — veri katmanı zaten `pet_id` ile ayrılmış, API ve arayüz eklenir
- **Beslenme analizi** — mama besin değerleri + enerji ihtiyacı hesabı, `insights.py` deseninde yeni bir kural modülü
- **İlaç ve belirti takibi** — mevcut kayıt tablolarıyla aynı desende yeni tablolar
- **Daha güçlü yerel model** — `config.CHAT_MODEL_ALIAS` tek satır; Türkçe üretimi de bu şekilde açılır
- **Masaüstü paketi** — PyInstaller ile tek dosya dağıtım
