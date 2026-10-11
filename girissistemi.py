import subprocess

def git_giris():

    print("Git kullanıcı adınızı ve e-posta adresinizi ayarlamak için lütfen aşağıdaki bilgileri girin.")

    kontrol = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True)
    mevcut_kullanici = kontrol.stdout.strip()

    if mevcut_kullanici:
        print(f"Zaten mevcut bir kullanıcı adı var: {mevcut_kullanici}")
        return True

    print("Bilgisayarınızda kayıtlı bir githesabı bulunamadı. Lütfen Tek seferlik olarak kullanıcı adınızı ve e-posta adresinizi ayarlayın.")
    kullanici_adi = input("Kullanıcı Adınızı Girin: ")
    eposta_adresi = input("E-posta Adresinizi Girin: ")

    if not kullanici_adi or not eposta_adresi:
        print("Kullanıcı adı ve e-posta adresi boş bırakılamaz. Lütfen geçerli bilgiler girin.")
        return False

    subprocess.run(["git", "config", "--global", "user.name", kullanici_adi])
    subprocess.run(["git", "config", "--global", "user.email", eposta_adresi])
    print("Git kullanıcı bilgileri başarıyla ayarlandı.")
    return True

if __name__ == "__main__":
    git_giris()