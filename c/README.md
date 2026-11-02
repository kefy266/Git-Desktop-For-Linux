# Git Desktop For Linux — native C sürümü

[GitHub Desktop](https://github.com/desktop/desktop) örnek alınarak **C + GTK4 + libadwaita** ile yazılmış, derlenen gerçek bir masaüstü uygulaması. Python yok, tek bir çalıştırılabilir dosya.

## Derleme ve çalıştırma

Gerekenler (Arch/CachyOS'ta hepsi resmi depolarda): `gtk4 libadwaita gtksourceview5 libgit2 libsecret json-glib libsoup3 git`

```bash
cd c
make            # build/git-desktop
make run        # bu repoyla başlat
make test       # git katmanı testleri
make install    # ~/.local/bin + uygulama menüsü kaydı ve ikon
```

`build/git-desktop /yol/repo` ile istediğin repoyu açabilirsin.

## Mimari

| Dosya | Görev |
|---|---|
| `src/git.c` | Yerel git işlemleri **libgit2** ile, süreç içinde: durum, diff, seçili dosyalarla commit, undo, geçmiş, dal, merge, stash |
| `src/net.c` | fetch / pull / push / clone: GitHub Desktop gibi arka planda `git` komutuyla. SSH anahtarların ve git ayarların aynen çalışır |
| `src/github.c` | GitHub API (**libsoup** + **json-glib**): profil, tüm repolar (sayfalamayla), avatar. Token **sistem anahtarlığında** (libsecret / KWallet / GNOME Keyring) |
| `src/window.c` | Ana pencere: araç çubuğu, Changes / History, commit kutusu, şeritler, hesap menüsü, kısayollar |
| `src/dialogs.c` | Clone, Create, dal adı, Merge, Tercihler, Giriş |
| `src/diffview.c` | GtkSourceView üzerinde eski/yeni satır numaralı renkli diff |
| `src/icons.c` | Vektör yollarla çizilen, temaya göre renk alan ikonlar |

Ağ ve GitHub işleri arayüzü dondurmaz (GTask ve GSubprocess ile arka planda çalışır). Token hiçbir zaman komut satırında görünmez; git'e ortam değişkeni üzerinden bir kimlik yardımcısıyla verilir.

## Özellikler

- **Araç çubuğu:** aranabilir repo listesi (son açılanlar + GitHub hesabındaki tüm repolar, sahibine göre gruplu), aranabilir dal listesi (yerel + uzak, sağ tıkla Rename/Delete), Fetch / Pull / Push / Publish branch butonu.
- **Changes:** dosya başına onay kutusu, sadece işaretlileri commit etme, Ctrl+Enter, push edilene kadar **Undo**, sağ tık menüsü (Discard: yeni dosyalar çöp kutusuna gider; .gitignore; yol kopyala; dosya yöneticisi; editör).
- **History:** avatarlı commit listesi (kaydırdıkça yüklenir), commit detayı, dosyalar ve diff'leri.
- **Dal değiştirme:** değişiklik varken *Leave my changes on X* (otomatik stash, dala dönünce *Restore*) ya da *Bring my changes to Y*.
- **Merge:** temiz merge otomatik commit edilir; çakışmada şerit + *Abort merge*.
- **Hesap:** sağ üstteki avatar; profil kartı, çıkış (sonrası giriş ekranı açılır), token ile giriş (kaydetmeden önce doğrulanır) veya `gh auth login` ile.
- **Tercihler:** git kimliği, harici editör, terminal, açık/koyu/sistem teması.

Kısayolların tam listesi: ana menü → *Keyboard Shortcuts*.

## Testler

```bash
make test
```

15 test geçici depolarda gerçek git ile çalışır; `~/.gitconfig` dosyana dokunmaz. Commit, undo, merge çakışması, stash, push ve diverge olmuş pull dahil. Uygulama ayrıca AddressSanitizer + UBSan ile tüm görünümlerde hatasız çalıştırıldı:

```bash
make clean && make CFLAGS="-O1 -g -fsanitize=address,undefined" LDFLAGS="-fsanitize=address,undefined"
```

Geliştirici: Kağan Efe TOPÇU [@kefy266](https://github.com/kefy266)
