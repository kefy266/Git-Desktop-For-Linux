# Git Desktop For Linux

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
