# Değerlendirme Sonuçları

Tarih: 2026-08-18 17:20

Ayarlar: `chunk_size=200 overlap=30 top_k=3 max_tokens=180 threshold=0.48`
Külliyat: 44 chunk / 6 kaynak
Model: `phi-3.5-mini` + `qwen3-embedding-0.6b`

## Özet

| Metrik | Sonuç |
|---|---|
| Retrieval isabeti (doğru kaynak top-3'te) | 17/17 |
| Cevaplanması gerekeni cevapladı | 17/17 |
| Reddetmesi gerekeni reddetti | 6/6 |
| Ortalama gecikme | 0.9s |
| Medyan gecikme | 1.0s |

## Benzerlik skorları

| Grup | En düşük | En yüksek | Ortalama |
|---|---|---|---|
| Cevaplanabilir | 0.547 | 0.785 | 0.661 |
| Cevaplanamaz | 0.165 | 0.428 | 0.354 |

Karar payı: en düşük cevaplanabilir skor ile en yüksek cevaplanamaz skor arasında **+0.120**. Eşik 0.48.

## Başarısızlıklar (0)

Yok.
## Tüm sorular

| # | Soru | Skor | Retrieval | Davranış | Süre |
|---|---|---|---|---|---|
| 1 | How many DHPP doses does a puppy need before sixteen weeks? | 0.608 | ok | ok | 2.0s |
| 2 | When should my kitten get its first rabies shot? | 0.634 | ok | ok | 0.6s |
| 3 | My dog's face swelled up after a vaccine. What should I do? | 0.701 | ok | ok | 0.8s |
| 4 | Does my indoor cat need the FeLV vaccine? | 0.750 | ok | ok | 1.6s |
| 5 | My dog's belly is swollen and he keeps trying to vomit but nothing comes out. | 0.785 | ok | ok | 1.1s |
| 6 | Is open-mouth breathing normal for a cat? | 0.720 | ok | ok | 1.2s |
| 7 | What should I do if my dog ate a lily? | 0.617 | ok | ok | 1.0s |
| 8 | How can I tell if my dog is a healthy weight? | 0.547 | ok | ok | 1.4s |
| 9 | How do I switch my cat to a new food without upsetting her stomach? | 0.640 | ok | ok | 1.3s |
| 10 | Is xylitol dangerous for dogs? | 0.684 | ok | ok | 1.2s |
| 11 | My cat hasn't eaten for two days. Should I worry? | 0.685 | ok | ok | 1.2s |
| 12 | My dog is drinking a lot more water than usual. | 0.647 | ok | ok | 1.4s |
| 13 | How often should I worm an adult dog? | 0.646 | ok | ok | 0.8s |
| 14 | I treated my cat for fleas but they came back. Why? | 0.619 | ok | ok | 1.8s |
| 15 | Can I use my dog's flea treatment on my cat? | 0.692 | ok | ok | 0.9s |
| 16 | Can I brush my dog's teeth with my own toothpaste? | 0.677 | ok | ok | 1.1s |
| 17 | My dog has a big mat behind his ear. Should I cut it out? | 0.578 | ok | ok | 1.0s |
| 18 | How do I train my puppy to sit? | 0.419 | - | ok | 0.0s |
| 19 | Which dog breed is best for an apartment? | 0.411 | - | ok | 0.0s |
| 20 | How much does it cost to neuter a cat? | 0.428 | - | ok | 0.0s |
| 21 | How long do indoor cats usually live? | 0.426 | - | ok | 0.0s |
| 22 | What is the capital of France? | 0.275 | - | ok | 0.0s |
| 23 | Who won the World Cup in 1998? | 0.165 | - | ok | 0.1s |
