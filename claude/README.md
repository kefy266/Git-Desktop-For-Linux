# Git Desktop For Linux — `claude/` sürümü

*Bu klasör, `antigravty/` (GTK 4 arayüzlü sürüm) klasörünün kopyasıdır; üzerinde hata düzeltmeleri yapılmıştır. `antigravty/` klasörüne dokunulmamıştır.*

## Ne düzeltildi?

**Çökmeler (uygulamanın ana özellikleri çalışmıyordu)**
- **Commit butonu** var olmayan `git.commit()` metodunu çağırıp çöküyordu → `git_commit()`.
- **Sync (Fetch/Pull/Push) butonu** var olmayan `push()/pull()/fetch()` metodlarını çağırıyordu; hata thread içinde kaldığı için spinner sonsuza kadar dönüyordu → doğru metodlar + hata yakalama. Hem ileride hem geride olunca artık önce pull sonra push yapılıyor.
- **GitHub giriş penceresi** `Gtk.PasswordEntryRow` (GTK'da böyle bir sınıf yok) yüzünden açılmıyordu → `Adw.PasswordEntryRow`.

**Türkçe dosya adları**
- `ö, ş, ç...` içeren dosyalar git tarafından `"\303\266zet.txt"` gibi kaçışlı geliyordu; bu dosyalar stage/commit edilemiyordu → `git status -z` ile ayrıştırma. Yeniden adlandırma ve çakışma (`U`) durumları da doğru gösteriliyor.

**Donma ve güvenlik**
- Her yenilemede GitHub API'sine ana thread'de istek atılıyordu (5 sn'ye kadar donma) → arka plan thread'i, sadece açılışta ve hesap değişince.
- GitHub token'ı `config.json` içinde herkesin okuyabileceği izinle (0644) duruyordu → dosya 0600, klasör 0700, atomik yazma.
- Geçersiz token doğrulanmadan kaydediliyordu → önce API ile doğrulanıyor, hata mesajı gösteriliyor.
- Çıkış yapınca `gh` CLI token'ı ile sessizce tekrar giriş yapılıyordu → düzeltildi.
- Şifre gerektiren push/pull/clone işlemleri görünmeyen bir terminalde şifre bekleyip asılı kalabiliyordu → `GIT_TERMINAL_PROMPT=0`, hata mesajı gösteriliyor.
- Yeni repo adında `../` ile başka klasörlere repo açılabiliyordu → ad doğrulaması.

**Küçük hatalar**
- "Yerel" kullanıcı ayarı yanlış klasördeki repoya yazılıyordu.
- Geçersiz dal adları (`-f`, `a..b`, boşluklu) kontrol edilmiyordu.
- Takip edilmeyen ikili (binary) dosyalar diff ekranına ham bayt olarak basılıyordu.
- "Tümünü seç" kutusu dosyaların durumunu yansıtmıyordu.
- Dal listesinde aynı dala ikinci tıklama çalışmıyordu.
- Diff ekranındaki "Open in Editor" ayarlardaki editörü yok sayıyordu.
- İsim/dal adındaki `&`, `<` karakterleri arayüz yazısını bozuyordu.
- `stash save` (eskimiş) → `stash push -m`; boş adla tag push engellendi.
- Repo yöneticisi açılır açılmaz `~/Git` klasörü oluşturuluyordu.

## Testler

```bash
cd claude
python3 -m unittest discover -s tests -v
```

Testler geçici depolarda gerçek git komutlarıyla çalışır; `~/.gitconfig` ve `~/.config/git-desktop-linux` dosyalarınıza dokunmaz. Ekran (Wayland/X11) varsa GTK penceresi de test edilir (commit, sync, giriş penceresi).

---

*Bu proje topluluk tarafından hazırlanmış olup, Linux kullanıcılarının Git'i masaüstü uygulaması olarak kullanabilmesi için yapılmış bi projedir. Github Desktop'tan bağımsız bi projedir. Normal Git'in komutlarını ***GTK*** ile görsel olarak sunmayı ve en basit şekilde repo yönetimi sağlamayı amaçlamaktadır.*

***Mevcut Durum***
*Backend'de giriş kodu, temel,remote ve branch komutları ayrıca geçmişe dönük işlem komutları ve* ***GTK*** *arayüzü bağlandığında oluşabilecek sorunları engelleyen kodlar başarıyla eklendi. Son güncellemede ise dosya, stash, tag işlemleri ve çakışmaları çözme özellikleri eklendi.*
### Mevcut Eklenen Özellikler:
***GİRİŞ SİSTEMİ
TEMEL KOMUTLAR
REMOTE KOMUTLARI
BRANCH KOMUTLARI
GEÇMİŞE DÖNÜK KOMUTLAR
DOSYA İŞLEMLERİ
STASH İŞLEMLERİ
TAG İŞLEMLERİ
ÇAKIŞMALARI ÇÖZME***




Geliştirici: Kağan Efe TOPÇU [@kefy266](https://github.com/kefy266)

---

### GTK 4 / Libadwaita Masaüstü Uygulaması (GitHub Desktop Stili)

Bu klasör, GitHub Desktop (`desktop/desktop`) tasarımından ilham alınarak GTK 4 ve Libadwaita ile inşa edilmiş modern masaüstü arayüzünü içerir.

#### Başlatma:
```bash
python3 app.py
# veya belirli bir repoyu açmak için:
python3 app.py /path/to/repo
```

#### Bileşenler:
- **`app.py`**: Uygulama giriş noktası (`Adw.Application`).
- **`git_service.py`**: Git CLI işlemlerini yöneten, çıktıları yakalayan ve durumları ayrıştıran arka uç motoru.
- **`ui/window.py`**: GitHub Desktop stili 3 segmentli üst çubuk (Repo, Branch, Sync), sol kenar çubuğu (Changes/History + Commit Box) ve ana görünüm.
- **`ui/diff_view.py`**: `GtkSourceView` ile sözdizimi vurgulamalı (Diff) ve satır numaralı değişiklik görüntüleyici.
- **`ui/dialogs.py`**: Yeni dal oluşturma ve Git kullanıcı ayarları iletişim pencereleri.
