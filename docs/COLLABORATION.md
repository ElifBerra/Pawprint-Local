# Çalışma Düzeni

Burak'ın Mac'i bozulduğu için proje tek bir Windows makinesinde geliştiriliyor.
Klavyede kim oturuyorsa commit'in yazarı o olur.

## Oturum başında

```powershell
.\scripts\git-as.ps1 burak     # Burak çalışacaksa
.\scripts\git-as.ps1 elif      # Elif çalışacaksa
.\scripts\git-as.ps1           # şu an kim ayarlı, göster
```

Bu ayar **sadece bu repo için** geçerli (`--local`), makinedeki diğer projeleri etkilemez.

Commit'ten önce kontrol et:

```powershell
git config user.email
```

## Birlikte yazılan kod

İkiniz de aynı koda katkı verdiyseniz, ikinizin de görünmesi için commit mesajının
sonuna boş bir satırdan sonra trailer ekleyin:

```
feat: add cosine similarity retrieval

Co-authored-by: burakaymak <burakdenizkaymak@gmail.com>
```

VS Code'da commit mesajı kutusunda çok satırlı yazabilirsiniz. GitHub bu commit'i
her iki profilde de gösterir.

## Push

Push işlemi kimin GitHub hesabıyla yapıldığından bağımsızdır — GitHub katkıları
**author e-postasına** göre sayar. Yani Elif'in kayıtlı kimlik bilgileriyle push
edilse bile, yazarı Burak olan commit'ler Burak'ın profilinde görünür.

`burakdenizkaymak@gmail.com` adresinin Burak'ın GitHub hesabında **doğrulanmış**
olması gerekiyor. Zaten öyle görünüyor — `mac/env-setup` branch'indeki commit'leri
profiline bağlanmış durumda.

## Branch düzeni

| Branch | Kim | Ne |
|---|---|---|
| `main` | ikisi | Her zaman çalışır durumda. Yarım iş buraya girmez. |
| `windows-setup` | Elif | Mevcut kurulum işi, bitince `main`'e merge |
| `mac/env-setup` | Burak | Mevcut kurulum işi, bitince `main`'e merge |
| `feat/<konu>` | duruma göre | Yeni özellikler buradan |

Mac artık devrede olmadığı için `mac/env-setup` adı yanıltıcı kalıyor.
`main`'e merge ettikten sonra sil, sonraki işler için `feat/...` kullanın.

## İş bölümü

Gün planı `docs/PLAN.md` içinde. Önerilen bölüm:

**Burak**
- Veri katmanı: `src/chunking.py`, `src/db.py`, `src/ingest.py`
- `data/docs/` altındaki bilgi tabanı içeriği
- `tests/eval_questions.json` — 20 soruluk değerlendirme seti
- `tests/test_chunking.py`
- Sunum slaytları

**Elif**
- SDK katmanı: `src/foundry.py`, `src/embeddings.py`, `src/llm.py`
- `src/retrieve.py`, `src/rag.py`, `src/cli.py`, `src/app.py`
- `docs/ARCHITECTURE.md`, `docs/EVALUATION.md`, `README.md`

Kesişen yerler (`config.py`, `REPORT.md`) birlikte yazılır → `Co-authored-by` kullanın.

Değerlendirme setini yazan kişinin belgeleri yazan kişiden farklı olması testin
kalitesini artırır — o yüzden `data/docs/` ve `eval_questions.json` aynı kişide
kalmasın diye bölünmedi, ikisi de Burak'ta ama farklı günlerde yazılacak.
