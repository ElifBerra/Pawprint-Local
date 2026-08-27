# Sunum notu

Konuşarak anlatmak için yazıldı, okumak için değil. Cümleler kısa çünkü
ezberlenmiyor, hatırlanıyor.

Video oynarken anlatılacak. Slayt yok.

---

## Tek cümle

> RAG'ı kurmak kolaydı. Doğru çalıştırmak, modele güvenmeyi bırakmakla oldu.

Başka hiçbir şey söyleyemeyecek olsan bunu söyle.

---

## Üç dakikalık anlatı

Üç perde. Her biri aynı şekilde ilerliyor: bir hata, prompt'la düzeltme
denemesi, işe yaramaması, mimariyle çözülmesi.

### Perde 1 — Model uyduruyordu

*"1998 dünya kupasını kim kazandı?"* diye sordum. Cevap verdi.

Prompt'a yazdım: "Senin genel bilgin yok. Sadece bu belgeleri biliyorsun."
Yine cevap verdi. Daha sert yazdım. Yine cevap verdi.

**Prompt bir güvenlik sınırı değil.** Model o bilgiyi biliyor ve söylüyor.

Çözüm modele söylemek değildi. Soruyu belgelere karşı puanlıyoruz; skor eşiğin
altındaysa **model hiç çağrılmıyor.** Reddetme artık modelin kararı değil, kod
akışı.

Yan fayda: kapsam dışı soru 16 saniye yerine sıfır saniyede reddediliyor.

### Perde 2 — Doğru sayılar, yanlış sonuç

Demo provasında yakaladım. Sordum: *"Khaleesi'nin porsiyonunu azaltmalı mıyım?"*

Cevap: *"Evet, azaltılmalı. Khaleesi 10 kilo, hedefin 2.5 kilo altında..."*

Kedi hedefinin **altında.** Model sayıyı doğru okudu, hatta "2.5 kilo altında"
diye kendi yazdı. Sonra belgedeki genel kuralı — "kaburgalar hissedilmiyorsa
azalt" — farkın hangi yöne olduğuna bakmadan uyguladı.

Prompt'taki her bilgi doğruydu. Eksik olan bilgi değil, **karardı.**

Yön bir karşılaştırma. O hâlde kararı da karşılaştırma versin: kurallar
kayıtlara bakıp "bu hayvan hedefinin altında, azaltma önerilemez" satırını
üretiyor, model sadece cümleyi kuruyor.

Bu ayrımın adı var ve projenin her yerinde: **aritmetiği kural yapar, model
anlatır.**

> Rahatsız edici kısmı: kural motorunda buna neredeyse birebir aynı bir koruma
> zaten vardı. Aynı hatayı ikinci kez, başka bir kapıdan yaptık.

### Perde 3 — Ölçmediğimiz şeyi ayarlamış sanıyorduk

Videoda Türkçe bir soru reddediliyor: *"selam, kedim kaç aylık"*. Aynı soru
İngilizce sorulunca cevap geliyor: *"10 months old"*.

Peşine düşünce çok daha kötü bir şey çıktı. Değerlendirme setimiz 23 soruluk ve
"6/6 reddetti" diyor. Ama `run_eval.py` içinde hayvan hiç yok — **ikinci kapı o
değerlendirmeye hiç girmemiş.** Haftalardır ölçtüğümüzü sandığımız şeyi
ölçmüyormuşuz.

Ölçtük. Eşik *"Fransa'nın başkenti neresi"* sorusunu **0.004 farkla**
durduruyormuş.

Sonra doğru soruyu sorduk: eşik yanıldığında ne oluyor? İki ayrı sınıf çıktı:

| | modele ulaşırsa |
|---|---|
| *"Fransa'nın başkenti"* | **cevaplıyor** — hiçbir prompt tutmuyor |
| *"köpeğime oturmayı nasıl öğretirim"* | reddediyor |

Fark şu: modelin bu kedinin aşı geçmişi hakkında bir görüşü yok, orada katı
prompt tutuyor. Fransa'nın başkentini biliyor, orada tutmuyor.

Eşiği yalnızca birinci sınıfın üstüne taşıdık. İkincisini prompt hallediyor ve
bunu varsaymadık, ölçtük.

---

## Sayılar

Ezberleme, lazım olursa bak.

| | |
|---|---|
| Retrieval isabeti | 17/17 |
| Cevaplaması gerekeni cevapladı | 17/17 |
| Reddetmesi gerekeni reddetti | 6/6 |
| Medyan gecikme | 0.9 s |
| İlk kelimeye kadar | 0.4 s |
| Kapsam dışı | 0 s (model çağrılmıyor) |
| Külliyat | 44 chunk / 6 belge |
| Test | 102 |

Karar payları — "eşik ne kadar yanılabilir":

| | pay |
|---|---|
| Belge kapısı | +0.120 |
| Kayıt kapısı (EN) | +0.125 |
| Kayıt kapısı (TR) | +0.036 |

Türkçedeki dar. Sorarlarsa dürüst cevap: *"Farkındayız, `config.py`'de not
düşülü, bugün çalışıyor ama ilk kırılacak yer orası."*

---

## Foundry Local kısmı

Ayrı bir hikâye, ayrı anlat. **Gecikmeyi 14 kat düşüren şey iki satırdı.**

Teşhis çıktısı iki hafta boyunca `is_registered=False` yazdı. "GPU yok" diye
okuduk. Katalog da her model için tek bir CPU sürümü gösteriyordu, bu da yorumu
doğruluyor sandık.

İkisi de aynı şeyin sonucuymuş: **Foundry Local yalnızca kayıtlı execution
provider'lara ait model varyantlarını gösteriyor.** GPU sürümü yok değildi,
görünmüyordu.

```python
manager.download_and_register_eps()
```

İki saniye sürdü.

| | CPU | GPU |
|---|---|---|
| İlk kelimeye kadar | 13.6 s | **0.4 s** |
| Medyan | 16.5 s | **1.2 s** |

Altı ayar koşusunda gecikmeyi 33 saniyeden 13'e indirmiştik — 2.5 kat. Gözden
kaçırdığımız çağrı 14 kat getirdi.

> Ayar çalışması boşa gitmedi, chunk küçültme doğruluğu da artırdı ve o kazanç
> donanımdan bağımsız. Ama gecikme tarafındaki emeğin çoğu, platformun zaten
> sunduğu bir şeyi kullanmadığımız için harcandı.

**Bir platformun etrafında optimizasyon yapmadan önce platformun ne sunduğunu
kontrol et.**

---

## Gelebilecek sorular

**"Neden bu kadar küçük bir model?"**
Çevrimdışı çalışması şart. Daha büyük modeli denedik değil — daha hızlısını
denedik. `qwen2.5-1.5b` 2.3 kat hızlıydı ve doğru pasajları görmesine rağmen
*"Evet, köpeğinize çikolata verebilirsiniz"* dedi. Hız için güvenlik verilmez.

**"Türkçe neden cevap üretmiyor?"**
5 model denedik, hiçbiri geçmedi. Çıktı bozuk: *"Bella'nin aktual yedi bardak
Acme Premium yiyen yedi gün boyunca..."* Kapattık ve `EVALUATION.md`'ye
yazdık. Arayüz, içgörüler ve vet raporu tamamen Türkçe — çünkü onları model
yazmıyor, kurallar yazıyor.

**"Neden kural motoru? Model yazsın."**
Bu bulgular kullanıcının aksiyon alacağı uyarılar üretiyor — "porsiyonu azalt",
"veterinere göster". Her açılışta aynı çıkması gerekiyor. Küçük bir model bunu
garanti edemez. Perde 2 tam olarak bunun örneği.

**"Vektör veritabanı neden yok?"**
44 chunk için tüm embedding'leri belleğe alıp tek matris çarpımı yapmak bir
milisaniyenin altında. Yaklaşık 10.000 chunk'a kadar taşır, ötesinde ANN
indeksi gerekir. Ölçtük, yazdık.

**"Bu hatalar neden raporda duruyor?"**
Çünkü hepsi ölçümle bulundu ve ölçümle düzeltildi. Bulunmamış bir hata
raporda olmayan bir hata değil, sadece görünmeyen bir hata.

---

## Anlatırken

- Perde 2'yi atlama. Videoda görünmüyor ama en iyi kısım o.
- "Prompt bir güvenlik sınırı değil" cümlesini bir kez net söyle, tekrarlama.
- Sayıları ekrandan okuma; biri sorarsa söyle.
- Hataları savunma diline kaydırma. "Yakaladık, ölçtük, düzelttik" yeter.
