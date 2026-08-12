# Değerlendirme Sonuçları

Tarih: 2026-08-12 20:39

Ayarlar: `chunk_size=200 overlap=30 top_k=3 max_tokens=256 threshold=0.48`
Külliyat: 44 chunk / 6 kaynak
Model: `phi-3.5-mini` + `qwen3-embedding-0.6b`

## Özet

| Metrik | Sonuç |
|---|---|
| Retrieval isabeti (doğru kaynak top-3'te) | 17/17 |
| Cevaplanması gerekeni cevapladı | 17/17 |
| Reddetmesi gerekeni reddetti | 6/6 |
| Ortalama gecikme | 10.6s |
| Medyan gecikme | 13.9s |

## Benzerlik skorları

| Grup | En düşük | En yüksek | Ortalama |
|---|---|---|---|
| Cevaplanabilir | 0.548 | 0.785 | 0.661 |
| Cevaplanamaz | 0.165 | 0.427 | 0.354 |

Karar payı: en düşük cevaplanabilir skor ile en yüksek cevaplanamaz skor arasında **+0.121**. Eşik 0.48.

## Başarısızlıklar (0)

Yok.
## Tüm sorular

| # | Soru | Skor | Retrieval | Davranış | Süre |
|---|---|---|---|---|---|
| 1 | How many DHPP doses does a puppy need before sixteen weeks? | 0.608 | ok | ok | 14.0s |
| 2 | When should my kitten get its first rabies shot? | 0.634 | ok | ok | 12.6s |
| 3 | My dog's face swelled up after a vaccine. What should I do? | 0.701 | ok | ok | 12.1s |
| 4 | Does my indoor cat need the FeLV vaccine? | 0.751 | ok | ok | 15.6s |
| 5 | My dog's belly is swollen and he keeps trying to vomit but nothing comes out. | 0.785 | ok | ok | 14.0s |
| 6 | Is open-mouth breathing normal for a cat? | 0.721 | ok | ok | 12.0s |
| 7 | What should I do if my dog ate a lily? | 0.618 | ok | ok | 14.4s |
| 8 | How can I tell if my dog is a healthy weight? | 0.548 | ok | ok | 14.2s |
| 9 | How do I switch my cat to a new food without upsetting her stomach? | 0.640 | ok | ok | 13.6s |
| 10 | Is xylitol dangerous for dogs? | 0.684 | ok | ok | 14.3s |
| 11 | My cat hasn't eaten for two days. Should I worry? | 0.685 | ok | ok | 12.2s |
| 12 | My dog is drinking a lot more water than usual. | 0.647 | ok | ok | 15.0s |
| 13 | How often should I worm an adult dog? | 0.646 | ok | ok | 14.3s |
| 14 | I treated my cat for fleas but they came back. Why? | 0.619 | ok | ok | 18.0s |
| 15 | Can I use my dog's flea treatment on my cat? | 0.692 | ok | ok | 15.1s |
| 16 | Can I brush my dog's teeth with my own toothpaste? | 0.677 | ok | ok | 15.1s |
| 17 | My dog has a big mat behind his ear. Should I cut it out? | 0.579 | ok | ok | 13.9s |
| 18 | How do I train my puppy to sit? | 0.419 | - | ok | 0.6s |
| 19 | Which dog breed is best for an apartment? | 0.411 | - | ok | 0.5s |
| 20 | How much does it cost to neuter a cat? | 0.427 | - | ok | 0.5s |
| 21 | How long do indoor cats usually live? | 0.426 | - | ok | 0.5s |
| 22 | What is the capital of France? | 0.275 | - | ok | 0.5s |
| 23 | Who won the World Cup in 1998? | 0.165 | - | ok | 0.5s |
