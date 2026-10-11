from loginsystem import git_giris
import os
import subprocess

if not git_giris():
    print("Öncelikle git kullanıcı bilgilerinizi ayarlamanız gerekiyor. Program sonlandırılıyor.")
    exit()

#BASIC COMMANDS

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

def git_clone(repo_url):
    subprocess.run(["git", "clone", repo_url])

#REMOTE COMMANDS

def git_remote_add(remote_name, remote_url):
    subprocess.run(["git", "remote", "add", remote_name, remote_url])

def git_remote_remove(remote_name):
    subprocess.run(["git", "remote", "remove", remote_name])

def git_remote_set_url(remote_name, remote_url):
    subprocess.run(["git", "remote", "set-url", remote_name, remote_url])

def git_remote_show(remote_name):
    subprocess.run(["git", "remote", "show", remote_name])

def git_remote_get_url(remote_name):
    subprocess.run(["git", "remote", "get-url", remote_name])

def git_remote_rename(old_name, new_name):
    subprocess.run(["git", "remote", "rename", old_name, new_name])

def git_remote_update(remote_name):
    subprocess.run(["git", "remote", "update", remote_name])

def git_remote_prune(remote_name):
    subprocess.run(["git", "remote", "prune", remote_name])

def git_remote_set_head(remote_name, branch_name):
    subprocess.run(["git", "remote", "set-head", remote_name, branch_name])

def git_remote_set_pushurl(remote_name, push_url):
    subprocess.run(["git", "remote", "set-url", "--push", remote_name, push_url])

def git_remote_set_fetchurl(remote_name, fetch_url):
    subprocess.run(["git", "remote", "set-url", "--fetch", remote_name, fetch_url])

#BRANCH COMMANDS
#Yakında branch komutları eklenecek.