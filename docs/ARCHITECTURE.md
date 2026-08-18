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
│   │   ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌──────────┐   │   │
│   │   │ rag.py   │  │insights.py│  │nutrition. │  │vaccines. │   │   │
│   │   │ RAG hattı│  │kural motoru│ │py  besin  │  │py aşı    │   │   │
│   │   └────┬─────┘  └─────┬─────┘  │hesabı     │  │takvimi   │   │   │
│   │        │              │        └─────┬─────┘  └────┬─────┘   │   │
│   │        │              │              │             │         │   │
│   │        │              └──────┬───────┴─────────────┘         │   │
│   │        │                     │            (model yok —       │   │
│   │        │                     │             saf Python)       │   │
│   │        │              ┌──────▼───────────────────┐           │   │
│   │        │              │ pet_context.py           │           │   │
│   │        │              │ kayıtlar → prompt metni  │           │   │
│   │        │              │ + arama terimleri        │           │   │
│   │        │              │ + alaka skoru (2. kapı)  │           │   │
│   │        │              └──────┬───────────────────┘           │   │
│   │   ┌────▼─────────┐           │       ┌────────────────┐      │   │
│   │   │ retrieve.py  │◄──────────┘       │  report.py     │      │   │
│   │   │ vektör arama │  sorgu            │  vet raporu    │      │   │
│   │   │ + zenginleş. │  zenginleştirme   │  (PDF)         │      │   │
│   │   └──────┬───────┘                   └────────────────┘      │   │
│   │          │                                                   │   │
│   │   ┌──────▼───────┐   ┌──────────────┐                        │   │
│   │   │embeddings.py │   │   llm.py     │                        │   │
│   │   └──────┬───────┘   └──────┬───────┘                        │   │
│   │          └────────┬─────────┘                                │   │
│   │              ┌────▼──────────┐                               │   │
│   │              │  foundry.py   │  SDK ile tek temas noktası    │   │
│   │              │               │  + EP kaydı + varyant seçimi  │   │
│   │              └────┬──────────┘  + warm_up()                  │   │
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
│   │ • stool_rec.    │   │  ONNX Runtime                │          │  │
│   │ • vaccine_rec.  │   │  CUDA varyantı (varsa)       │          │  │
│   │ • foods         │   │  yoksa generic-cpu           │          │  │
│   └─────────────────┘   └──────────────────────────────┘          │  │
│                                                                   │  │
│   ✓ İnternet gerekmiyor   ✓ API anahtarı yok   ✓ Bulut yok        │  │
└───────────────────────────────────────────────────────────────────┴──┘
```

**Çalışma zamanı seçimi.** `foundry.py` açılışta `download_and_register_eps()`
çağırıyor. Bu çağrı olmadan katalog her model için yalnızca `generic-cpu`
varyantını gösteriyor — GPU sürümü var olsa bile. Kayıttan sonra `_pick_variant()`
adında "gpu" geçen varyantı seçiyor. Kayıt başarısızsa uygulama sessizce CPU
varyantıyla devam ediyor; `PREFER_GPU = False` ile de elle kapatılabiliyor.
Ayrıntı: `docs/EVALUATION.md` Koşu 11.

---

## 2. İki bilgi kaynağı

Projeyi bir belge arama kutusundan ayıran şey bu ayrım.

```
  GENEL BİLGİ                             BU HAYVANA ÖZEL
  data/docs/*.md                          SQLite kayıtları
  ────────────────                        ─────────────────
  "Yetişkin köpekler günde                "Bella 30.2 kg, hedef 28.0,
   iki öğün yer"                           günde 320 g Pro Plan Adult,
  "Çikolata teobromin içerir"              hesaplanan ihtiyaç 255 g"
        │                                        │
        │ chunk'lanır, embed edilir              │ kural + besin motorundan geçer
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
   "Bella günde 320 g alıyor, mevcut kilosu ve yaşı için
    hesaplanan ihtiyaç 255 g. Son 3 haftada 0.8 kg almış.
    Kademeli azaltma ve haftalık tartım öneriliyor."
```

İki kaynak prompt'ta **ayrı etiketlerle** duruyor. Sebebi: model genel bir
kılavuzu bu hayvana ait ölçülmüş bir veriymiş gibi sunmasın. Prompt'ta açık
kural var: *"KAYITLAR'da geçmeyen hiçbir şeyi ölçülmüş gibi belirtme."*

---

## 3. RAG hattı

```
  Kullanıcı sorusu           Hayvanın kaydı
        │                          │
        │      pet_context.search_terms(pet) → "cat kitten"
        │                          │
        ▼                          ▼
  ┌─────────────────────────────────────────────┐
  │ 0. SORGU ZENGİNLEŞTİRME                     │
  │    retrieve.expand(soru, terimler)          │
  │    "can i give chocolate"                   │
  │      → "can i give chocolate (cat kitten)"  │
  │                                             │
  │    SADECE embed edilen metne ekleniyor.     │
  │    Model bu metni hiç görmüyor.             │
  └──────────────────┬──────────────────────────┘
                     ▼
  ┌─────────────────────────────────────────────┐
  │ 1. RETRIEVE                                 │
  │    embeddings.embed_one(zenginleşmiş metin) │
  │    → 1024 boyutlu vektör                    │
  │                                             │
  │    retrieve.rank()                          │
  │    → tüm chunk'lar SQLite'tan okunur        │
  │    → L2 normalize + tek matmul              │
  │    → cosine similarity, en iyi 3            │
  └──────────────────┬──────────────────────────┘
                     │
        ╔════════════▼═════════════╗
        ║ 1. KAPI — belge eşiği    ║
        ║ en yüksek skor ≥ eşik?   ║
        ║ (EN: 0.48 · TR: 0.27)    ║
        ╚════════════┬═════════════╝
         ┌───────────┴────────────┐
      hayır                      evet
         │                        │
         ▼                        │
  ╔═══════════════════════╗       │
  ║ 2. KAPI — kayıt eşiği ║       │
  ║ pet_context.relevance ║       │
  ║ (EN: 0.32 · TR: 0.20) ║       │
  ╚═══════┬═══════════════╝       │
    ┌─────┴──────┐                │
  hayır        evet               │
    │            │                │
    ▼            ▼                ▼
┌──────────┐ ┌────────────┐ ┌──────────────────────────────┐
│"Bu bilgi │ │ SADECE     │ │ 2. AUGMENT                   │
│ belgele- │ │ KAYITLAR   │ │    prompt = sistem talimatı  │
│ rimde    │ │ prompt'u   │ │           + KAYITLAR         │
│ yok."    │ │            │ │           + REFERANS         │
│          │ │ ("Bella    │ │           + soru             │
│ 0.0 sn   │ │  kaç kilo?"│ └──────────────┬───────────────┘
│ model hiç│ │  gibi)     │                │
│ çağrılmaz│ └─────┬──────┘                │
└──────────┘       └────────┬──────────────┘
                            ▼
                 ┌──────────────────────────────┐
                 │ 3. GENERATE                  │
                 │    phi-3.5-mini, streaming   │
                 │    max 180 token             │
                 └──────────────┬───────────────┘
                                ▼
                     Cevap + kaynak dosya adları
                     + kullanılan pasajlar (skorlarıyla)
```

**Eşik neden var.** Kapsam dışı soru modele hiç gitmiyor: hem doğru sonuç
(model uydurma şansı bulamıyor) hem hızlı (16 saniye yerine 0 saniye).
Eşik değerleri 23 soruluk değerlendirmeden ölçüldü, tahmin değil. Ölçülen karar
payı **+0.120**: en düşük cevaplanabilir skor 0.547, en yüksek cevaplanamaz
0.428.

**Neden iki kapı.** Tek kapı yeterli değildi. Kullanıcı *"Bella kaç kilo?"* diye
sorduğunda hiçbir belge eşleşmiyor — cevap kayıtlarda. Ama belge kapısını
gevşetmek kapsam dışı soruları da içeri alıyordu.

İlk denemem prompt'a *"genel bilgin yok"* yazmaktı. İşe yaramadı: model
*"France won the FIFA World Cup in 1998"* cevabını, ne kadar sert söylenirse
söylensin vermeye devam etti. **Prompt bir güvenlik sınırı değil.** Çözüm
mimari oldu — belge kapısı kapanınca soru bu kez hayvanın kayıtlarına karşı
puanlanıyor, o da tutmazsa model hiç çağrılmıyor. Reddetme artık modelin
kararına bağlı değil; kod akışında.

**Sorgu zenginleştirme neden var.** *"can i give chocolate"* skoru 0.446 —
eşiğin altında, haksız yere reddediliyordu. *"can i give my cat chocolate"*
ise 0.523. Eksik olan tek şey türdü. Eşiği düşürmek yerine hayvanın türünü
embed edilen metne ekledim; model bu ekleme metnini görmüyor, yalnızca vektör
değişiyor. İki soru kurtuldu, kapsam dışı soruların hiçbiri yükselmedi ve karar
payı +0.019 yerine +0.077 oldu — eşiği düşürseydik pay daralacaktı.

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
  │  • veri kalitesi   (ardışık tartımda %25+ fark,│
  │                     gelecek tarihli kayıt)     │
  │  • kilo artışı     (+ mama değişikliği ile     │
  │                     zaman örtüşmesi)           │
  │  • kilo kaybı      (vücut ağırlığının %5'i →   │
  │                     uyarı, veterinere yönlendir)│
  │  • porsiyon        (hesaplanan ihtiyaçla fark) │
  │  • makro besinler  (AAFCO kuru madde alt sınır)│
  │  • hedef kilo      (üstünde / altında)         │
  │  • dışkı kalitesi  (30 günlük normal oranı)    │
  │  • aşı            (geciken / yaklaşan doz)     │
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

**Kurallar birbiriyle çelişebilir, bu yüzden uzlaştırılıyor.** Hayvan hedefinin
üstünde ve kilo alıyorsa, porsiyon kuralı "hesaplanan ihtiyacın altında
besleniyor" diyebilir — çünkü ihtiyaç *mevcut* kilodan hesaplanıyor.
`insights.py` bu durumda "daha çok ver" demeyi reddediyor; ölçülen gerçek
(kilo artıyor) hesaplanan tahmine üstün geliyor.

---

## 5. Beslenme hesabı

`nutrition.py` de saf Python, aynı gerekçeyle. Veteriner beslenme literatüründeki
standart zinciri uyguluyor:

```
  Hayvan (tür, kilo, yaş, kısırlık)      Mama (etiket paneli)
        │                                      │
        ▼                                      ▼
  ┌──────────────────────┐          ┌────────────────────────┐
  │ RER = 70 × kg^0.75   │          │ % protein, yağ, lif,   │
  │ dinlenme enerjisi    │          │ nem, kül  (as-fed)     │
  └──────────┬───────────┘          │ kcal/100 g             │
             │                      └───────────┬────────────┘
  ┌──────────▼───────────┐                      │
  │ MER = RER × faktör   │          ┌───────────▼────────────┐
  │ yavru 2.5 · kısır 1.6│          │ kuru maddeye çevir     │
  │ kısırsız 1.8 · yaşlı │          │ %DM = %as-fed ÷        │
  │ 1.4 · kilo verme 1.0 │          │        (100 − nem)×100 │
  └──────────┬───────────┘          └───────────┬────────────┘
             │                                  │
             └───────────┬──────────────────────┘
                         ▼
        ┌────────────────────────────────────────┐
        │ gerekli gram = MER ÷ (kcal/g)          │
        │ AAFCO alt sınırlarıyla karşılaştır     │
        │ (kedi/köpek, yavru/yetişkin ayrı)      │
        └────────────────┬───────────────────────┘
                         ▼
         Öğün analizi · Günlük · Haftalık · Aylık
```

**Neden bardak değil gram.** Bardak bir hacim ölçüsü; mamanın yoğunluğuna göre
aynı bardak 80 g da olabilir 130 g da. Enerji hesabı kütleye dayanıyor, dolayısıyla
hacimle yapılan her hesap baştan hatalı. Eski kayıtlar `pets_db._migrate()` ile
grama çevrildi.

**Hedefler hayvana göre.** Sabit bir "günde X gram" tablosu yok; her sayı o
hayvanın kilosu, yaşı, türü ve kısırlık durumundan hesaplanıyor.

**Aşı takvimi** (`vaccines.py`) aynı desende: `data/docs/vaccination-schedule.md`
içindeki protokol Python veri yapısına kodlanmış, `next_due()` bir sonraki dozu
kayıtlardan ve doğum tarihinden hesaplıyor.

---

## 6. Veri modeli (SQLite)

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
  │ UNIQUE(source,chunk_index)│ │      │ neutered     INTEGER     │
  └───────────────────────────┘ │      │ target_weight_kg REAL    │
                                │      │ owner_name   TEXT        │
   float32 dizisi .tobytes()    │      └───────────┬──────────────┘
   ile saklanır — JSON'dan      │                  │ 1
   ~4 kat küçük ve okurken      │                  │
   ayrıştırma yok. Retrieval    │        ┌─────────┴──────────┐
   her soruda tabloyu tümüyle   │        │ N                  │
   okuduğu için bu fark önemli. │   ┌────▼──────────┐  ┌──────▼─────────┐
                                │   │ weight_records│  │ feeding_records│
  ┌───────────────────────────┐ │   │───────────────│  │────────────────│
  │ foods    (mama kataloğu)  │ │   │ pet_id     FK │  │ pet_id      FK │
  │───────────────────────────│ │   │ recorded_on   │  │ recorded_on    │
  │ id            INTEGER PK  │ │   │ weight_kg     │  │ food_id     FK │──┐
  │ brand         TEXT        │◄┼───┤ UNIQUE(pet,   │  │ food_brand     │  │
  │ product       TEXT        │ │   │        date)  │  │ portion_grams  │  │
  │ species       TEXT ◄──────┼─┼─┐ └───────────────┘  │ meals_per_day  │  │
  │ life_stage    TEXT        │ │ │                    │ note           │  │
  │ kcal_per_100g REAL        │ │ │ ┌───────────────┐  └────────────────┘  │
  │ protein_pct   REAL        │ │ │ │ stool_records │                      │
  │ fat_pct       REAL        │ │ │ │───────────────│  ┌─────────────────┐ │
  │ fiber_pct     REAL        │ │ │ │ pet_id     FK │  │ vaccine_records │ │
  │ moisture_pct  REAL        │ │ │ │ recorded_on   │  │─────────────────│ │
  │ ash_pct       REAL        │ │ │ │ quality       │  │ pet_id       FK │ │
  │ source        TEXT        │ │ │ │ frequency     │  │ vaccine_name    │ │
  └───────────────────────────┘ │ │ └───────────────┘  │ given_on        │ │
              ▲                 │ │                    │ next_due_on     │ │
              └─────────────────┼─┼────────────────────┴─────────────────┘ │
                                │ │                                        │
   Arayüz mama listesini türe   │ └────────────────────────────────────────┘
   göre süzüyor: kedi seçiliyse
   kedi mamaları geliyor.       │  "Diğer" seçilirse kullanıcı etiket
                                │  panelini kendi giriyor, kayıt
                                │  foods'a eklenmeden saklanıyor.
```

**İki alan neden ayrı.** Belge koleksiyonu `ingest --rebuild` ile silinip
yeniden kurulabilir; hayvan kayıtları kullanıcının verisi ve o işlemden
etkilenmemeli. Bu yüzden `db.py` (chunk'lar) ve `pets_db.py` (kayıtlar) ayrı
modüller, aynı bağlantıyı paylaşıyorlar ama şemaları bağımsız.

**Vektör araması neden SQL'de değil.** 44 chunk için tüm embedding'leri belleğe
alıp tek `matmul` yapmak bir milisaniyenin altında sürüyor. Vektör indeksi
(sqlite-vec vb.) bu ölçekte gereksiz karmaşıklık. Bu yaklaşım yaklaşık 10.000
chunk'a kadar taşır; ötesinde ANN indeksi gerekir.

**Her kayıt için tam CRUD.** Yanlış girilen bir tartım ya da öğün düzeltilebiliyor
ve silinebiliyor: `pets_db` her kayıt türü için `add / list / update / delete`
sunuyor, arayüzde her satırın yanında ✎ ve 🗑 var. Bunun bir de veri kalitesi
tarafı var — `insights.py` düzeltilmemiş bir kaydı (ardışık iki tartım arasında
%25 fark, gelecek tarihli giriş) uyarı olarak gösteriyor.

---

## 7. Modül haritası

```
src/
├── config.py        Tüm ayarlar tek yerde. Dile göre eşikler, promptlar.
├── foundry.py       SDK ile TEK temas noktası. Singleton koruması, lazy
│                    yükleme, model cache, EP kaydı, GPU varyant seçimi,
│                    warm_up(). Yerel model değişirse burası değişir.
├── models.py        Ortak veri tipleri: Chunk, Retrieved, Answer, Pet,
│                    WeightRecord, FeedingRecord, StoolRecord,
│                    VaccineRecord, Food, Insight
│
├── chunking.py      Başlık sınırlı bölme + başlık izi
├── embeddings.py    Metin → vektör, batch'li, L2 normalize, tek yeniden deneme
├── db.py            chunks tablosu
├── ingest.py        belgeler → chunk → embedding → SQLite
│
├── retrieve.py      Cosine similarity, top-K, alaka eşiği, sorgu zenginleştirme
├── llm.py           Sohbet istemcisi sarmalayıcı, streaming, <think> filtresi
├── rag.py           Hat: retrieve → augment → generate, iki kapılı savunma
├── pet_context.py   Kayıtları prompt metnine çevirir, arama terimleri,
│                    kayıt alaka skoru (2. kapı)
│
├── pets_db.py       pets + kayıt tabloları, tam CRUD, şema göçü
├── foods_db.py      foods tablosu, türe göre süzme
├── insights.py      Kural motoru
├── nutrition.py     RER/MER, kuru madde çevrimi, AAFCO sınırları,
│                    öğün/günlük/haftalık/aylık analiz
├── vaccines.py      Aşı protokolü, sonraki doz hesabı
├── report.py        Vet raporu (veri + PDF, Türkçe karakterler için TTF)
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

Kilit `Lock` değil **`RLock`** — `get_model()` kilidi alıp `get_manager()`
çağırdığı için düz kilit kendini kilitliyordu.

---

## 8. Programın istediği teknolojiler nerede

| Beklenti | Nerede | Nasıl doğrulanır |
|---|---|---|
| Foundry Local ile çevrimdışı çıkarım | `src/foundry.py`, `src/llm.py` | `python scripts/check_env.py` |
| Donanım hızlandırma | `src/foundry.py` — EP kaydı + varyant seçimi | `python -m scripts.probe_providers` |
| RAG (retrieve → augment → generate) | `src/rag.py` | `docs/eval-results.md` |
| Belge koleksiyonu | `data/docs/` — 6 belge, 44 chunk | `python -m src.ingest` |
| Embedding | `src/embeddings.py` — qwen3-embedding-0.6b, 1024 boyut | `python -m scripts.embed_steps` |
| Vektör arama | `src/retrieve.py` — cosine similarity | `pytest tests/test_retrieve.py` |
| SQLite | `src/db.py`, `src/pets_db.py`, `src/foods_db.py` | `pawprint.db` |
| Alan hesabı (model değil) | `src/nutrition.py`, `src/vaccines.py`, `src/insights.py` | `pytest tests/test_nutrition.py` |
| Prompt mühendisliği | `src/config.py` — TR/EN, tek ve iki kaynaklı şablonlar | `docs/EVALUATION.md` |
| Soru-Cevap arayüzü | `web/`, `src/cli.py` | `python -m src.serve` |
| Tamamen çevrimdışı | Her yerde — CDN bile yok | Ağı kapatıp çalıştır |

---

## 9. Orijinal tasarımdan sapma

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

Aynı gerekçe sonradan `nutrition.py` ve `vaccines.py` için de geçerli oldu:
enerji ihtiyacı bir çıkarma-çarpma işi, aşı takvimi bir tarih aritmetiği. İkisi
de modele sorulacak sorular değil.

---

## 10. Ölçülmüş sınırlar

| Konu | Durum | Ayrıntı |
|---|---|---|
| Türkçe cevap üretimi | Kapalı | 5 model denendi, hiçbiri geçmedi — `docs/EVALUATION.md` |
| Çapraz dilli retrieval | Çalışıyor | Türkçe soru → İngilizce belge, 7/8 |
| Gecikme (GPU) | 0.9s medyan | 23 soruluk değerlendirme, ısıtma sonrası |
| Gecikme (CPU) | ~16s medyan | `PREFER_GPU = False` |
| Kapsam dışı tespiti | 6/6 | Dördü alan içi ama belgelerde olmayan sorular |
| Karar payı | +0.120 | 0.547 (en düşük evet) − 0.428 (en yüksek hayır) |
| Ölçek | ~10.000 chunk | Ötesinde ANN indeksi gerekir |
| Çoklu hayvan | Şema hazır, arayüz tek hayvanlı | `pet_id` her kayıtta var |
| Mama kataloğu | Elle derlendi | Üretici etiket panellerinden; barkod/OCR yok |

---

## 11. Genişletme noktaları

Mimari şunlara hazır, hiçbiri yapılmadı:

- **Çoklu hayvan** — veri katmanı zaten `pet_id` ile ayrılmış, API ve arayüz eklenir
- **Etiket fotoğrafından okuma** — "Diğer" mamada besin panelini elle girmek yerine
  fotoğraftan çıkarmak; `scripts/probe_vision.py` yazıldı, çalıştırılmadı
- **İlaç ve belirti takibi** — mevcut kayıt tablolarıyla aynı desende yeni tablolar
- **Daha güçlü yerel model** — `config.CHAT_MODEL_ALIAS` tek satır; Türkçe üretimi de bu şekilde açılır
- **Masaüstü paketi** — PyInstaller ile tek dosya dağıtım
