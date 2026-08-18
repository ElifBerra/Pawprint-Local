# Pawprint-Local — Proje Raporu

**Microsoft AI Innovators Yaz Programı, 2026**
Elif Berra Çelik · Burak Deniz Kaymak

---

## 1. Problem

Genel amaçlı bir dil modeline alanına özgü bir soru sorulduğunda, cevap sıklıkla
akıcı, biçimli ve yanlış oluyor. Projenin başında `phi-3.5-mini`'ye RAG'in ne
anlama geldiğini sorduk:

> "RAG stands for **Restart, Adapt, and Growth**, a strategy often used by
> companies, particularly in the energy sector..."

Tamamen uydurma, ve cevabın hiçbir yerinde bunu belli eden bir işaret yok. Bu
tür bir hata genel sohbette rahatsız edici; **evcil hayvan sağlığında zararlı.**
"Köpeğime çikolata verebilir miyim?" sorusuna kendinden emin yanlış bir cevap
gerçek sonuç doğurur.

Retrieval-Augmented Generation bu sorunu şöyle çözüyor: cevap üretmeden önce
güvenilir bir koleksiyondan ilgili pasajlar çekiliyor, modelden **yalnızca o
pasajlara dayanarak** cevap vermesi ve kaynak göstermesi isteniyor. İlgili
bir şey bulunamazsa model tahmin etmek yerine bilmediğini söylüyor.

### Neden evcil hayvan sağlığı

Alan seçimi keyfi değildi. Üç özelliği projeyi ilginç kılıyor:

**Veri hassas.** Hayvanın sağlık kayıtları sahibinin özel verisi. Tamamen
çevrimdışı çalışan bir sistem, "bulut yok" iddiasını pazarlama cümlesi olmaktan
çıkarıp mimari bir gerçeğe dönüştürüyor.

**Genel bilgi tek başına yetmiyor.** "Yetişkin köpekler günde iki öğün yer"
doğru ama işe yaramaz. Kullanıcının sorusu "*benim* köpeğim doğru besleniyor
mu?" ve buna cevap vermek için o hayvanın kendi kayıtları gerekiyor.

**Yanlış cevabın bedeli var.** Bu, sistemi tasarlarken sürekli geri döndüğümüz
kısıt oldu ve birçok kararı belirledi.

---

## 2. Yaklaşım

### İki bilgi kaynağı

Projenin üzerine kurulduğu ayrım:

```
  GENEL BİLGİ                              BU HAYVANA ÖZEL
  data/docs/*.md — 6 belge, 44 chunk       SQLite kayıtları
  ─────────────────────────────            ─────────────────────────
  "Çikolata teobromin içerir"              "30.2 kg, hedef 28.0 kg,
  "Yetişkin köpek günde iki öğün"           420 g Acme Premium,
                                            1596 kcal / 1363 gerekli"
        │                                          │
        │ chunk'lanır, embed edilir                │ kural motorundan geçer
        │ cosine similarity ile çekilir            │ metne dönüştürülür
        ▼                                          ▼
  ┌──────────────────────────────────────────────────────────┐
  │        PROMPT — iki kaynak ayrı etiketlerle              │
  └──────────────────────────┬───────────────────────────────┘
                             ▼
                  phi-3.5-mini (yerel, CPU)
                             ▼
   "Porsiyonu 420 g, Acme Premium için hesaplanan ihtiyaç 359 g.
    Son üç haftada 0.8 kg almış. Kademeli azaltma öneriliyor."
```

İki kaynak prompt'ta ayrı etiketlerle duruyor ve prompt'ta açık kural var:
*"KAYITLAR'da geçmeyen hiçbir şeyi ölçülmüş gibi belirtme."* Amaç, modelin genel
bir kılavuzu bu hayvana ait bir ölçümmüş gibi sunmasını engellemek.

### Kullanılan teknolojiler

| Bileşen | Seçim | Neden |
|---|---|---|
| Yerel çıkarım | Microsoft Foundry Local | Program gereksinimi; SDK model indirmeyi ve yaşam döngüsünü yönetiyor |
| Üretim modeli | `phi-3.5-mini` (3.8B) | CPU'da kabul edilebilir hız/kalite dengesi |
| Embedding | `qwen3-embedding-0.6b` | 1024 boyut, çok dilli |
| Veri | SQLite tek dosya | Sunucusuz, taşınabilir, vektörler BLOB olarak aynı dosyada |
| Vektör arama | NumPy cosine similarity | 44 chunk için tek `matmul`, bir milisaniyenin altında |
| Arayüz | FastAPI + düz HTML/CSS/JS | Çerçeve yok, derleme adımı yok, **CDN yok** |

CDN kullanmama kararı önemli: uygulama ağ kapalıyken çalışmak zorunda. Grafik
kütüphanesi yerine SVG'yi JavaScript üretiyor, tek bir dış kaynak yok.

---

## 3. Tasarım kararları

Bu bölüm raporun çekirdeği. Her karar bir ölçüme ya da bulunan bir hataya
dayanıyor.

### 3.1 Hesabı model yapmıyor

`insights.py` ve `nutrition.py` tamamen kural tabanlı, saf Python. Kilo trendi,
enerji ihtiyacı, porsiyon karşılaştırması, aşı tarihleri — hiçbiri modele
sorulmuyor.

Gerekçe: bu bulgular kullanıcının aksiyon alacağı uyarılar üretiyor
(*"porsiyonu azalt"*, *"veterinere göster"*). Böyle bir çıktının her açılışta
aynı olması gerekiyor. CPU'da çalışan 3.8 milyar parametreli bir model bunu
garanti edemez.

**İş bölümü: aritmetiği kural yapar, model cümle kurar.**

Bu kararın sonradan ortaya çıkan ikinci bir faydası oldu. Modelin Türkçe
üretemediğini ölçtükten sonra da içgörüler ve veteriner raporu **tamamen Türkçe
kalabildi** — çünkü o katman modele hiç uğramıyor.

### 3.2 Prompt bir güvenlik sınırı değil

Projenin en pahalı dersi.

Belge eşiğini geçemeyen bir soru, hayvanın kayıtları olduğu için yine de modele
gidiyordu. *"Who won the World Cup in 1998?"* sorusuna sistem
**"France won the FIFA World Cup in 1998"** cevabını verdi.

Prompt'u sertleştirdik:

> "Tek bildiğin şey aşağıdaki kayıtlar. Başka hiçbir bilgin yok. Veteriner
> bilgisi yok, genel bilgi yok, dünya hakkında hiçbir şey bilmiyorsun."

İşe yaramadı. Model 1998'de Fransa'nın kazandığını biliyor ve söylüyor.

Çözüm mimari oldu: kayıtların **ne hakkında olduğu** bir cümleye çevrilip embed
ediliyor, soru ona karşı ölçülüyor, eşiğin altındaysa **model hiç
çağrılmıyor.** Sonuç: 0.6 saniyede doğru ret.

Aynı ders Türkçe tarafında da çıktı: İngilizce bir prompt'a "cevabı Türkçe yaz"
talimatı eklemek bozuk çıktı verdi; promptun tamamını Türkçe yazmak gerekti.

**Bir modele "bilmiyormuş gibi yap" demek, mimariye "sorma" demekten zayıf.**

### 3.3 Chunk sınırları başlıklara göre

İlk sürümde chunk'lar 200 kelimelik pencerelerle kesiliyordu. Çikolata sorusuna
şu cevap geldi:

> "Chocolate contains theobromine, which is toxic to pets **and can indicate
> serious health issues like kidney disease, diabetes, or hyperadrenocorticism**."

İkinci kısım belgenin **su tüketimi** bölümünden geliyordu — aşırı susamanın
işaret ettiği hastalıklar. Pencere "Water" ve "Foods that are dangerous"
bölümlerini tek chunk'a paketlemişti. Model doğru chunk'ı çekiyordu, chunk'ın
kendisi iki konuluydu.

Önce prompt'a "sadece soruyu doğrudan cevaplayan cümleleri kullan" kuralı
eklendi. Benzer bir bulaşmayı düzeltti ama bunu düzeltmedi.

Yapısal çözüm: chunk'lar Markdown başlıklarını asla aşmıyor ve her chunk kendi
başlık izini taşıyor (`Nutrition and Feeding > Foods that are dangerous`).

### 3.4 Eşik dile göre değişiyor

Koleksiyon İngilizce. Türkçe soru çapraz dilde eşleştiriliyor ve aynı anlamdaki
soru **~0.30 daha düşük** skor alıyor.

| | Kapsam içi en düşük | Kapsam dışı en yüksek | Karar payı |
|---|---|---|---|
| İngilizce | 0.504 | 0.419 | +0.085 |
| Türkçe | 0.293 | 0.250 | +0.042 |

Tek eşik (0.48) kullanılırken Türkçe kapsam içi soruların **8/8'i** modele hiç
ulaşmadan reddediliyordu. Retrieval bozuk değildi — doğru belge 8 sorudan
7'sinde bulunuyordu — kalibrasyon bozuktu.

`SIM_THRESHOLDS = {"en": 0.48, "tr": 0.27}`

Türkçe karar payının İngilizcenin yarısı olduğunu da raporluyoruz: Türkçede
kapsam dışı tespiti ölçülebilir biçimde daha kırılgan.

### 3.5 Gram, bardak değil

Beslenme kayıtları gram cinsinden tutuluyor. "Bardak" bir birim değil — aynı
bardak iki farklı mamada ağırlıkça %20 fark eder.

Demo senaryosu bunun üzerine kuruldu: sahibi mamayı değiştirdi, kabı **aynı**
doldurdu, hiçbir şey değiştirmediğini düşünüyor. Ama yeni mama daha yoğun ve
günde 210 kcal fazla veriyor. Kilo artışı oradan geliyor.

**Gram kalori değildir.**

### 3.6 Mama verisi uydurulmadı

Katalogda 22 kayıt var: 17'si gerçek ürün (paket fotoğraflarından okunan ya da
üreticinin kendi ürün sayfasından çekilen), 5'i "(tipik)" diye işaretli kategori
ortalaması. **Hiçbir gerçek marka uydurma değer taşımıyor.**

Bu bir tercih değil zorunluluktu: arama sonuçları tutarsız ve eksik değer
döndürdü ("Protein: 7.0%", "Yağ İçeriği: .0%"), perakende siteleri analiz
panelini doğru aktarmıyor.

---

## 4. Değerlendirme

### 4.1 Notlandırılan koşu

23 soru: 17 belgelerden cevaplanabilir, 6 cevaplanamaz. Cevaplanamazların
**dördü alan içi ama belgelerde yok** ("yavru köpeğe otur komutu nasıl
öğretilir", "kısırlaştırma ne kadar tutar"). Fransa'nın başkenti kolay negatif;
asıl test bunlar.

Belgeleri yazan kişi ile soruları yazan kişi ayrı tutuldu — belgeyi yazan,
hangi soruların cevaplanabileceği konusunda kör oluyor.

| Metrik | Sonuç |
|---|---|
| Retrieval isabeti (doğru kaynak top-3'te) | **17/17** |
| Cevaplanması gerekeni cevapladı | **17/17** |
| Reddetmesi gerekeni reddetti | **6/6** |
| Hata | 0 |
| Medyan gecikme | 1.2s |
| İlk kelimeye kadar | 0.4s |
| Kapsam dışı gecikme | 0.2s |

Gecikme rakamları GPU'lu makinede. CPU'da aynı sorular ~16 saniye sürüyor ve
başka hiçbir şey değişmiyor (bkz. 4.5).

Karar payı: en düşük cevaplanabilir skor (0.548) ile en yüksek cevaplanamaz
skor (0.427) arasında **+0.121**.

### 4.2 Ayar turları

Altı koşu, her biri tek bir değişkeni ölçtü.

| Koşu | Değişiklik | Medyan | Doğruluk |
|---|---|---|---|
| 1 | Başlangıç (chunk 350, top_k 3) | 33.3s | 6/6 · 2/2 |
| 2 | Chunk 350 → 200 | 21.0s | 6/6 · 2/2 |
| 2b | Tekrar (gürültü ölçümü) | 20.0s | değişmedi |
| 3 | top_k 3 → 2 | 15.7s | 6/6 · 2/2 |
| 4 | Başlık sınırlı chunk'lama | 11.5s | **5/6** · 2/2 |
| 5 | top_k 2 → 3, eşik 0.48 | 13.3s | 6/6 · 2/2 |

**Koşu 2'nin bulgusu beklenmedikti:** chunk küçültmek sadece hızlandırmadı,
**doğruluğu da artırdı**. Kapsam içi skorlar 0.425-0.602'den 0.480-0.629'a
çıktı. Açıklaması: büyük chunk'ta farklı konulardaki paragraflar tek vektörde
ortalanıyor ve "biraz her şeye benzeyen" bulanık bir temsil oluşuyor.

**Koşu 2b kasten değil, kazayla oldu** — bir ayar değişikliği kaydedilmemişti.
Ama faydalı çıktı: aynı ayarla ölçüm gürültüsünün **±1 saniye** olduğunu
gösterdi. Sonraki karşılaştırmalarda bu eşiğin altındaki farklar anlamlı
sayılmadı.

**Koşu 4 bir gerileme üretti** ve bunu raporluyoruz. Başlık sınırlı chunk'lama
bulaşmayı çözdü ama "kötü nefes" sorusu cevaplanamaz oldu: "bad **breath**"
sorgusu acil durum belgesinin **Breathing** bölümüyle eşleşti ve `top_k=2` ile
diş belgesi listeden düştü. Koşu 5 bunu kapattı.

### 4.3 Üretici doğrulaması

Beslenme motorunu bağımsız olarak sınamanın bir yolunu bulduk: mama üreticileri
kendi besleme tablolarını yayımlıyor.

| Ürün | Üreticinin önerisi | Bizim hesabımız |
|---|---|---|
| Purina ONE Sterilcat, 4-6 kg kedi | 60-85 g | **81 g** |
| Pro Plan Sterilised, 4-6 kg kedi | 60-90 g | **80 g** |
| Pro Plan Small-Mini Adult, 5 kg köpek | 105 g | **101 g** |
| Pro Plan Small-Mini Adult, 10 kg köpek | 165-185 g | **170 g** |

Dört karşılaştırma, iki tür, iki üretici — hepsi aralığın içinde.

Kalori tahmin formülünü de doğruladık. Dört üründe üretici kendi metabolik
enerji değerini veriyor:

| Ürün | Üreticinin ME'si | Bizim tahminimiz | Sapma |
|---|---|---|---|
| Everyday Small-Mini Adult | 370 | 374 | %1.1 |
| Large Robust Puppy | 360 | 362 | %0.6 |
| HA Hypoallergenic | 342 | 348 | %1.6 |
| DRM Dermatosis | 400 | 381 | %4.8 |

### 4.4 Türkçe üretimi — ölçüldü, kapatıldı

Arayüzün Türkçe olması istendi. İki ayrı soru vardı ve ayrı ayrı ölçüldü.

**Retrieval çalışıyor.** Türkçe soru İngilizce belgeyi buluyor: 8 sorudan
7'sinde doğru kaynak. Dile göre eşikle sorun çözülüyor.

**Üretim çalışmıyor.** Kabul kriteri baştan konuldu: 5 soruda 0 hata, medyan
< 25s, okunabilir Türkçe, pire sorusunda permethrin uyarısının verilmesi.

| Model | Hata | Medyan | Gözlem |
|---|---|---|---|
| `phi-3.5-mini` | 3/5 | 65s | Bozuk dilbilgisi |
| `qwen3-1.7b` | 1/5 | 44s | İngilizce düşünüyor, cevap vermiyor |
| `qwen3-4b` | 3/5 | 59s | Aynı davranış |
| `qwen2.5-1.5b` | 3/5 | 76s | Uydurma kelimeler: *"cıkçatalar biraz azetli"* |
| `ministral-3-3b` | 5/5 | — | Hiç cevap vermedi |

**Karar: arayüz Türkçe, cevaplar İngilizce.** Türkçe promptlar ve dile göre
eşik kod tabanında duruyor — çalışıyorlar, ölçüm onlara karşı yapıldı, daha
güçlü bir yerel model çıktığında tek satırlık değişiklik.

Bu bir eksiklik değil, ölçülmüş bir sınır. Çalışmayan bir Türkçe modunu arayüze
koymak, kullanıcıya *"cıkçatalar biraz azetli"* gibi bir sağlık tavsiyesi
göstermek olurdu.

### 4.5 Kayıtsız execution provider — projenin en pahalı gözden kaçırması

`check_env.py` ilk günden beri şunu yazıyordu:

```
CUDAExecutionProvider    is_registered=False
WebGpuExecutionProvider  is_registered=False
```

"GPU yok, CPU'da çalışıyoruz" diye okuduk. Katalog da `phi-3.5-mini` için tek
varyant gösteriyordu (`generic-cpu`), bu da yorumu doğruluyordu.

Yanlıştı. **Foundry Local yalnızca kayıtlı provider'lara ait varyantları
gösteriyor.** GPU sürümü yok değildi, görünmüyordu. Kayıt tek çağrı ve iki
saniye:

```python
manager.download_and_register_eps()
```

Makinede NVIDIA kartı varmış.

| Metrik | CPU | GPU | Kat |
|---|---|---|---|
| İlk kelimeye kadar | 13.6s | **0.4s** | **34×** |
| Toplam medyan | 16.5s | **1.2s** | 14× |
| Doğruluk | 8/8 | 8/8 | değişmedi |

**Ders — ve rahatsız edici olan kısım bu:** altı ayar koşusu boyunca gecikmeyi
33.3 saniyeden 13.3'e indirdik, yaklaşık 2.5 kat. Gözden kaçırdığımız iki
satırlık çağrı 14 kat getirdi.

Ayar çalışması boşa gitmedi — chunk küçültme aynı zamanda doğruluğu artırdı ve
o kazanç donanımdan bağımsız. Ama gecikme tarafındaki emeğin büyük kısmı,
platformun zaten sunduğu bir yeteneği kullanmadığımız için harcandı.

**Bir platformun etrafında optimizasyon yapmadan önce platformun ne sunduğunu
kontrol et.** Teşhis çıktısı iki hafta boyunca doğru bilgiyi gösterdi; biz
yanlış okuduk.

Ek olarak GPU'ya geçince ilk çağrı sorunları çıktı (ilk embedding iptal
ediliyor, ilk cevap 64 saniye). Sebep modellerin yüklenip hiç
çalıştırılmamasıydı; `warm_up()` artık her iki modelden birer istek geçiriyor.

CPU yolu korunuyor: `PREFER_GPU = False` ile geri dönülüyor ve yukarıdaki bütün
CPU ölçümleri o senaryo için geçerli kalıyor.

### 4.6 Hız için model küçültme — denendi, reddedildi

Demo video olarak çekilecekti ve izleyicinin beklediği süre — ilk kelimenin
ekranda belirmesi — 13.6 saniyeydi. En büyük kaldıraç modeli küçültmekti.

`qwen2.5-1.5b` gerçekten hızlı: ilk kelime **5.5 saniye**, medyan toplam
7.2 saniye. Yaklaşık 2.3 kat.

Ve iki cevap kararı verdi:

> **"Can I give my dog chocolate?"**
> *"**Yes, you can give your dog chocolate.** However, dark chocolate has more
> theobromine than milk chocolate..."*

Doğru pasajları çekmişti — kaynaklar listede duruyordu. Doğru bağlamı aldı ve
tersini söyledi.

> **"What is the capital of France?"** (skor 0.363, eşiğin altında)
> *"Paris."*

`phi-3.5-mini` aynı soruyu aynı promptla reddediyor.

**2.3 kat hız, güvenlik karşılığında satın alınamaz.** `phi-3.5-mini` kaldı.

Bu ölçümün ikinci bir faydası oldu: projenin tasarım ilkesini doğruladı. Model
değiştiğinde kural motoru, eşikler, enerji hesapları ve aşı takvimi **hiç
değişmedi** — çünkü hiçbiri modele bağlı değil. Bozulan tek şey modelin kendi
cevaplarıydı. Önemli işleri modele yaptırmamak, tam olarak bunun için.

### 4.6 Testler

87 birim testi, model yüklemeden 2.7 saniyede çalışıyor. En yoğun olduğu yer
kural motoru — çünkü orada geliştirme sırasında **dört ayrı boşluk** tesadüfen
bulundu:

| Bulunan boşluk | Nasıl fark edildi |
|---|---|
| Kilo kaybı kuralı hiç yoktu | Test verisine −25 kg girildi, sistem sustu |
| Veri kalitesi kontrolü yoktu | 30.2 kg → 5.0 kg gerçek veri sanıldı |
| Kurallar çelişiyordu | Kilo alan hayvana "daha çok ver" dedi |
| Anahtar değişikliği çağıranları kırdı | Soru-cevap ve PDF aynı anda çöktü |

Dördü de artık test. Bazı testler davranışı değil **kararı** kilitliyor:
kaybın artıştan düşük eşikte raporlanması, veri kalitesinin ondan çıkarılan
tavsiyeden önce gelmesi, veterinerin yazdığı tarihin her kuralı geçersiz
kılması.

---

## 5. Çıkarılan dersler

**Ölçüm aracının kendisi de test edilmeli.** Değerlendirmenin ilk koşusunda üç
"başarısızlık" göründü. Cevaplara bakınca model doğru davranmıştı; bizim ret
tespitimiz *"I'm sorry, but..."* önekli meşru reddi tanımıyordu. Ham sayıya
bakıp "3/6" diye rapor etseydik yanlış bir sonuç yayınlamış olacaktık.

**Kimsenin kullanmadığı yolu ölçmek kolay.** `bench.py` uzun süre `pet=None`
ile çalıştı; arayüz ise her soruda kayıtları gönderiyordu. Gerçek yol ölçülünce
medyan 15.2s değil 67.9s çıktı. Aynı hatayı ikinci kez streaming'de yapmamak
için bench'e `--stream` seçeneği eklendi.

**Bir SDK'nın parametreyi kabul etmesi, uyguladığı anlamına gelmiyor.**
`frequency_penalty` reddedilmiyordu ama çıktıyı bozuyordu — "three colours are
three. Name three colours are th". Ölçmeden parametre eklenmemeli.

**Gecikmenin sebebi genelde sanılan yerde değil.** Kayıtlar prompt'a girince
süre 4.5 katına çıktı. İlk tahmin prompt uzunluğuydu; rakamlar tutmuyordu.
Asıl sebep modelin token tavanına kadar yazmasıydı — konuşacak daha çok şeyi
vardı ve durması için sebep yoktu.

**Dokümantasyon kod kadar bozulabilir.** `insights.summary()` anahtarları
bardaktan grama çevrilirken iki çağıran güncellenmedi ve tek bir `KeyError`
soru-cevabı, ekrandaki raporu ve PDF'i aynı anda düşürdü.

---

## 6. Bilinen sınırlar

- **Veteriner tavsiyesi değil.** Küçük bir belge koleksiyonundan çalışıyor ve
  hayvanı muayene edemiyor.
- **Cevaplar İngilizce.** Beş model ölçüldü, hiçbiri geçmedi.
- **AAFCO değerleri minimum, hedef değil.** Minimumu karşılayan bir mama
  otomatik olarak o hayvan için ideal değildir.
- **Enerji hesabı tahmindir.** Bireysel metabolizma %20 civarında sapabilir.
  Hesap başlangıç noktası, tartı ölçüm.
- **Gecikme CPU'ya bağlı.** Makinede başka ağır iş varsa süre belirgin uzuyor.
- **Ölçek.** Tüm chunk'lar her soruda belleğe alınıyor; yaklaşık 10.000 chunk'a
  kadar taşır, ötesinde yaklaşık en yakın komşu indeksi gerekir.
- **Tek tur.** "Peki ya kediler için?" gibi devam soruları çalışmıyor.
- **Kurulum başına tek hayvan.** Şema `pet_id` taşıyor, yani çoklu hayvan bir
  arayüz işi.

---

## 7. Sonraki adımlar

Mimari şunlara hazır, hiçbiri yapılmadı:

- **Çoklu hayvan** — veri katmanı hazır, API ve arayüz eklenir
- **Etiket fotoğrafından okuma** — katalogda `qwen3-vl` modelleri var, SDK'nın
  görüntü kabul edip etmediği sondası yazıldı ama çalıştırılmadı
- **İlaç ve belirti takibi** — mevcut kayıt tablolarıyla aynı desende
- **Daha güçlü yerel model** — `CHAT_MODEL_ALIAS` tek satır; Türkçe üretimi de
  bu şekilde açılır
- **Masaüstü paketi** — PyInstaller ile tek dosya dağıtım

---

## 8. Program gereksinimleri karşılama

| Beklenti | Nerede | Doğrulama |
|---|---|---|
| Foundry Local ile çevrimdışı çıkarım | `src/foundry.py` | `python scripts/check_env.py` |
| RAG (retrieve → augment → generate) | `src/rag.py` | `docs/eval-results.md` |
| Belge koleksiyonu | `data/docs/` — 6 belge, 44 chunk | `python -m src.ingest` |
| Embedding | `src/embeddings.py` — 1024 boyut | `python -m scripts.test_embeddings` |
| Vektör arama | `src/retrieve.py` — cosine similarity | `pytest tests/test_retrieve.py` |
| SQLite | `src/db.py`, `src/pets_db.py` | `pawprint.db` |
| Prompt mühendisliği | `src/config.py` | `docs/EVALUATION.md` |
| Soru-Cevap arayüzü | `web/`, `src/cli.py`, `src/app.py` | Üç seçeneğin üçü de yapıldı |
| Test ve değerlendirme | 87 birim testi + 23 soruluk set | `pytest`, `tests/run_eval.py` |
| Dokümantasyon | README + 5 doküman | `docs/` |
| Tamamen çevrimdışı | Her yerde — CDN bile yok | Ağı kapatıp çalıştır |

---

## Ekler

- [ARCHITECTURE.md](ARCHITECTURE.md) — mimari ve diyagramlar
- [EVALUATION.md](EVALUATION.md) — her ölçüm koşusu, ham veriyle
- [eval-results.md](eval-results.md) — notlandırılan koşunun çıktısı
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) — bilinen sorunlar ve teşhis sırası
- [COLLABORATION.md](COLLABORATION.md) — tek makinede iki kişilik çalışma düzeni
