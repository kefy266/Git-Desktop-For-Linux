from girissistemi import git_giris
import os
import subprocess

if not git_giris():
    print("Öncelikle git kullanıcı bilgilerinizi ayarlamanız gerekiyor. Program sonlandırılıyor.")
    exit()

def git_init():
    subprocess.run(["git", "init"])

def git_status():
    subprocess.run(["git", "status"])

def git_push():
    subprocess.run(["git", "push"])

def git_pull():
    subprocess.run(["git", "pull"])

def git_commit(message):
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", message])

