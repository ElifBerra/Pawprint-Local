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

## Koşu 4 — Başlık sınırlı chunk'lama

Chunk'lar artık Markdown başlıklarını aşmıyor ve her chunk kendi başlık izini
(`Nutrition and Feeding > Foods that are dangerous`) taşıyor.

**Gerekçe — gerçek bir hatadan çıktı.** Çikolata sorusuna verilen cevap şuydu:

> "Chocolate contains theobromine, which is toxic to pets **and can indicate
> serious health issues like kidney disease, diabetes, or hyperadrenocorticism**."

Bu ikinci kısım `nutrition-and-feeding.md`'nin **su tüketimi** bölümünden
geliyordu; aşırı susamanın işaret ettiği hastalıklar listesi. 200 kelimelik
pencere "Water" ve "Foods that are dangerous" bölümlerini tek chunk'a
paketlemişti. Model doğru chunk'ı çekiyordu, chunk'ın kendisi iki konuluydu.

Önce prompt'a "sadece soruyu doğrudan cevaplayan cümleleri kullan" kuralı
eklendi. Bu, kene sorusundaki benzer bulaşmayı düzeltti ama çikolatayı
düzeltmedi — yani prompt katmanı yapısal bir sorunu kapatmaya yetmiyor.

| Metrik | Koşu 3 | Koşu 4 |
|---|---|---|
| Chunk sayısı | 23 | 44 |
| Ortalama chunk boyutu | 995 karakter | 472 karakter |
| Doğru cevaplanan | 6/6 | **5/6** |
| Doğru "bilmiyorum" | 2/2 | 2/2 |
| Medyan gecikme | 15.7s | 11.5s |
| Kapsam içi skor aralığı | 0.480 – 0.629 | 0.504 – 0.759 |
| Kapsam dışı en yüksek skor | 0.174 | **0.275** |

**Yorum.** Bulaşma düzeldi ve skorlar iyileşti, ama iki yeni sorun çıktı:

1. **Gerileme:** "Why does my dog have bad breath?" cevaplanamaz oldu. Sorgudaki
   "breath" kelimesi `emergency-signs.md`'nin **Breathing** bölümüyle eşleşti ve
   `TOP_K=2` ile diş belgesi listeden düştü. Chunk'lar küçüldükçe kelime düzeyi
   eşleşmeler öne çıkıyor.
2. **Daralan pay:** Kapsam dışı en yüksek skor 0.174'ten 0.275'e çıktı. Küçük
   chunk'lar ve başlık izleri taban benzerliğini yükseltiyor. Eşik 0.35 iken pay
   sadece 0.075 kalmıştı.

---

## Koşu 5 — TOP_K 3, eşik 0.40

Koşu 4'ün iki yan etkisini düzeltmek için.

`TOP_K` 3'e çıkarıldı: chunk'lar 472 karaktere indiği için 2 tanesi artık bir
konuyu kapsamıyor. `SIM_THRESHOLD` 0.40 yapıldı: en düşük kapsam içi skor 0.504,
en yüksek kapsam dışı 0.275 — 0.40 ikisinin ortasında, her iki tarafa da pay
bırakıyor.

| Metrik | Koşu 4 | Koşu 5 |
|---|---|---|
| Doğru cevaplanan | 5/6 | **6/6** |
| Doğru "bilmiyorum" | 2/2 | 2/2 |
| Ortalama gecikme | 9.7s | 10.7s |
| Medyan gecikme | 11.5s | 13.3s |
| En yavaş | 15.4s | 17.0s |

**Yorum.** Gerileme kapandı, 1.8 saniyelik gecikme artışı karşılığında.
Doğruluk için makul bir bedel.

---

## Nihai durum

8 soruluk bench (ayar turları):

| | Başlangıç | Son | Değişim |
|---|---|---|---|
| Medyan gecikme | 33.3s | 13.3s | **−60%** |
| En yavaş soru | 49.9s | 17.0s | −66% |
| Bulaşma hatası | var | yok | düzeltildi |

23 soruluk değerlendirme seti (notlandırılan koşu):

| Metrik | Sonuç |
|---|---|
| Retrieval isabeti | **17/17** |
| Cevaplanması gerekeni cevapladı | **17/17** |
| Reddetmesi gerekeni reddetti | **6/6** |
| Ortalama gecikme | 10.6s |
| Medyan gecikme | 13.9s |
| Karar payı | +0.121 |

Nihai ayarlar: `chunk_size=200 overlap=30 top_k=3 max_tokens=256 threshold=0.48`,
başlık sınırlı chunk'lama, `phi-3.5-mini` + `qwen3-embedding-0.6b`.

Model değiştirilmedi, donanım değiştirilmedi. Kazancın tamamı chunk'lama
stratejisi ve retrieval ayarlarından geldi.

---

## Koşu 6 — Tam değerlendirme seti (23 soru)

8 soruluk bench ayar turları için hızlı bir ölçüydü. Bu, notlandırılan koşu:
17 cevaplanabilir + 6 cevaplanamaz soru, `tests/eval_questions.json`.

Set kasıtlı olarak zorlaştırıldı. Cevaplanamaz soruların **dördü alan içi ama
belgelerde yok**: "yavru köpeğe otur komutu nasıl öğretilir", "apartman için
hangi ırk", "kısırlaştırma ne kadar tutar", "kedilerin ömrü ne kadar". Fransa'nın
başkenti kolay negatif; asıl test bunlar.

Belgeleri yazan kişi (Burak) ile soruları yazan kişi (Elif) ayrı tutuldu.
Belgeyi yazan, hangi soruların cevaplanabileceği konusunda kör oluyor.

### İlk koşu — eşik 0.40

| Metrik | Sonuç |
|---|---|
| Retrieval isabeti | 17/17 |
| Cevaplanması gerekeni cevapladı | 17/17 |
| Reddetmesi gerekeni reddetti | **3/6** |

**Üç başarısızlığın ikisi ölçüm hatası çıktı.** Cevaplara bakıldığında model
doğru davranmıştı:

> "I'm sorry, but the provided context does not contain information regarding
> training a puppy to sit. I don't have that information in my documents."

`_is_fallback()` cevabın *yalnızca* fallback cümlesinden ibaret olmasını
arıyordu; model başına özür eklediği için tanımadı. Sistem 23/23 doğru
davranmıştı, biz 3'ünü yanlış etiketledik.

Ham sayıya bakıp "3/6" diye rapor etseydik yanlış bir sonuç yayınlamış
olacaktık. **Ölçüm aracının kendisi de test edilmesi gereken bir bileşen.**

Ama altında gerçek bir sorun da vardı: bu üç soru eşiği aşıp (0.411-0.427 >
0.40) modele gitmişti. Doğru sonuç, yanlış sebeple — retrieval katmanı elemesi
gerekeni elememiş, model kendi sağduyusuyla kurtarmıştı. 3B'lik bir modelin
sağduyusuna yaslanmak tasarım değil, şans.

### Eşik ayarı

Skor dağılımı doğru sayıyı veriyordu:

| Grup | En düşük | En yüksek | Ortalama |
|---|---|---|---|
| Cevaplanabilir | **0.548** | 0.785 | 0.661 |
| Cevaplanamaz | 0.165 | **0.427** | 0.354 |

İki grup çakışmıyor; arada 0.121'lik temiz boşluk var. Eşik 0.40'tan **0.48**'e
çekildi — boşluğun ortası, iki tarafa da yaklaşık eşit pay.

`_is_fallback()` de genişletildi: fallback cümlesinin varlığı + uzunluk sınırı.
Özürlü ret cümlenin ~3 katı uzunlukta, cevabı gizleyen ret çok daha uzun.

### Son koşu — eşik 0.48

| Metrik | Eşik 0.40 | Eşik 0.48 |
|---|---|---|
| Retrieval isabeti | 17/17 | **17/17** |
| Cevaplanması gerekeni cevapladı | 17/17 | **17/17** |
| Reddetmesi gerekeni reddetti | 3/6 | **6/6** |
| Ortalama gecikme | 14.6s | 10.6s |
| Medyan gecikme | 15.5s | 13.9s |
| Başarısızlık | 3 | **0** |

Zor negatifler artık modele hiç gitmiyor: 14.9s → 0.6s. Ortalama gecikmedeki
4 saniyelik düşüş bundan geliyor.

**Sonuç: 23/23.** Karar payı +0.121, eşik boşluğun ortasında.

---

## Denenmedi

**Daha küçük sohbet modeli.** `qwen2.5-1.5b-instruct` (3.8B yerine 1.5B) CPU'da
belirgin hızlanma sağlardı. Gecikme kabul edilebilir seviyeye indiği için
denenmedi; cevap kalitesini riske atmaya değmedi. Daha yavaş bir donanımda ilk
başvurulacak seçenek bu olurdu.

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
