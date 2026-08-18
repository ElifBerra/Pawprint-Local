# Değerlendirme

Ölçümler `python -m scripts.bench` ile alındı. Sabit 8 soruluk set: 6'sı
belgelerden cevaplanabilir, 2'si kapsam dışı. Donanım: Windows.

**Koşu 1-10 CPU'da alındı.** O sırada makinede GPU olmadığını sanıyorduk;
`generic-cpu` varyantıyla çalışıyorduk. Bunun neden yanlış olduğu ve gecikme
rakamlarının nereye gittiği **Koşu 11**'de. Koşu 1-10 arasındaki karşılaştırmalar
kendi içinde geçerli — hepsi aynı donanımda, tek değişkenle alındı — ama mutlak
saniyeler artık geçerli değil.

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

## Koşu 7 — Hayvan kayıtları prompt'a girdiğinde

Kişiselleştirme eklendikten sonra `bench.py` hâlâ `pet=None` ile çalışıyordu;
yani **kimsenin kullanmadığı bir yolu ölçüyorduk.** Arayüz her soruda hayvanın
kayıtlarını da gönderiyor. Bench düzeltilip iki yol yan yana ölçüldü.

| | Kayıtsız | Kayıtlarla |
|---|---|---|
| Medyan | 15.2s | **67.9s** |
| Ortalama | 12.1s | 80.4s |
| En yavaş | 21.3s | 123.4s |
| Hata | 0 | **2** |
| Kapsam dışı doğru | 2/2 | **1/2** |

Dört buçuk kat yavaşlama, iki zaman aşımı ve bir korrektlik hatası.

### Sebep prompt uzunluğu değildi

İlk tahmin bağlamın büyümesiydi (594 karakter kayıt bloğu). Ama kayıt bloğu
prompt'u yaklaşık %30 büyütüyor, süre 4.5 kat artıyordu. Rakamlar tutmuyordu.

Cevaplara bakınca görüldü: kayıtlar varken model **her soruda token tavanına
dayanıyordu.** Konuşacak daha çok şeyi vardı ve durması için sebep yoktu.
Ayrıca prompt'un iç etiketlerini tekrarlıyordu — *"According to the REFERENCE
document [emergency-signs.md]..."*

| Değişiklik | Gerekçe |
|---|---|
| `MAX_TOKENS` 256 → 180 | Üretilen token sayısı asıl maliyetti |
| "en fazla beş cümle" → "en fazla üç cümle" | Beş izni verilince beş yazıyordu |
| Bölüm adlarını anmak yasaklandı | Prompt yapısı kullanıcıya sızıyordu |

| | Önce | Sonra |
|---|---|---|
| Medyan | 67.9s | **15.6s** |
| Ortalama | 80.4s | 14.6s |
| En yavaş | 123.4s | 19.6s |
| Hata | 2 | **0** |

Kayıtları prompt'a koymanın gecikme bedeli **sıfıra indi** — kayıtsız yolla
(15.2s) eşitlendi.

### Prompt bir güvenlik sınırı değil

Bir hata kaldı: *"Who won the World Cup in 1998?"* sorusu belge eşiğini
geçemiyordu (0.165) ama hayvanın kayıtları olduğu için model yine çağrılıyor ve
**"France won the FIFA World Cup in 1998"** cevabı geliyordu.

Prompt sertleştirildi. İşe yaramadı:

> "Tek bildiğin şey aşağıdaki kayıtlar. Başka hiçbir bilgin yok. Veteriner
> bilgisi yok, genel bilgi yok, dünya hakkında hiçbir şey bilmiyorsun."

Model 1998'de Fransa'nın kazandığını biliyor ve söylüyor. **Bir modele
"bilmiyormuş gibi yap" demek, mimariye "sorma" demekten zayıf.**

Aynı ders Türkçe bölümünde de çıkmıştı: İngilizce prompt'a "Türkçe yaz"
talimatı eklemek işe yaramamış, promptu tamamen Türkçe yazmak gerekmişti.

### Çözüm: aynı mekanizmayı ikinci kez uygulamak

Belgeler için eşik vardı, kayıtlar için yoktu. Kayıtların **ne hakkında
olduğu** bir cümleye çevrilip embed ediliyor ("kilo, hedef kilo, mama, porsiyon,
protein, dışkı, aşı"), soru ona karşı ölçülüyor. Eşiğin altındaysa model hiç
çağrılmıyor.

`PET_SIM_THRESHOLDS = {"en": 0.32, "tr": 0.20}` — belge eşiğinden düşük, çünkü
soruyu düzyazıyla değil bir konu listesiyle karşılaştırıyor.

### Son durum

| Metrik | Sonuç |
|---|---|
| Hata | 0 |
| Kapsam dışı doğru | **2/2** |
| Medyan | 16.6s |
| Ortalama | 14.1s |
| "Dünya Kupası" | **0.6s** — model çağrılmadı |
| "Fransa'nın başkenti" | 7.6s — kayıt eşiğini geçti, model doğru reddetti |

İki katmanlı savunma: biri soruyu modele hiç göndermiyor, diğeri gönderilenler
için ret talimatı veriyor. İkincisi tek başına yetmiyordu.

---

## Koşu 8 — Kısa sorularda retrieval kaybı

Arayüzde gerçek kullanımda ortaya çıktı. Kullanıcı **"can i give chocolate"**
yazdı ve sistem reddetti — oysa çikolata belgelerde var ve değerlendirme
setinde aynı konu 0.615 ile geçiyordu.

Fark, değerlendirme setindeki sorunun **"Can I give my dog chocolate?"** olması.
İki kelime eksikti.

| Sorgu | Skor |
|---|---|
| `Can I give my dog chocolate?` | 0.615 |
| `is chocolate bad for cats` | 0.598 |
| `can i give my cat chocolate` | 0.523 |
| `can i give chocolate` | **0.446** — eşiğin altında |
| `chocolate` | 0.378 |

**Bulgu: eşik düzgün kurulmuş sorularla ayarlandı, gündelik yazımda kırılgan.**
Değerlendirme setini biz yazdık ve tam cümleler kurduk. Kullanıcı kısa yazıyor
ve kendisi için apaçık olanı — hangi hayvandan bahsettiğini — atlıyor.

### Denenen ve reddedilen: eşiği düşürmek

İlk çözüm eşiği 0.48'den 0.44'e çekmekti. Reddedildi, çünkü karar payını
yok ediyor:

| | Kapsam içi en düşük | Kapsam dışı en yüksek | Pay |
|---|---|---|---|
| Eşik 0.48 | 0.548 | 0.427 | +0.121 |
| Eşik 0.44 | 0.446 | 0.427 | **+0.019** |

0.019'luk bir payla yeni bir kapsam dışı soru rahatlıkla sızar.

### Uygulanan: sorguyu hayvanın bağlamıyla tamamlamak

Türü zaten biliyoruz — profilde duruyor. Kullanıcı "çikolata verebilir miyim?"
derken kendi hayvanını kastediyor. Tür (ve 12 aydan küçükse "kitten"/"puppy")
**embedding'e giden metne** ekleniyor. Modele giden soru değişmiyor.

| Soru | Önce | Sonra | Fark |
|---|---|---|---|
| `can i give chocolate` | 0.446 | **0.537** | +0.091 |
| `when are the shots due` | 0.441 | **0.549** | +0.109 |
| `chocolate` | 0.378 | 0.467 | +0.089 |
| `is this urgent` | 0.482 | 0.522 | +0.039 |
| `Can I give my dog chocolate?` | 0.615 | 0.604 | −0.011 |
| `is chocolate bad for cats` | 0.598 | 0.550 | −0.048 |
| `how much does neutering cost` | 0.409 | 0.460 | +0.050 |
| `who won the world cup in 1998` | 0.215 | 0.355 | +0.140 |

**İki meşru soru kurtarıldı, iki kapsam dışı soru altta kaldı.** Yeni pay:
en düşük kapsam içi 0.537, en yüksek kapsam dışı 0.460 → **+0.077**. Eşik
düşürme seçeneğinin dört katı.

Soru zaten türü içeriyorsa skor hafif düşüyor (−0.011, −0.048) — tekrar eklemek
sinyali seyreltiyor. İkisi de rahat eşiğin üstünde kaldığı için kabul edildi.

**Dürüst not:** en çok yükselen sorgu, tamamen alakasız olan Dünya Kupası oldu
(+0.140). Eşiğin epey altında ama boşluk 0.265'ten 0.125'e indi. Zenginleştirme
her şeyi biraz yukarı itiyor, sadece doğru olanları değil. Daha agresif bir
zenginleştirme (ırk, kilo, mama adı eklemek) bu payı yiyip bitirirdi.

### Doğrulama

23 soruluk set değişiklikten sonra tekrar çalıştırıldı:

| Metrik | Sonuç |
|---|---|
| Retrieval isabeti | 17/17 |
| Cevaplanması gerekeni cevapladı | 17/17 |
| Reddetmesi gerekeni reddetti | 6/6 |
| Hata | 0 |
| Medyan gecikme | 14.0s |
| Karar payı | +0.121 |

Değerlendirme seti `pet` göndermiyor, yani zenginleştirme orada devrede değil —
sonucun değişmemesi beklenen ve doğrulanan sonuç.

---

## Koşu 9 — Videoda görünen gecikme

Demo video olarak çekilecek. O yüzden ölçtüğümüz metrik yanlıştı: izleyicinin
beklediği şey toplam süre değil, **ilk kelimenin ekranda belirmesi.** Metin
akmaya başladıktan sonra süre hissedilmiyor; başlamadan önceki boşluk
hissediliyor.

| Metrik | Değer |
|---|---|
| Toplam medyan | 16.5s |
| **İlk kelimeye kadar medyan** | **13.6s** |
| İlk kelimeye kadar en kötü | 17.6s |

**Sürenin %82'si ilk kelimeden önce.** Üretim sadece ~3 saniye; geri kalanı
modelin prompt'u okuması (prefill). Streaming bu yüzden beklenen faydayı
vermiyordu — akacak metin henüz yok.

### Uygulanan: boşluğu retrieval sonucuyla doldurmak

Retrieval yarım saniyede bitiyor, üretim 13 saniye sonra başlıyor. Arada
elimizde çekilen pasajlar duruyordu ama gösterilmiyordu.

`answer_stream` artık `on_retrieved` geri çağrısı alıyor; API bunu ayrı bir
NDJSON olayı olarak yolluyor ve arayüz kaynakları **hemen** gösteriyor. Cevap
altına akıyor.

Boşluk aynı uzunlukta ama artık boş değil, ve doldurduğu şey projenin anlattığı
şeyin ta kendisi: önce arama, sonra üretim.

---

## Koşu 10 — Daha hızlı model denendi ve reddedildi

İlk kelime 13.6 saniyede geliyordu ve demo video olarak çekilecekti. En büyük
kaldıraç modeli küçültmekti: `phi-3.5-mini` 3.8 milyar parametre,
`qwen2.5-1.5b` 1.5 milyar.

Hız kazancı gerçek:

| Metrik | phi-3.5-mini | qwen2.5-1.5b |
|---|---|---|
| Medyan toplam | 16.5s | **7.2s** |
| İlk kelimeye kadar | 13.6s | **5.5s** |
| En yavaş | 22.0s | 10.7s |

**Ve kabul edilemez.** İki cevap:

> **"Can I give my dog chocolate?"**
> *"**Yes, you can give your dog chocolate.** However, dark chocolate has more
> theobromine than milk chocolate..."*

> **"What is the capital of France?"** (skor 0.363, eşiğin altında)
> *"Paris."*

Birincisi zararlı. Bir evcil hayvan sağlığı uygulamasının köpeğe çikolata
verilebileceğini söylemesi, projenin engellemek için var olduğu şeyin ta
kendisi. Üstelik doğru pasajları çekmişti — `nutrition-and-feeding.md` ve
`emergency-signs.md` kaynak olarak listelendi. Model doğru bağlamı aldı ve
tersini söyledi.

İkincisi kapsam dışı korumasını deliyor. `phi-3.5-mini` aynı soruyu aynı
promptla doğru şekilde reddediyor; bu model talimatı hiç dinlemiyor.

**Karar: `phi-3.5-mini` kalıyor.** 2.3 kat hız, güvenlik karşılığında satın
alınamaz.

Bu ölçüm projenin genel tasarım ilkesini de doğruluyor: modele önemli işleri
yaptırmamak doğru karardı. Kural motoru ve eşikler model değişse de aynı
davranıyor; model değiştiğinde bozulan tek şey modelin kendi cevapları oldu.

### Hız için kalan yollar

Model değişmediğine göre gecikme kabul edilmiş bir kısıt. Hafifletmeler:

- **Retrieval sonucunu hemen göstermek** (uygulandı) — bekleme aynı uzunlukta
  ama boş değil
- **Demo öncesi ısıtma sorusu** — ilk sorgu modeli belleğe alıyor
- **Makineyi boşaltmak** — ekran kaydı ve görüntülü görüşme süreyi katlıyor

---

## Koşu 11 — Kayıtsız execution provider

Projenin en pahalı gözden kaçırması.

`check_env.py` ilk günden beri şunu yazıyordu:

```
Execution providers (2):
  name='CUDAExecutionProvider'    is_registered=False
  name='WebGpuExecutionProvider'  is_registered=False
```

"GPU yok, CPU'da çalışıyoruz, normal" diye okuduk ve devam ettik. `phi-3.5-mini`
için katalog tek varyant gösteriyordu — `generic-cpu` — bu da yorumu
doğruluyordu.

**Yanlıştı.** Foundry Local, kataloğunda yalnızca **kayıtlı** execution
provider'lara ait varyantları gösteriyor. Kayıt yapılmadığı için GPU sürümü
görünmüyordu; yoktu değil, görünmüyordu.

Kayıt tek çağrı ve iki saniye sürüyor:

```python
manager.download_and_register_eps()
```

Sonrasında katalog değişti:

```
Phi-3.5-mini-instruct-cuda-gpu:2     ← yeni
Phi-3.5-mini-instruct-generic-cpu:2  (cached)
```

Makinede NVIDIA kartı varmış. İki hafta boyunca bilmiyorduk.

### Etki

| Metrik | CPU | GPU | Kat |
|---|---|---|---|
| **İlk kelimeye kadar (medyan)** | 13.6s | **0.4s** | **34×** |
| Toplam medyan | 16.5s | **1.2s** | 14× |
| Ortalama | 14.7s | 1.0s | 15× |
| En yavaş | 22.0s | 1.5s | 15× |
| Hata | 0 | 0 | — |
| Doğruluk | 8/8 | 8/8 | değişmedi |

### İlk çağrı sorunu

GPU'ya geçince iki yeni belirti çıktı: ilk embedding çağrısı
`Operation was cancelled` ile patlıyor, ilk cevap 64 saniye sürüyordu —
sonrakiler bir saniye.

Sebep: modeller yükleniyordu ama **hiç çalıştırılmıyordu.** Çalışma zamanı bir
şeyleri ilk kullanımda tembel kuruyor ve o bedeli ilk isteği yapan ödüyor.

İki düzeltme:

- `foundry.warm_up()` artık her iki modelden birer istek geçiriyor. Ölçülen
  ısınma: embedding 1.1s, sohbet 0.4s.
- `embeddings.py` ilk çağrı iptal edilirse bir kez daha deniyor. Isınma normal
  durumu kapatıyor; bu da geri kalanı.

Sonuç: 8 soruda 0 hata, ilk soru dahil hepsi 1.5 saniyenin altında.

### Ders

Bu bulgudan sonra önceki altı ayar koşusuna yeniden bakmak gerekiyor. Chunk
boyutunu 350'den 200'e düşürmek, `top_k`'yı ayarlamak, `max_tokens`'ı kısmak,
prompt'u kısaltmak — hepsi gerçek kazanç sağladı ve toplamda medyanı 33.3
saniyeden 13.3'e indirdi. **Yaklaşık 2.5 kat.**

Gözden kaçırdığımız iki satırlık çağrı **14 kat** getirdi.

Ayar çalışması boşa gitmedi: chunk küçültme aynı zamanda **doğruluğu** artırdı
(kapsam içi skorlar 0.425-0.602'den 0.480-0.629'a çıktı) ve o kazanç
donanımdan bağımsız. Ama gecikme tarafındaki emeğin büyük kısmı, platformun
zaten sunduğu bir yeteneği kullanmadığımız için harcandı.

**Ders: bir platformun etrafında optimizasyon yapmadan önce platformun ne
sunduğunu kontrol et.** Teşhis çıktısı iki hafta boyunca `is_registered=False`
yazdı; okuduk ve yanlış yorumladık.

### CPU hâlâ destekleniyor

`PREFER_GPU = False` ile CPU'ya dönülüyor, `scripts/bench.py --cpu` ile
karşılaştırılabiliyor. GPU varyantı olmayan modellerde otomatik olarak CPU'ya
düşüyor. Yani proje GPU'suz makinelerde de çalışıyor — sadece daha yavaş, ve
yukarıdaki bütün CPU ölçümleri o senaryo için geçerli.

---

## Koşu 12 — Doğru sayılar, yanlış yön

Demo provasında yakalandı. Değerlendirme setinde olmayan bir soru:

> **Should I reduce Khaleesi's portion?**
>
> *Yes, based on the reference material, if the ribs cannot be felt easily under
> a thin layer of fat, the portion size should be reduced. Since Khaleesi's
> current weight is 10.0 kg, which is 2.5 kg below the target weight, it
> suggests that her portion size may need adjustment. Reassess in a month after
> reducing the daily amount by roughly ten percent.*

Khaleesi hedefinin **2.5 kg altında.** Cevap "azalt" diyor.

**Bu bir retrieval hatası değil.** Doğru belgeler geldi, kayıtlar prompt'a
girdi, model sayıyı doğru okudu ve *"2.5 kg below the target weight"* diye
kendisi yazdı. Sonra genel bir kuralı ("kaburgalar hissedilmiyorsa azalt")
farkın hangi yöne olduğuna bakmadan uyguladı.

Prompt'taki her bilgi doğruydu. Eksik olan bir bilgi değil, bir **karar**dı.

### Neden bu sınıf hata önemli

Reddetme hatalarından farklı. Kapsam dışı bir soruya uydurma cevap veren model
zararsızdır — kullanıcı saçmalığı görür. Burada cevap akıcı, kaynaklı, sayıları
doğru ve **zayıf bir hayvanın yemeğini azaltmayı öneriyor.** Kullanıcının
yanlışlığı fark etmesi için zaten bilmesi gerekiyor.

### Çözüm

Yönü karşılaştırma belirliyor, o hâlde kararı da karşılaştırma versin.
`pet_context.feeding_direction()` kayıtlardan tek bir satır üretiyor:

```
FEEDING DIRECTION: this animal is UNDER its target weight. Reducing the
amount of food would be wrong. Any advice must keep the amount the same or
increase it, and a weight this far below target is worth raising with a vet.
```

Model artık yönü çıkarmıyor, cümleyi kuruyor. Aynı iş bölümü `insights.py`'de
zaten vardı — aritmetiği kural yapar, model anlatır. Bu sefer beslenme yönü de
o tarafa geçti.

Ek olarak `SYSTEM_PROMPT_WITH_PET`'e tek kural eklendi: REFERANS genel olarak
hayvanları anlatır, bu hayvanın hedefine göre ne tarafta olduğunu bilemez.

Kural motorunda buna çok benzeyen bir uzlaştırma zaten vardı (kilo alan ve hedef
üstündeki hayvana "daha çok ver" dememek). Aynı hatayı ikinci kez, başka bir
yoldan yaptık — RAG cevabında. Kural motoruna koyduğumuz korumanın modele
verdiğimiz prompt'ta olmadığını fark etmemiştik.

`tests/test_pet_context.py` — 11 test, dördü doğrudan bu yönü sabitliyor.

**Ders: modelin doğru sayıyı yazması, o sayıdan doğru sonucu çıkardığı anlamına
gelmiyor.** Bu cevap prova olmasa videoya girecekti.

---

## Türkçe desteği — ölçüm ve karar

Arayüzün Türkçe olması istendi. Belge koleksiyonu İngilizce. İki ayrı soru
vardı ve ayrı ayrı ölçüldü: **Türkçe soru İngilizce belgeyi bulabiliyor mu**, ve
**model Türkçe cevap yazabiliyor mu**. Sonuç: birincisi evet, ikincisi hayır.

### Çapraz dilli retrieval — çalışıyor, ama kalibrasyon gerekiyor

`scripts/probe_crosslingual.py`, sekiz soruyu hem Türkçe hem İngilizce sorup
skorları karşılaştırıyor.

| | Kapsam içi en düşük | Kapsam içi ortalama | Kapsam dışı en yüksek | Karar payı |
|---|---|---|---|---|
| İngilizce | 0.504 | 0.658 | 0.419 | +0.085 |
| Türkçe | 0.293 | 0.343 | 0.250 | +0.042 |

Doğru belge bulunma oranı: **Türkçe 7/8, İngilizce 8/8.** Yani `qwen3-embedding-0.6b`
Türkçe soruyu İngilizce pasajla eşleştirebiliyor. Ama aynı anlamdaki soru
Türkçe sorulduğunda skor sistematik olarak **~0.30 düşük** çıkıyor.

Bunun pratik sonucu ağırdı: tek eşik (0.48) kullanılırken Türkçe kapsam içi
soruların **8/8'i** modele hiç ulaşmadan reddediliyordu. Sorun anlama değil,
kalibrasyondu.

Çözüm dile göre eşik: `SIM_THRESHOLDS = {"en": 0.48, "tr": 0.27}`.

Dürüst not: Türkçe karar payı (+0.042) İngilizcenin (+0.085) yarısı kadar.
Yani Türkçede kapsam dışı tespiti ölçülebilir biçimde daha kırılgan.

### Üretim — dört model denendi, hiçbiri geçmedi

Kabul kriteri baştan konuldu: 5 soruda 0 hata, medyan < 25s, okunabilir Türkçe
ve pire sorusunda permethrin uyarısının net verilmesi.

| Model | Hata | Medyan | Gözlem |
|---|---|---|---|
| `phi-3.5-mini` | 3/5 | 65s | Bozuk dilbilgisi: *"Bella'nin aktual yedi bardak Acme Premium yiyen yedi gün boyunca..."* |
| `qwen3-1.7b` | 1/5 | 44s | `<think>` bloğunda İngilizce düşünüyor, token bütçesi bitiyor, cevap hiç gelmiyor |
| `qwen3-4b` | 3/5 | 59s | Aynı davranış, daha yavaş |
| `qwen2.5-1.5b` | 3/5 | 76s | Uydurma kelimeler: *"cıkçatalar biraz azetli ve çok zengin"* |

Ara bulgu: İngilizce prompt'a "cevabı Türkçe yaz" talimatı eklemek, prompt'un
tamamını Türkçe yazmaktan belirgin daha kötü. Model okuduğu dil ile yazması
istenen dil arasında savruluyor. Bu yüzden `SYSTEM_PROMPT_TR` çeviri değil,
Türkçe yazılmış ayrı bir şablon. Yine de tek başına yetmedi.

Qwen3'ün düşünme modu `/no_think` ile kapatılmaya çalışıldı (hem sistem hem
kullanıcı mesajında). Foundry Local'ın ONNX derlemesi bu yumuşak anahtarı
tanımıyor.

Tekrarlayan `Operation was cancelled` hatası da rastgele değil: Türkçe üretim
uzadıkça ortaya çıkıyor. Türkçe bu modellerin kelime dağarcığında çok daha
fazla token'a bölünüyor.

### Karar

**Arayüz Türkçe, cevaplar İngilizce.** `EXPERIMENTAL_TURKISH_ANSWERS = False`.

Türkçe promptlar ve dile göre eşik kod tabanında kalıyor — çalışıyorlar, ölçüm
onlara karşı yapıldı, ve daha güçlü bir yerel model çıktığında bu tek satırlık
bir değişiklik olur.

Bu bir eksiklik değil, ölçülmüş bir sınır. Retrieval katmanının çok dilli
çalıştığı, üretim katmanının çalışmadığı ayrı ayrı gösterildi. Çalışmayan bir
Türkçe modunu arayüze koymak, kullanıcıya *"cıkçatalar biraz azetli"* gibi bir
sağlık tavsiyesi göstermek olurdu.

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
