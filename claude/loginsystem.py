import subprocess
from typing import Tuple, Optional

def get_git_user_config() -> Tuple[str, str]:
    """Returns (user.name, user.email) from global git config without blocking."""
    res_name = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True)
    res_email = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True)
    return res_name.stdout.strip(), res_email.stdout.strip()

def has_git_user_config() -> bool:
    """Checks if git user.name and user.email are configured."""
    name, email = get_git_user_config()
    return bool(name and email)

def set_git_user_config(name: str, email: str) -> bool:
    """Sets global user.name and user.email."""
    r1 = subprocess.run(["git", "config", "--global", "user.name", name], capture_output=True, text=True)
    r2 = subprocess.run(["git", "config", "--global", "user.email", email], capture_output=True, text=True)
    return r1.returncode == 0 and r2.returncode == 0

def git_giris(interactive: bool = False) -> bool:
    """
    Non-blocking check by default. 
    If interactive=True and config is missing, prompts via console input.
    """
    name, email = get_git_user_config()
    if name and email:
        return True

    if not interactive:
        return False

    print("Bilgisayarınızda kayıtlı bir Git hesabı bulunamadı. Lütfen kullanıcı adınızı ve e-postanızı girin.")
    kullanici_adi = input("Kullanıcı Adınızı Girin: ").strip()
    eposta_adresi = input("E-posta Adresinizi Girin: ").strip()

    if not kullanici_adi or not eposta_adresi:
        print("Kullanıcı adı ve e-posta adresi boş bırakılamaz.")
        return False

    return set_git_user_config(kullanici_adi, eposta_adresi)

if __name__ == "__main__":
    git_giris(interactive=True)