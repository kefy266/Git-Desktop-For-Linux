"""
Git Desktop For Linux - Main Backend Interface
This module wraps GitService to provide clean, backwards-compatible,
and non-blocking procedural functions for Git operations.
"""

import sys
import os
from typing import Tuple, List, Dict, Optional, Any
from git_service import GitService
from loginsystem import has_git_user_config, git_giris

# Initialize default service for current working directory
_git = GitService()

def set_repo_path(path: str):
    """Change the active repository path for procedural functions."""
    _git.set_repo_path(path)

# ==================== BASIC COMMANDS ====================
def git_init():
    ok, out = _git.git_init()
    if out: print(out)
    return ok, out

def git_status():
    ok, out = _git.git_status()
    if out: print(out)
    return ok, out

def git_push(remote: str = "origin", branch: Optional[str] = None):
    ok, out = _git.git_push(remote, branch)
    if out: print(out)
    return ok, out

def git_pull(remote: str = "origin", branch: Optional[str] = None):
    ok, out = _git.git_pull(remote, branch)
    if out: print(out)
    return ok, out

def git_commit(message: str, description: str = ""):
    ok, out = _git.git_commit(message, description)
    if out: print(out)
    return ok, out

def git_clone(repo_url: str, target_dir: str = "."):
    ok, out = _git.git_clone(repo_url, target_dir)
    if out: print(out)
    return ok, out

def git_fetch(remote: Optional[str] = None):
    ok, out = _git.git_fetch(remote)
    if out: print(out)
    return ok, out

# ==================== REMOTE COMMANDS ====================
def git_remote_add(remote_name: str, remote_url: str):
    ok, out = _git.git_remote_add(remote_name, remote_url)
    if out: print(out)
    return ok, out

def git_remote_remove(remote_name: str):
    ok, out = _git.git_remote_remove(remote_name)
    if out: print(out)
    return ok, out

def git_remote_set_url(remote_name: str, remote_url: str):
    ok, out = _git.git_remote_set_url(remote_name, remote_url)
    if out: print(out)
    return ok, out

def git_remote_show(remote_name: str):
    ok, out = _git.git_remote_show(remote_name)
    if out: print(out)
    return ok, out

def git_remote_get_url(remote_name: str):
    ok, out = _git.git_remote_get_url(remote_name)
    if out: print(out)
    return ok, out

def git_remote_rename(old_name: str, new_name: str):
    ok, out = _git.git_remote_rename(old_name, new_name)
    if out: print(out)
    return ok, out

def git_remote_update(remote_name: Optional[str] = None):
    ok, out = _git.git_remote_update(remote_name)
    if out: print(out)
    return ok, out

def git_remote_prune(remote_name: str):
    ok, out = _git.git_remote_prune(remote_name)
    if out: print(out)
    return ok, out

def git_remote_set_head(remote_name: str, branch_name: str):
    ok, out = _git.git_remote_set_head(remote_name, branch_name)
    if out: print(out)
    return ok, out

def git_remote_set_pushurl(remote_name: str, push_url: str):
    ok, out = _git.git_remote_set_pushurl(remote_name, push_url)
    if out: print(out)
    return ok, out

def git_remote_set_fetchurl(remote_name: str, fetch_url: str):
    ok, out = _git.git_remote_set_fetchurl(remote_name, fetch_url)
    if out: print(out)
    return ok, out

# ==================== BRANCH COMMANDS ====================
def git_branch():
    branches = _git.get_branches()
    curr = _git.get_current_branch()
    for b in branches.get("local", []):
        prefix = "* " if b == curr else "  "
        print(f"{prefix}{b}")
    return branches

def git_branch_create(branch_name: str):
    ok, out = _git.git_branch_create(branch_name)
    if out: print(out)
    return ok, out

def git_branch_delete(branch_name: str):
    ok, out = _git.git_branch_delete(branch_name, force=False)
    if out: print(out)
    return ok, out

def git_branch_rename(old_name: str, new_name: str):
    ok, out = _git.git_branch_rename(old_name, new_name)
    if out: print(out)
    return ok, out

def git_branch_checkout(branch_name: str):
    ok, out = _git.checkout_branch(branch_name)
    if out: print(out)
    return ok, out

def git_branch_checkout_new(branch_name: str):
    ok, out = _git.create_and_checkout_branch(branch_name)
    if out: print(out)
    return ok, out

def git_branch_merge(branch_name: str):
    ok, out = _git.git_branch_merge(branch_name)
    if out: print(out)
    return ok, out

def git_branch_rebase(branch_name: str):
    ok, out = _git.git_branch_rebase(branch_name)
    if out: print(out)
    return ok, out

def git_branch_list():
    branches = _git.get_branches()
    return branches.get("local", []) + branches.get("remote", [])

def git_branch_delete_remote(remote_name: str, branch_name: str):
    ok, out = _git.git_branch_delete_remote(remote_name, branch_name)
    if out: print(out)
    return ok, out

def git_branch_set_upstream(branch_name: str, remote_name: str, remote_branch: str):
    ok, out = _git.git_branch_set_upstream(branch_name, remote_name, remote_branch)
    if out: print(out)
    return ok, out

def git_branch_show_upstream(branch_name: str):
    ok, out = _git.git_branch_show_upstream(branch_name)
    if out: print(out)
    return ok, out

def git_branch_list_remote(remote_name: str):
    return _git.git_branch_list_remote(remote_name)

def git_branch_list_merged():
    return _git.git_branch_list_merged()

def git_branch_list_unmerged():
    return _git.git_branch_list_unmerged()

def git_branch_delete_merged():
    ok, msg = _git.git_branch_delete_merged()
    print(msg)
    return ok, msg

def git_branch_delete_unmerged():
    ok, msg = _git.git_branch_delete_unmerged()
    print(msg)
    return ok, msg

# ==================== HISTORY & LOG ====================
def git_log(limit: int = 10):
    ok, out = _git.git_log(limit)
    if out: print(out)
    return ok, out

def git_show(commit_hash: str):
    ok, out = _git.git_show(commit_hash)
    if out: print(out)
    return ok, out

def git_discard_all_changes():
    ok = _git.discard_all_changes()
    print("All working tree changes discarded." if ok else "Failed to discard all changes.")
    return ok

def git_restore_file(file_path: str):
    ok, out = _git.restore_file(file_path)
    if out: print(out)
    return ok, out

# ==================== STASH COMMANDS ====================
def git_stash_save(message: str = ""):
    ok, out = _git.git_stash_save(message)
    if out: print(out)
    return ok, out

def git_stash_pop():
    ok, out = _git.git_stash_pop()
    if out: print(out)
    return ok, out

def git_stash_list():
    lst = _git.git_stash_list()
    for s in lst: print(s)
    return lst

def git_stash_apply(stash_name: str = "stash@{0}"):
    ok, out = _git.git_stash_apply(stash_name)
    if out: print(out)
    return ok, out

def git_stash_drop(stash_name: str = "stash@{0}"):
    ok, out = _git.git_stash_drop(stash_name)
    if out: print(out)
    return ok, out

def git_stash_clear():
    ok, out = _git.git_stash_clear()
    if out: print(out)
    return ok, out

# ==================== TAG COMMANDS ====================
def git_tag_create(tag_name: str, message: str = ""):
    ok, out = _git.git_tag_create(tag_name, message)
    if out: print(out)
    return ok, out

def git_tag_list():
    tags = _git.git_tag_list()
    for t in tags: print(t)
    return tags

def git_tag_delete(tag_name: str):
    ok, out = _git.git_tag_delete(tag_name)
    if out: print(out)
    return ok, out

def git_tag_push(remote: str = "origin", tag_name: str = ""):
    ok, out = _git.git_tag_push(remote, tag_name)
    if out: print(out)
    return ok, out

def git_tag_push_all(remote: str = "origin"):
    ok, out = _git.git_tag_push_all(remote)
    if out: print(out)
    return ok, out

# ==================== FILE & STAGING ====================
def git_add_file(file_path: str):
    return _git.stage_file(file_path)

def git_stage_file(file_path: str):
    return _git.stage_file(file_path)

def git_stage_all():
    return _git.stage_all()

def git_unstage_file(file_path: str):
    return _git.unstage_file(file_path)

def git_unstage_all():
    return _git.unstage_all()

def git_reset_file(file_path: str):
    ok, out = _git.reset_file(file_path)
    if out: print(out)
    return ok, out

# ==================== RESET & CONFLICTS ====================
def git_reset_hard(commit_hash: str = "HEAD"):
    ok, out = _git.reset_hard(commit_hash)
    if out: print(out)
    return ok, out

def git_reset_soft(commit_hash: str = "HEAD~1"):
    ok, out = _git.reset_soft(commit_hash)
    if out: print(out)
    return ok, out

def git_merge_abort():
    ok, out = _git.merge_abort()
    if out: print(out)
    return ok, out

def git_rebase_abort():
    ok, out = _git.rebase_abort()
    if out: print(out)
    return ok, out

# ==================== DIFF ====================
def git_diff(file_path: Optional[str] = None):
    out = _git.get_diff(file_path)
    if out: print(out)
    return out

def git_diff_cached():
    out = _git.git_diff_cached()
    if out: print(out)
    return out

def git_diff_commit(commit_hash: str):
    out = _git.git_diff_commit(commit_hash)
    if out: print(out)
    return out

def git_diff_commit_range(commit1: str, commit2: str):
    out = _git.git_diff_commit_range(commit1, commit2)
    if out: print(out)
    return out

def git_diff_staged_commit(commit_hash: str):
    out = _git.git_diff_staged_commit(commit_hash)
    if out: print(out)
    return out

def git_diff_staged_commit_range(commit1: str, commit2: str):
    out = _git.git_diff_staged_commit_range(commit1, commit2)
    if out: print(out)
    return out

# ==================== MAIN LAUNCHER ====================
if __name__ == "__main__":
    from app import main as start_gui
    sys.exit(start_gui())