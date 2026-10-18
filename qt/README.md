# Git Desktop For Linux — Qt sürümü

*[GitHub Desktop](https://github.com/desktop/desktop) örnek alınarak **Qt 6 (PySide6)** ile yazılmış masaüstü Git istemcisi. Git ve GitHub backend'i `claude/` sürümünden alınıp genişletildi.*

## Kurulum ve çalıştırma

```bash
cd qt
python3 -m venv --system-site-packages .venv
.venv/bin/pip install PySide6-Essentials
.venv/bin/python app.py                  # son açılan repo
.venv/bin/python app.py /yol/repo        # belirli bir repo
```

`requests` paketi sistemden gelir (`--system-site-packages`). `.venv/` git'e eklenmez.

## Özellikler (GitHub Desktop'taki gibi)

**Araç çubuğu:** *Current repository* (aranabilir liste + Clone / Create / Add), *Current branch* (aranabilir yerel ve uzak dallar, sağ tıkla Rename / Delete), *Fetch / Pull / Push / Publish branch* butonu ("Last fetched … ago", ↑↓ sayıları).

**Changes:** dosya başına onay kutusu ve üç durumlu "tümünü seç", sadece işaretli dosyaları commit etme, Summary + Description, `Ctrl+Enter` ile commit. Commit'ten sonra push edilene kadar **Undo**. Sağ tık: Discard (yeni dosyalar çöp kutusuna gider), .gitignore'a ekle, yolu kopyala, dosya yöneticisinde göster, editörde aç.

**History:** commit listesi (aşağı kaydırdıkça daha fazla yüklenir), commit detayı, commit'teki dosyalar ve her dosyanın diff'i.

**Diff:** eski/yeni satır numaraları, renkli eklenen/silinen satırlar, binary dosya algılama.

**Dal değiştirme:** değişiklik varken *"Leave my changes on X"* (otomatik stash, o dala dönünce *Restore*) veya *"Bring my changes to Y"*.

**Diğer:** merge (çakışma şeridi + Abort merge), stash, Options (GitHub hesabı, git kimliği, editör, terminal, açık/koyu/sistem teması), açılışta ve pencere odaklanınca durum yenileme, 30 dakikada bir arka planda fetch.

**GitHub hesabı:** sağ üstteki avatara tıkla. Giriş yapılmışsa profil kartı (ad, kullanıcı adı, repo sayısı, *Your profile on GitHub*, *Sign out*), yapılmamışsa *Sign in to GitHub.com*. Giriş, kişisel erişim token'ı ile yapılır (kaydetmeden önce GitHub'da doğrulanır) ya da `gh auth login` sonrası *Check again* ile. HTTPS push/pull/clone bu hesabı kullanır; token komut satırında görünmez ve ayar dosyası sadece sana açıktır (0600).

**GitHub repoların:** hesabındaki tüm repolar (100 sınırı yok; kendi, iş birliği yaptığın ve organizasyonlarındakiler) *Current repository* listesinde sahibine göre gruplu görünür. Bilgisayarında olanlar tekrar listelenmez, tıklayınca Clone penceresi o repo seçili açılır.

## Kısayollar

| Kısayol | İşlem | Kısayol | İşlem |
|---|---|---|---|
| `Ctrl+1` / `Ctrl+2` | Changes / History | `Ctrl+P` | Push |
| `Ctrl+T` | Repo listesi | `Ctrl+Shift+P` | Pull |
| `Ctrl+B` | Dal listesi | `Ctrl+Shift+T` | Fetch |
| `Ctrl+Shift+N` | Yeni dal | `Ctrl+Shift+M` | Merge |
| `Ctrl+N` / `Ctrl+O` / `Ctrl+Shift+O` | Yeni / Ekle / Clone | `Ctrl+Shift+A` | Editörde aç |
| `Ctrl+,` | Options | `Ctrl+\`` | Terminalde aç |

## Testler

```bash
cd qt
.venv/bin/python -m unittest discover -s tests -v
```

Testler ekran gerektirmez (`QT_QPA_PLATFORM=offscreen`), geçici depolarda çalışır, `~/.gitconfig` ve ayar dosyalarınıza dokunmaz.

Geliştirici: Kağan Efe TOPÇU [@kefy266](https://github.com/kefy266)
