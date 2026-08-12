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
| Chunk sayısı | 12 | |
| Doğru cevaplanan | 6/6 | |
| Doğru "bilmiyorum" | 2/2 | |
| Medyan gecikme | 33.3s | |

**Yorum.**

---

## Koşu 3 — TOP_K 3 → 2

Gerekçe: bağlamı üçte bir daha kısaltır. Risk, birden fazla belgeden bilgi
birleştiren soruların bozulması ("çikolata" sorusu üç kaynaktan çekiyordu).

| Metrik | Koşu 2 | Koşu 3 |
|---|---|---|
| Doğru cevaplanan | | |
| Medyan gecikme | | |

**Yorum.**

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
