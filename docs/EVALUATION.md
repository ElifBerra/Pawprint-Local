# Değerlendirme

Ölçümler `python -m scripts.bench` ile alındı. Sabit 8 soruluk set: 6'sı
belgelerden cevaplanabilir, 2'si kapsam dışı. Donanım: Windows, CPU
(GPU yok, tüm modeller `generic-cpu` varyantı).

## Koşu 1 — Referans

`chunk_size=350 overlap=50 top_k=3 max_tokens=256 threshold=0.35`
Külliyat: 12 chunk / 6 kaynak / ortalama 1801 karakter
Model: `phi-3.5-mini` + `qwen3-embedding-0.6b`

| Metrik | Değer |
|---|---|
| Doğru cevaplanan (kapsam içi) | 6/6 |
| Doğru "bilmiyorum" (kapsam dışı) | 2/2 |
| Hata | 0 |
| Ortalama gecikme | 28.3s |
| Medyan gecikme | 33.3s |
| En hızlı / en yavaş | 0.6s / 49.9s |
| Model ısınma | 8.6s |

Benzerlik skorları:

| Soru tipi | En yüksek skor aralığı |
|---|---|
| Kapsam içi | 0.425 – 0.602 |
| Kapsam dışı | 0.142 – 0.144 |

**Yorum.** Doğruluk tarafı sorunsuz: her kapsam içi soru doğru kaynaklarla
cevaplandı, her kapsam dışı soru reddedildi. Kapsam içi ve dışı skorlar
arasındaki boşluk büyük (0.425 vs 0.144), yani `SIM_THRESHOLD=0.35` güvenli bir
yerde duruyor — eşiğe yakın hiçbir sonuç yok, dolayısıyla sınırda yanlış karar
riski düşük.

Eşik mekanizmasının hız kazancı net görülüyor: kapsam dışı sorular **0.6
saniyede** dönüyor çünkü model hiç çağrılmıyor. Kapsam içi sorular 31-50 saniye.

**Sorun: gecikme.** Medyan 33 saniye kullanılamaz. Bağlam yaklaşık
3 × 1800 = 5400 karakter (~1400 token) ve CPU'da asıl maliyet bu bağlamın
işlenmesi. Sonraki koşular bunu hedefliyor.

---

## Koşu 2 — Chunk boyutu 350 → 200

`chunk_size=200 overlap=30`

Gerekçe: bağlam uzunluğu doğrudan prompt işleme süresini belirliyor. Daha küçük
chunk'lar hem bağlamı kısaltır hem de retrieval'ı keskinleştirir — 12 chunk'lık
bir külliyatta `top_k=3` demek verinin dörtte birini modele göndermek demek.

| Metrik | Koşu 1 | Koşu 2 |
|---|---|---|
| Chunk sayısı | 12 | 23 |
| Ortalama chunk boyutu | 1801 karakter | 995 karakter |
| Doğru cevaplanan | 6/6 | 6/6 |
| Doğru "bilmiyorum" | 2/2 | 2/2 |
| Ortalama gecikme | 28.3s | 16.2s |
| Medyan gecikme | 33.3s | **21.0s** |
| En yavaş | 49.9s | 22.9s |
| Kapsam içi skor aralığı | 0.425 – 0.602 | **0.480 – 0.629** |
| Kapsam dışı skor aralığı | 0.142 – 0.144 | 0.149 – 0.174 |

**Yorum.** Beklenen hız kazancı geldi (medyan %37 düştü, en yavaş soru yarıya
indi) ama asıl bulgu doğruluk tarafında: **kapsam içi benzerlik skorları
yükseldi.** Bu sezgiye aykırı görünebilir, açıklaması şu: büyük bir chunk'ta
farklı konulardaki paragraflar tek bir vektörde ortalanıyor ve sonuç "biraz her
şeye benzeyen" bulanık bir temsil oluyor. Küçük chunk tek bir konuya ait
olduğundan daha keskin bir sinyal veriyor.

Bu, çekilen kaynaklarda somut olarak görülüyor:

| Soru | Koşu 1 kaynakları | Koşu 2 kaynakları |
|---|---|---|
| Yavru aşı takvimi | vaccination-schedule, parasite-prevention | vaccination-schedule |
| Kene çıkarma | parasite-prevention, dental-and-grooming | parasite-prevention |
| Yavru kedi besleme | nutrition-and-feeding, vaccination-schedule | nutrition-and-feeding |

Koşu 1'de alakasız ikinci bir kaynak sürükleniyordu; Koşu 2'de retrieval doğru
belgede kalıyor. Kapsam dışı skorlar hafifçe yükseldi (0.144 → 0.174) ama eşiğin
(0.35) hâlâ çok altında, karar sınırı güvende.

**Sonuç: chunk boyutu bu projede yalnızca bir performans ayarı değil, doğruluk
ayarı.** İkisi aynı yönde iyileşti, yani takas yok.

---

## Koşu 2b — Tekrarlanabilirlik

Koşu 2 ayarları değiştirilmeden ikinci kez çalıştırıldı (ilk denemede
`TOP_K` değişikliği kaydedilmemişti; kaza eseri faydalı bir ölçüm oldu).

| Metrik | Koşu 2 | Koşu 2b | Fark |
|---|---|---|---|
| Ortalama | 16.2s | 16.3s | +0.1s |
| Medyan | 21.0s | 20.0s | −1.0s |
| En yavaş | 22.9s | 23.9s | +1.0s |

Doğruluk ve çekilen kaynaklar birebir aynı — retrieval deterministik, tek
değişkenlik üretim süresinde.

**Ders:** Aynı ayarla ölçüm gürültüsü yaklaşık **±1 saniye**. Sonraki
karşılaştırmalarda bu eşiğin altındaki farklar anlamlı sayılmadı.

---

## Koşu 3 — TOP_K 3 → 2

Gerekçe: bağlamı üçte bir daha kısaltır. Risk, birden fazla belgeden bilgi
birleştiren soruların bozulması ("çikolata" sorusu üç kaynaktan çekiyordu).

| Metrik | Koşu 2b | Koşu 3 |
|---|---|---|
| Doğru cevaplanan | 6/6 | 6/6 |
| Doğru "bilmiyorum" | 2/2 | 2/2 |
| Ortalama gecikme | 16.3s | 12.8s |
| Medyan gecikme | 20.0s | **15.7s** |
| En yavaş | 23.9s | 20.5s |

**Yorum.** Medyan 4.3 saniye düştü — ölçüm gürültüsünün (±1s) belirgin biçimde
üstünde, yani gerçek bir kazanç. Doğrulukta kayıp yok.

Endişe edilen senaryo gerçekleşmedi: birden fazla belgeden bilgi birleştiren
çikolata sorusu üç kaynaktan ikiye indi ama cevap aynı kaldı, çünkü kritik bilgi
(theobromine, köpekler için toksik) zaten en yüksek skorlu iki chunk'ta
bulunuyordu. Üçüncü chunk teyit ediyordu, bilgi eklemiyordu.

Genel olarak Koşu 2'deki chunk küçültme işi bu değişikliği mümkün kıldı: chunk'lar
tek konuya odaklandığı için 2 tanesi, eskiden 3 büyük chunk'ın taşıdığı bilgiyi
taşıyor.

### Buraya kadarki toplam

| | Başlangıç | Şimdi | Değişim |
|---|---|---|---|
| Medyan gecikme | 33.3s | 15.7s | **−53%** |
| En yavaş soru | 49.9s | 20.5s | −59% |
| Kapsam içi doğruluk | 6/6 | 6/6 | değişmedi |
| Kapsam dışı doğruluk | 2/2 | 2/2 | değişmedi |

İki ayar değişikliğiyle (chunk 350→200, top_k 3→2) gecikme yarıdan fazla düştü
ve doğruluk korundu. Model değiştirilmedi, donanım değiştirilmedi.

---

## Koşu 4 — Daha küçük sohbet modeli

`phi-3.5-mini` (3.8B) yerine `qwen2.5-1.5b-instruct`.

Gerekçe: parametre sayısı CPU'da süreyi neredeyse doğrusal etkiliyor. Beklenti
belirgin hızlanma, olası bedel cevap kalitesinde düşüş. Ölçmeden karar
verilemez.

| Metrik | phi-3.5-mini | qwen2.5-1.5b |
|---|---|---|
| Doğru cevaplanan | | |
| Medyan gecikme | | |

**Yorum.**

---

## Denenip geri alınan: frequency_penalty

İlk uçtan uca testte `phi-3.5-mini` doğru cevabı verdikten sonra tekrar
döngüsüne girip `000000...` üretti. Çözüm olarak `frequency_penalty=0.6` ve
`presence_penalty=0.2` eklendi.

`scripts/probe_settings.py` ile her ayar tek tek ölçüldüğünde bu parametrelerin
**kabul edildiği ama çıktı kalitesini bozduğu** görüldü. "Name three colours"
sorusuna verilen cevap:

```
frequency_penalty=0.6  ->  "three colours are three. Name three colours are th"
top_k=40               ->  "1. Red 2. Blue 3. Yellow"
```

Ayrıca uzun bağlamla birlikte kullanıldığında `Operation was cancelled` hatası
alındı. Her ikisi de kaldırıldı; tekrar kontrolü `top_k=40` ve `max_tokens=256`
ile, ayrıca system prompt'a eklenen "en fazla dört cümle" kuralıyla sağlanıyor.

**Ders:** SDK bir parametreyi kabul ediyor olması, altındaki runtime'ın onu
anlamlı biçimde uyguladığı anlamına gelmiyor. Ölçmeden parametre eklenmemeli.
