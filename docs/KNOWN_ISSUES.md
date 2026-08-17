# Bilinen Sorunlar

## Script "Embedding..." ya da "Initializing Foundry Local" satırında donuyor

**Belirti:** Herhangi bir script ilk SDK çağrısında takılıyor, `Ctrl+C` işe yaramıyor,
diske hiçbir şey yazılmıyor, log dosyasına da yeni satır düşmüyor.

**İki ayrı sebebi var, ikisini de kontrol et:**

### 1. venv aktif değil

Prompt'ta `(venv)` yoksa global Python'daki farklı bir SDK kurulumu çalışıyor demektir.
Traceback'te `AppData\Local\Programs\Python\...` yolu görürsen sebep budur.

```powershell
.\venv\Scripts\Activate.ps1
```

Aktivasyon `ExecutionPolicy` hatası verirse:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### 2. Önceki çalıştırmadan artık süreç kalmış

Takılan bir script'i zorla öldürdüğünde native runtime kilidi açık kalıyor ve
**sonraki her çalıştırma başlangıçta donuyor**. `Ctrl+C` bu durumda çalışmaz —
indirme/yükleme .NET katmanında bloke, sinyal oraya ulaşmıyor.

Süreci VS Code'da terminal sekmesindeki çöp kutusu ikonuyla kapat, sonra:

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'foundry|onnx' } | Stop-Process -Force
```

Kural: **takılan bir script'i öldürdükten sonra her zaman bu temizliği yap.**
Yapmazsan olmayan hatalar kovalarsın.

---

## Streamlit konsolunda `[WinError 123] ... streamlit\static\*`

Uygulama açılırken terminale uzun bir ASGI traceback'i düşüyor ve sonunda:

```
OSError: [WinError 123] Dosya adı, dizin adı veya birim etiketi sözdizimi hatalı:
'...\venv\Lib\site-packages\streamlit\static\*'
```

**Zararsız.** Streamlit'in statik dosya sunucusunun Windows'ta joker karakterli
bir yol denemesinden kaynaklanıyor. Arayüz normal çalışıyor, sorular
cevaplanıyor, akış ve kaynaklar görünüyor.

Demo sırasında terminali ekrana yansıtacaksanız uygulamayı önceden başlatın ki
bu traceback izleyicinin gördüğü ilk şey olmasın.

---

## Cevaplar bazen 80-180 saniye sürüyor

**Belirti:** Aynı soru bazen 15 saniyede, bazen 3 dakikada cevaplanıyor.

**Sebep: CPU rekabeti.** Model GPU değil CPU kullanıyor. Aynı anda ekran kaydı,
görüntülü görüşme, ağır bir tarayıcı sekmesi ya da derleme çalışıyorsa çıkarım
süresi doğrudan katlanıyor. Ölçüldü:

| Durum | Medyan | En yavaş |
|---|---|---|
| Makine boştayken | 16.7s | 20.4s |
| Arka planda yük varken | 18.6s | **84.9s** |
| Ekran kaydı + görüntülü görüşme | — | **180.2s** |

Bu bir hata değil, CPU çıkarımının doğası. Ama bilmeden demoya girilirse
felakete dönüşür.

**Demo öncesi kontrol listesi:**

1. Görüntülü görüşme uygulamalarını kapat (Meet, Teams, Zoom)
2. Ekran kaydını kapat
3. Gereksiz tarayıcı sekmelerini kapat
4. Uygulamayı açıp **bir soru sor** — ilk sorgu modeli belleğe alıyor,
   izleyicinin o gecikmeyi görmesine gerek yok

---

## Teşhis sırası

Bir şey çalışmadığında sırayla:

1. `python scripts\check_env.py` — venv, paketler, katalog, execution provider'lar
2. `python scripts\hello_pet.py` — chat yolu (cache'ten yükler, indirme yok)
3. `python -m scripts.download_models` — indirme, yüzde ve süre basar
4. `python -m scripts.embed_steps` — embedding yolu, adım adım, süreli

Bu sıra sorunu ortam / indirme / yükleme / çıkarım olarak ayırıyor.

SDK log'ları:

```powershell
Get-Content (Get-ChildItem "$HOME\.pawprint-local\logs" -Recurse -File |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 40
```

---

## Execution provider'lar kayıtlı değil

`check_env.py` çıktısında `CUDAExecutionProvider` ve `WebGpuExecutionProvider`
için `is_registered=False` görünüyor. Bu makinede GPU yok, modeller `generic-cpu`
varyantlarıyla çalışıyor. **Beklenen durum, düzeltilmesi gerekmiyor.**

## Ölçülen süreler (CPU, referans)

| Adım | Süre |
|---|---|
| Manager başlatma | 0.2s |
| Alias çözümleme | 2.2s |
| `qwen3-embedding-0.6b` yükleme | 1.3s |
| Tek metin embedding | 0.4s |
| 3 metin batch embedding | 1.4s |
| `qwen3-embedding-0.6b` indirme | 23.7s |

Embedding boyutu: **1024**
