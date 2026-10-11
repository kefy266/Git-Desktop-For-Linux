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

def git_branch():
    subprocess.run(["git", "branch"])

def git_branch_create(branch_name):
    subprocess.run(["git", "branch", branch_name])

def git_branch_delete(branch_name):
    subprocess.run(["git", "branch", "-d", branch_name])

def git_branch_rename(old_name, new_name):
    subprocess.run(["git", "branch", "-m", old_name, new_name])

def git_branch_checkout(branch_name):
    subprocess.run(["git", "checkout", branch_name])

def git_branch_checkout_new(branch_name):
    subprocess.run(["git", "checkout", "-b", branch_name])

def git_branch_merge(branch_name):
    subprocess.run(["git", "merge", branch_name])

def git_branch_rebase(branch_name):
    subprocess.run(["git", "rebase", branch_name])

def git_branch_list(): 
    subprocess.run(["git", "branch", "-a"])

def git_branch_delete_remote(remote_name, branch_name):
    subprocess.run(["git", "push", remote_name, "--delete", branch_name])

def git_branch_set_upstream(branch_name, remote_name, remote_branch):
    subprocess.run(["git", "branch", "--set-upstream-to", f"{remote_name}/{remote_branch}", branch_name])

def git_branch_show_upstream(branch_name):
    subprocess.run(["git", "rev-parse", "--abbrev-ref", f"{branch_name}@{{upstream}}"])

def git_branch_list_remote(remote_name):
    subprocess.run(["git", "ls-remote", "--heads", remote_name])

def git_branch_list_merged():
    subprocess.run(["git", "branch", "--merged"])

def git_branch_list_unmerged():
    subprocess.run(["git", "branch", "--no-merged"])

def git_branch_delete_merged():
    subprocess.run(["git", "branch", "--merged", "|", "grep", "-v", "'*'", "|", "xargs", "git", "branch", "-d"])

def git_branch_delete_unmerged():
    subprocess.run(["git", "branch", "--no-merged", "|", "grep", "-v", "'*'", "|", "xargs", "git", "branch", "-D"])

def git_branch_list_remote_merged(remote_name):
    subprocess.run(["git", "branch", "-r", "--merged", remote_name])

def git_branch_list_remote_unmerged(remote_name):
    subprocess.run(["git", "branch", "-r", "--no-merged", remote_name])

def git_branch_delete_remote_merged(remote_name):
    subprocess.run(["git", "branch", "-r", "--merged", remote_name, "|", "grep", "-v", "'*'", "|", "xargs", "git", "push", remote_name, "--delete"])

def git_branch_delete_remote_unmerged(remote_name):
    subprocess.run(["git", "branch", "-r", "--no-merged", remote_name, "|", "grep", "-v", "'*'", "|", "xargs", "git", "push", remote_name, "--delete"])

def git_branch_list_remote_merged_branches(remote_name):
    subprocess.run(["git", "branch", "-r", "--merged", remote_name, "|", "grep", "-v", "'*'", "|", "xargs", "git", "branch", "-r"])

def git_branch_list_remote_unmerged_branches(remote_name):
    subprocess.run(["git", "branch", "-r", "--no-merged", remote_name, "|", "grep", "-v", "'*'", "|", "xargs", "git", "branch", "-r"])

#GEÇMİŞE DÖNÜK KOMUTLAR

def git_log(limit=10):
    subprocess.run(["git", "log", f"-n {limit}", "--oneline"])

def git_show(commit_hash):
    subprocess.run(["git", "show", commit_hash])

def git_discard_all_changes():
    subprocess.run(["git", "checkout", "."])

def git_restore_file(file_path):
    subprocess.run(["git", "restore", file_path])

def git_stash_save(message):
    subprocess.run(["git", "stash", "save", message])

def git_stash_pop():
    subprocess.run(["git", "stash", "pop"])

def git_stash_list():
    subprocess.run(["git", "stash", "list"])

def git_tag_create(tag_name, message):
    subprocess.run(["git", "tag", "-a", tag_name, "-m", message])

def git_tag_list():
    subprocess.run(["git", "tag"])

#DOSYA İŞLEMLERİ

def git_add_file(file_path):
    subprocess.run(["git", "add", file_path])

def git_reset_file(file_path):
    subprocess.run(["git", "reset", file_path])

#RESET VE COMMIT İŞLEMLERİ

def git_reset_hard(commit_hash):
    subprocess.run(["git", "reset", "--hard", commit_hash])

def git_reset_soft(commit_hash):
    subprocess.run(["git", "reset", "--soft", commit_hash])

#STASH İŞLEMLERİ

def git_stash_apply(stash_name):
    subprocess.run(["git", "stash", "apply", stash_name])

def git_stash_drop(stash_name):
    subprocess.run(["git", "stash", "drop", stash_name])

def git_stash_clear():
    subprocess.run(["git", "stash", "clear"])

#TAG İŞLEMLERİ

def git_tag_delete(tag_name):
    subprocess.run(["git", "tag", "-d", tag_name])

def git_tag_push(tag_name):
    subprocess.run(["git", "push", "origin", tag_name])

def git_tag_push_all():
    subprocess.run(["git", "push", "origin", "--tags"])

#ÇAKIŞMALARI ÇÖZME

def git_merge_abort():
    subprocess.run(["git", "merge", "--abort"])

def git_rebase_abort():
    subprocess.run(["git", "rebase", "--abort"])