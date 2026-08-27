# Mimari anlatımı — ekran ekran

Projeyi açıp gezdirirken okunacak metin. Her başlıkta önce **ne göstereceğin**,
sonra **ne söyleyeceğin** var.

Kural: hiçbir mimari iddiayı ekranda karşılığı olmadan söyleme. "İki bilgi
kaynağı var" demek zayıf; ekranda ikisini birden gösterip söylemek güçlü.

Toplam 6-8 dakika. Sıkışırsan 5, 7 ve 8'i atla.

---

## Başlamadan

Sunucuyu önceden başlat, `Warm-up` satırını bekle, bir soru sor ve sil.
İzleyicinin ilk model yüklemesini beklemesine gerek yok.

Tarayıcı ve terminal yan yana dursun. İkisini de göstereceksin.

---

## 1 — Ne olduğu (30 sn)

**[EKRAN]** Uygulamanın ana ekranı, sol menü görünür.

> Pawprint-Local, evcil hayvan sağlığı için çevrimdışı çalışan bir asistan.
> Sol tarafta iki grup var. Üstte takip: kilo, beslenme, dışkı, aşı. Altta
> analiz: soru-cevap, içgörüler, veteriner raporu.
>
> Aradaki fark şu: üstteki bölüm veri topluyor, alttaki bölüm o veriyi
> kullanıyor. Bütün mimari bu ayrımın üzerine kurulu.

**[EKRAN]** Sol alttaki yeşil "Çevrimdışı" rozetini göster.

> Model de veri de bu bilgisayarda. Ağ bağlantısı yok, API anahtarı yok.
> İsterseniz wifi'yi kapatıp aynı soruları sorabiliriz.

---

## 2 — İki bilgi kaynağı (1 dk)

Projeyi bir belge arama kutusundan ayıran şey bu. En önemli bölüm.

**[EKRAN]** Soru-Cevap. Şunu sor:

```
is she at a healthy weight
```

**[EKRAN]** Cevap gelince altındaki etiketleri işaret et: yeşil
`kayıtlar kullanıldı` ve yanındaki dosya adları.

> Buradaki cevap iki ayrı yerden geliyor ve ekranda ikisini de görüyorsunuz.
>
> Gri etiketler belge koleksiyonundan gelen pasajlar — genel veteriner bilgisi.
> "Yetişkin kedi günde iki öğün yer" gibi. Bunlar her hayvan için aynı.
>
> Yeşil etiket ise bu hayvanın kendi kayıtları. Khaleesi'nin kilosu, hedefi,
> ne yediği. Bunlar sadece bu hayvana ait ve veritabanından geliyor.
>
> İkisi modele **ayrı etiketlerle** gidiyor. Sebebi şu: model genel bir
> kılavuzu, bu hayvana ait ölçülmüş bir veriymiş gibi sunmasın.

---

## 3 — RAG hattını görünür kılmak (1 dk)

**[EKRAN]** Cevabın altındaki **"Kullanılan pasajlar"**ı aç. Skorlar görünsün.

> RAG'ın üç adımı var: bul, ekle, üret. Genelde ilk adım görünmez. Burada
> görünür olsun istedim.
>
> Soru bir vektöre çevriliyor — 1024 boyutlu. Veritabanındaki 44 pasajın hepsi
> de aynı uzayda. Aralarındaki açıyı ölçüp en yakın üçünü alıyoruz.
>
> Ekranda gördüğünüz sayılar o benzerlik skorları. Yani cevabın nereden
> geldiğini sadece söylemiyorum, gösteriyorum.

**[EKRAN]** Sağdaki süreyi göster (≈1 sn).

> Bir saniye. Model bu bilgisayarın ekran kartında çalışıyor.

---

## 4 — Eşik: modeli hiç çağırmamak (1 dk)

**[EKRAN]** Şunu sor:

```
where is paris
```

**[EKRAN]** Cevap: *"I don't have that information in my documents."* — süre
0.0 saniye, kaynak etiketi yok.

> Dikkat edin: sıfır saniye. Diğer sorular bir saniye sürüyordu.
>
> Çünkü bu soruda model **hiç çağrılmadı.** Soru pasajlara yeterince
> yakın değil, eşiğin altında kaldı ve akış orada durdu.
>
> Bunu neden böyle yaptığımı anlatayım. Önce prompt'a yazmıştım: "senin genel
> bilgin yok, sadece bu belgeleri biliyorsun." Model yine cevaplıyordu.
> 1998 dünya kupasını kimin kazandığını biliyor ve söylüyor.
>
> Prompt bir güvenlik sınırı değil. O yüzden reddetme kararını modelden aldık,
> koda verdik.

---

## 5 — İkinci kapı (45 sn)

**[EKRAN]** Şunu sor:

```
kedim kaç aylık
```

Cevap gelmeli.

> Bu sorunun cevabı hiçbir belgede yok. Kayıtlarda var.
>
> Yani ilk kapı bu soruyu reddediyor. Ama arkasında ikinci bir kapı var: soru
> bu kez **kayıtların neyle ilgili olduğuna** karşı puanlanıyor. Kilo, yaş,
> mama, aşı. Yakınsa kayıtlarla cevaplanıyor, değilse yine model çağrılmıyor.
>
> İki kapı iki farklı işi yapıyor. Biri belgelerin kapsamını, diğeri kayıtların
> kapsamını koruyor.

**[EKRAN]** Terminale geç, `Records relevance 0.462 (limit 0.29)` satırını
göster.

> Kararı burada görebiliyorsunuz. Skor ve eşik loglanıyor.

---

## 6 — Kural motoru (1 dk)

**[EKRAN]** İçgörüler sayfası.

> Buradaki bulguların hiçbirini model yazmıyor. Hepsi saf Python.
>
> Kilo trendi, mama değişimiyle zaman örtüşmesi, porsiyonun hesaplanan
> ihtiyaca göre yeri, dışkı oranı, geciken aşı.
>
> Neden model yazmıyor: bunlar kullanıcının aksiyon alacağı uyarılar.
> "Porsiyonu azalt", "veterinere göster". Böyle bir çıktının her açılışta aynı
> olması gerekiyor. Üç milyar parametreli bir model bunu garanti edemez.
>
> İş bölümü şu: **aritmetiği kural yapar, model sadece cümle kurar.**

**[EKRAN]** Bir uyarıyı işaret et (örn. tartım hatası ya da hızlı kilo kaybı).

> Bu uyarıyı ben yazmadım, kural buldu. Aynı bulgu üç yerde birden çıkıyor:
> bu ekranda, veteriner raporunda, ve soru sorduğunuzda modele giden metinde.
> Tek kaynaktan besleniyorlar, o yüzden çelişemiyorlar.

---

## 7 — Beslenme hesabı (45 sn)

**[EKRAN]** Beslenme sayfası, günlük analiz.

> Buradaki sayılar da hesap, tahmin değil.
>
> Önce dinlenme enerjisi: 70 çarpı kilonun 0.75'inci kuvveti. Sonra hayvanın
> durumuna göre çarpan — yavru, kısır, yaşlı, kilo verme. Sonra mamanın etiket
> paneli kuru maddeye çevriliyor, çünkü nem oranı markadan markaya değişiyor.
> En sonda AAFCO'nun yayımladığı alt sınırlarla karşılaştırılıyor.
>
> Bir de şu: gram kullanıyoruz, bardak değil. Bardak hacim ölçüsü; aynı bardak
> bir mamada 80 gram, başkasında 130 gram. Enerji hesabı kütleye dayanıyor,
> hacimle yapılan hesap baştan yanlış olur.

---

## 8 — Veri (30 sn)

**[EKRAN]** Tüm Kayıtlar, ya da herhangi bir kayıt satırındaki ✎ / 🗑 butonları.

> Tek bir SQLite dosyası. İki bağımsız alan var ve aralarında bağ yok.
>
> Belge koleksiyonu silinip yeniden kurulabiliyor — `ingest --rebuild`.
> Hayvanın kayıtları ise kullanıcının verisi, o işlemden etkilenmiyor.
>
> Her kayıt üzerinde ekleme, düzeltme, silme var. Yanlış girilen bir tartım
> düzeltilebiliyor — ve düzeltilmezse kural motoru onu uyarı olarak gösteriyor.

---

## 9 — Foundry Local (1 dk)

**[EKRAN]** Terminal, açılış logları.

```
INFO src.foundry: Registered execution providers: CUDAExecutionProvider, ...
INFO src.foundry: Loading qwen3-embedding-0.6b into memory
INFO src.foundry: Loading phi-3.5-mini into memory
INFO src.foundry: Warm-up: {'embedding': 0.9, 'chat': 0.5, ...}
```

> İki model var. `phi-3.5-mini` cevabı yazıyor, `qwen3-embedding-0.6b`
> vektörleri üretiyor. İkisi de Foundry Local üzerinden, bu makinede.
>
> Şu satır önemli: execution provider kaydı. İki hafta boyunca bu projenin
> CPU'da çalıştığını sandık, çünkü teşhis çıktısı "kayıtlı değil" diyordu ve
> biz onu "GPU yok" diye okuduk.
>
> Öyle değilmiş. Foundry Local yalnızca **kayıtlı** provider'lara ait model
> varyantlarını gösteriyor. GPU sürümü vardı, görünmüyordu. Kayıt tek satır ve
> iki saniye sürüyor.
>
> Medyan gecikme 16.5 saniyeden 1.2 saniyeye indi. İlk kelimeye kadar geçen
> süre 13.6 saniyeden 0.4'e.

**[EKRAN]** `src/foundry.py` dosyasını aç.

> Bütün SDK teması bu tek dosyada. Yerel çalışma zamanını değiştirmek
> isteseydik sadece burası değişirdi.

---

## 10 — Kapanış (20 sn)

**[EKRAN]** Ana ekrana dön.

> Özetlersem: iki bilgi kaynağı, ikisi ayrı etiketlerle modele gidiyor. İki
> kapı, ikisi de modeli çağırmadan önce duruyor. Bir kural motoru, hesabı o
> yapıyor. Ve bir model, sadece cümle kuruyor.
>
> Tekrar eden bir desen var: modele ne kadar az iş verirsek sonuç o kadar
> güvenilir oldu.

---

## Kaçınılacaklar

- Dosya adı saymak. "`rag.py`, `retrieve.py`, `embeddings.py` var" kimseye bir
  şey anlatmıyor. Ne yaptığını göster.
- "Cosine similarity kullandık" deyip geçmek. Ekranda skorlar var, onları
  göster.
- Her sayıyı söylemek. Bir bölümde en fazla iki sayı.
- Özür dilemek. Bir şey yapmadıysan sebebini söyle, ölçtüysen sayısını ver.
