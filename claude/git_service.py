import os
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple, Any


def git_env() -> Dict[str, str]:
    """Environment for git calls from the GUI.

    GIT_TERMINAL_PROMPT=0 makes git fail fast instead of waiting forever for a
    username/password on a terminal the user cannot see. Credential helpers
    (libsecret, gh, store) keep working.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def run_git_command(args: List[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run git without a shell, never reading from stdin, never raising."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="replace",
            env=git_env(),
        )
    except Exception as e:
        return subprocess.CompletedProcess(args=["git", *args], returncode=-1, stdout="", stderr=str(e))


class GitService:
    """
    Robust, object-oriented Git engine for Git Desktop Linux.
    Executes commands with proper cwd, captures stdout and stderr,
    handles errors cleanly, and avoids shell injection risks.
    """

    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = os.path.abspath(repo_path) if repo_path else os.getcwd()

    def set_repo_path(self, path: str):
        self.repo_path = os.path.abspath(path)

    def run_git(self, *args: str) -> subprocess.CompletedProcess:
        """Run a git command in the repository path."""
        return run_git_command(list(args), cwd=self.repo_path)

    def is_git_repo(self) -> bool:
        if not os.path.isdir(self.repo_path):
            return False
        res = self.run_git("rev-parse", "--is-inside-work-tree")
        return res.returncode == 0 and res.stdout.strip() == "true"

    def get_repo_name(self) -> str:
        return os.path.basename(self.repo_path)

    # ==================== BASIC COMMANDS ====================
    def git_init(self) -> Tuple[bool, str]:
        res = self.run_git("init")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_status(self) -> Tuple[bool, str]:
        res = self.run_git("status")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_push(self, remote: str = "origin", branch: Optional[str] = None, set_upstream: bool = False) -> Tuple[bool, str]:
        cmd = ["push"]
        if set_upstream and branch:
            cmd.extend(["--set-upstream", remote, branch])
        elif remote and branch:
            cmd.extend([remote, branch])
        res = self.run_git(*cmd)
        if res.returncode != 0 and "no upstream branch" in res.stderr:
            curr = branch or self.get_current_branch()
            res = self.run_git("push", "--set-upstream", remote, curr)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_pull(self, remote: str = "origin", branch: Optional[str] = None) -> Tuple[bool, str]:
        cmd = ["pull"]
        if remote and branch:
            cmd.extend([remote, branch])
        res = self.run_git(*cmd)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_fetch(self, remote: Optional[str] = None, prune: bool = True) -> Tuple[bool, str]:
        cmd = ["fetch"]
        if prune:
            cmd.append("--prune")
        if remote:
            cmd.append(remote)
        else:
            cmd.append("--all")
        res = self.run_git(*cmd)
        return res.returncode == 0, res.stderr.strip() or res.stdout.strip()

    def git_commit(self, summary: str, description: str = "") -> Tuple[bool, str]:
        if not summary.strip():
            return False, "Commit summary cannot be empty."
        message = summary.strip()
        if description.strip():
            message += f"\n\n{description.strip()}"
        res = self.run_git("commit", "-m", message)
        return res.returncode == 0, res.stdout.strip() if res.returncode == 0 else res.stderr.strip()

    def git_clone(self, repo_url: str, target_dir: str) -> Tuple[bool, str]:
        res = run_git_command(["clone", "--", repo_url, target_dir])
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    # ==================== REMOTE COMMANDS ====================
    def git_remote_add(self, remote_name: str, remote_url: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "add", remote_name, remote_url)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_remove(self, remote_name: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "remove", remote_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_set_url(self, remote_name: str, remote_url: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "set-url", remote_name, remote_url)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_show(self, remote_name: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "show", remote_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_get_url(self, remote_name: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "get-url", remote_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_rename(self, old_name: str, new_name: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "rename", old_name, new_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_update(self, remote_name: Optional[str] = None) -> Tuple[bool, str]:
        cmd = ["remote", "update"]
        if remote_name:
            cmd.append(remote_name)
        res = self.run_git(*cmd)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_prune(self, remote_name: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "prune", remote_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_set_head(self, remote_name: str, branch_name: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "set-head", remote_name, branch_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_set_pushurl(self, remote_name: str, push_url: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "set-url", "--push", remote_name, push_url)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_set_fetchurl(self, remote_name: str, fetch_url: str) -> Tuple[bool, str]:
        res = self.run_git("remote", "set-url", "--fetch", remote_name, fetch_url)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_remote_list(self) -> List[str]:
        res = self.run_git("remote")
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return []

    # ==================== BRANCH COMMANDS ====================
    def get_current_branch(self) -> str:
        res = self.run_git("branch", "--show-current")
        branch = res.stdout.strip()
        if not branch:
            res_head = self.run_git("rev-parse", "--short", "HEAD")
            head = res_head.stdout.strip()
            return f"HEAD ({head})" if head else "No branch"
        return branch

    def get_branches(self) -> Dict[str, List[str]]:
        res = self.run_git("branch", "-a")
        local_branches = []
        remote_branches = []
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                clean_line = line.replace("*", "").strip()
                if not clean_line or "->" in clean_line:
                    continue
                if clean_line.startswith("remotes/"):
                    remote_branches.append(clean_line.replace("remotes/", ""))
                else:
                    local_branches.append(clean_line)
        return {"local": local_branches, "remote": remote_branches}

    def validate_branch_name(self, branch_name: str) -> Tuple[bool, str]:
        """Rejects invalid names and ones starting with '-' (would be read as an option)."""
        if not branch_name or branch_name.startswith("-"):
            return False, f"Invalid branch name: '{branch_name}'"
        res = self.run_git("check-ref-format", "--branch", branch_name)
        if res.returncode != 0:
            return False, f"Invalid branch name: '{branch_name}'"
        return True, ""

    def git_branch_create(self, branch_name: str) -> Tuple[bool, str]:
        ok, msg = self.validate_branch_name(branch_name)
        if not ok:
            return False, msg
        res = self.run_git("branch", branch_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_branch_delete(self, branch_name: str, force: bool = False) -> Tuple[bool, str]:
        flag = "-D" if force else "-d"
        res = self.run_git("branch", flag, branch_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_branch_rename(self, old_name: str, new_name: str) -> Tuple[bool, str]:
        res = self.run_git("branch", "-m", old_name, new_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def checkout_branch(self, branch_name: str) -> Tuple[bool, str]:
        res = self.run_git("checkout", branch_name)
        return res.returncode == 0, res.stderr.strip() or res.stdout.strip()

    def create_and_checkout_branch(self, branch_name: str) -> Tuple[bool, str]:
        ok, msg = self.validate_branch_name(branch_name)
        if not ok:
            return False, msg
        res = self.run_git("checkout", "-b", branch_name)
        return res.returncode == 0, res.stderr.strip() or res.stdout.strip()

    def git_branch_merge(self, branch_name: str) -> Tuple[bool, str]:
        res = self.run_git("merge", branch_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_branch_rebase(self, branch_name: str) -> Tuple[bool, str]:
        res = self.run_git("rebase", branch_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_branch_delete_remote(self, remote_name: str, branch_name: str) -> Tuple[bool, str]:
        res = self.run_git("push", remote_name, "--delete", branch_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_branch_set_upstream(self, branch_name: str, remote_name: str, remote_branch: str) -> Tuple[bool, str]:
        res = self.run_git("branch", "--set-upstream-to", f"{remote_name}/{remote_branch}", branch_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_branch_show_upstream(self, branch_name: str) -> Tuple[bool, str]:
        res = self.run_git("rev-parse", "--abbrev-ref", f"{branch_name}@{{upstream}}")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_branch_list_remote(self, remote_name: str) -> List[str]:
        res = self.run_git("ls-remote", "--heads", remote_name)
        branches = []
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                parts = line.split("refs/heads/")
                if len(parts) > 1:
                    branches.append(parts[1].strip())
        return branches

    def git_branch_list_merged(self) -> List[str]:
        res = self.run_git("branch", "--merged")
        if res.returncode == 0:
            return [b.replace("*", "").strip() for b in res.stdout.splitlines() if b.strip() and not b.startswith("*")]
        return []

    def git_branch_list_unmerged(self) -> List[str]:
        res = self.run_git("branch", "--no-merged")
        if res.returncode == 0:
            return [b.replace("*", "").strip() for b in res.stdout.splitlines() if b.strip() and not b.startswith("*")]
        return []

    # Pure Python safe mass delete (no fragile shell pipes!)
    def git_branch_delete_merged(self) -> Tuple[bool, str]:
        merged = self.git_branch_list_merged()
        deleted = []
        errors = []
        for b in merged:
            if b in ("main", "master"):
                continue
            ok, msg = self.git_branch_delete(b, force=False)
            if ok:
                deleted.append(b)
            else:
                errors.append(f"{b}: {msg}")
        return len(errors) == 0, f"Deleted: {', '.join(deleted)}" if deleted else "No branches deleted."

    def git_branch_delete_unmerged(self) -> Tuple[bool, str]:
        unmerged = self.git_branch_list_unmerged()
        deleted = []
        errors = []
        for b in unmerged:
            if b in ("main", "master"):
                continue
            ok, msg = self.git_branch_delete(b, force=True)
            if ok:
                deleted.append(b)
            else:
                errors.append(f"{b}: {msg}")
        return len(errors) == 0, f"Force deleted: {', '.join(deleted)}" if deleted else "No branches deleted."

    # ==================== HISTORY & LOG ====================
    def git_log(self, limit: int = 10) -> Tuple[bool, str]:
        res = self.run_git("log", "-n", str(limit), "--oneline")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_show(self, commit_hash: str) -> Tuple[bool, str]:
        res = self.run_git("show", commit_hash)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def get_commit_history(self, limit: int = 40) -> List[Dict[str, str]]:
        fmt = "%H%x1f%h%x1f%an%x1f%ae%x1f%ar%x1f%s%x1f%b%x1e"
        res = self.run_git("log", f"-n{limit}", f"--pretty=format:{fmt}")
        commits = []
        if res.returncode != 0:
            return commits

        entries = res.stdout.split("\x1e")
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split("\x1f")
            if len(parts) >= 6:
                commits.append({
                    "hash": parts[0].strip(),
                    "short_hash": parts[1].strip(),
                    "author": parts[2].strip(),
                    "email": parts[3].strip(),
                    "date": parts[4].strip(),
                    "summary": parts[5].strip(),
                    "body": parts[6].strip() if len(parts) > 6 else ""
                })
        return commits

    def undo_last_commit(self) -> Tuple[bool, str]:
        res = self.run_git("reset", "--soft", "HEAD~1")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def discard_file(self, file_path: str, is_untracked: bool = False) -> bool:
        if is_untracked:
            full_path = os.path.join(self.repo_path, file_path)
            try:
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path, ignore_errors=True)
                elif os.path.isfile(full_path):
                    os.remove(full_path)
                return True
            except OSError:
                return False
        else:
            self.run_git("restore", "--staged", "--", file_path)
            res = self.run_git("restore", "--", file_path)
            if res.returncode != 0:
                res = self.run_git("checkout", "--", file_path)
            return res.returncode == 0

    def discard_all_changes(self) -> bool:
        """Discards both tracked modifications and untracked files completely."""
        r1 = self.run_git("reset", "HEAD", ".")
        r2 = self.run_git("restore", ".")
        r3 = self.run_git("clean", "-fd")
        return all(r.returncode == 0 for r in (r1, r2, r3))

    def restore_file(self, file_path: str) -> Tuple[bool, str]:
        res = self.run_git("restore", file_path)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    # ==================== STASH COMMANDS ====================
    def git_stash_save(self, message: str = "") -> Tuple[bool, str]:
        # "stash save" is deprecated; "stash push -m" is the supported form
        cmd = ["stash", "push"]
        if message.strip():
            cmd.extend(["-m", message.strip()])
        res = self.run_git(*cmd)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_stash_pop(self) -> Tuple[bool, str]:
        res = self.run_git("stash", "pop")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_stash_list(self) -> List[str]:
        res = self.run_git("stash", "list")
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return []

    def git_stash_apply(self, stash_name: str = "stash@{0}") -> Tuple[bool, str]:
        res = self.run_git("stash", "apply", stash_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_stash_drop(self, stash_name: str = "stash@{0}") -> Tuple[bool, str]:
        res = self.run_git("stash", "drop", stash_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_stash_clear(self) -> Tuple[bool, str]:
        res = self.run_git("stash", "clear")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    # ==================== TAG COMMANDS ====================
    def git_tag_create(self, tag_name: str, message: str = "") -> Tuple[bool, str]:
        if message:
            res = self.run_git("tag", "-a", tag_name, "-m", message)
        else:
            res = self.run_git("tag", tag_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_tag_list(self) -> List[str]:
        res = self.run_git("tag")
        if res.returncode == 0:
            return [t.strip() for t in res.stdout.splitlines() if t.strip()]
        return []

    def git_tag_delete(self, tag_name: str) -> Tuple[bool, str]:
        res = self.run_git("tag", "-d", tag_name)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_tag_push(self, remote: str = "origin", tag_name: str = "") -> Tuple[bool, str]:
        if not tag_name.strip():
            return False, "Tag name cannot be empty."
        res = self.run_git("push", remote, f"refs/tags/{tag_name.strip()}")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def git_tag_push_all(self, remote: str = "origin") -> Tuple[bool, str]:
        res = self.run_git("push", remote, "--tags")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    # ==================== FILE & STAGING ====================
    def stage_file(self, file_path: str) -> bool:
        res = self.run_git("add", "--", file_path)
        return res.returncode == 0

    def unstage_file(self, file_path: str) -> bool:
        res = self.run_git("restore", "--staged", "--", file_path)
        if res.returncode != 0:
            res = self.run_git("reset", "HEAD", "--", file_path)
        return res.returncode == 0

    def stage_all(self) -> bool:
        res = self.run_git("add", "-A")
        return res.returncode == 0

    def unstage_all(self) -> bool:
        res = self.run_git("reset", "HEAD")
        return res.returncode == 0

    def reset_file(self, file_path: str) -> Tuple[bool, str]:
        res = self.run_git("reset", file_path)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def get_status_files(self) -> List[Dict[str, Any]]:
        # -z gives raw paths: no quoting/octal escapes for non-ASCII names (ö, ş, ...)
        res = self.run_git("status", "--porcelain=v1", "-z", "-uall")
        files = []
        if res.returncode != 0:
            return files

        entries = res.stdout.split("\0")
        i = 0
        while i < len(entries):
            entry = entries[i]
            i += 1
            if len(entry) < 4:
                continue
            x = entry[0]
            y = entry[1]
            path = entry[3:]
            orig_path = ""
            if x in ('R', 'C'):
                # Renames/copies are followed by the original path as a separate entry
                orig_path = entries[i] if i < len(entries) else ""
                i += 1

            is_staged = (x not in (' ', '?'))

            if 'U' in (x, y) or (x, y) in (('A', 'A'), ('D', 'D')):
                status = 'U'
                label = 'Conflicted'
            elif x == '?' or y == '?':
                status = '?'
                label = 'Untracked'
            elif x == 'A' or y == 'A':
                status = 'A'
                label = 'Added'
            elif x == 'D' or y == 'D':
                status = 'D'
                label = 'Deleted'
            elif x == 'R' or y == 'R':
                status = 'R'
                label = 'Renamed'
            else:
                status = 'M'
                label = 'Modified'

            files.append({
                'path': path,
                'orig_path': orig_path,
                'filename': os.path.basename(path),
                'dirname': os.path.dirname(path),
                'status': status,
                'status_label': label,
                'staged': is_staged
            })
        return files

    # ==================== RESET & CONFLICTS ====================
    def reset_hard(self, commit_hash: str = "HEAD") -> Tuple[bool, str]:
        res = self.run_git("reset", "--hard", commit_hash)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def reset_soft(self, commit_hash: str = "HEAD~1") -> Tuple[bool, str]:
        res = self.run_git("reset", "--soft", commit_hash)
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def merge_abort(self) -> Tuple[bool, str]:
        res = self.run_git("merge", "--abort")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    def rebase_abort(self) -> Tuple[bool, str]:
        res = self.run_git("rebase", "--abort")
        return res.returncode == 0, res.stdout.strip() or res.stderr.strip()

    # ==================== DIFF (FIXED DUPLICATE PARAMS) ====================
    def get_diff(self, file_path: Optional[str] = None) -> str:
        if file_path:
            full_path = os.path.join(self.repo_path, file_path)
            res_status = self.run_git("status", "--porcelain", "--", file_path)
            if res_status.stdout.startswith("??"):
                if os.path.isfile(full_path):
                    # Let git build the "new file" diff: it detects binary files
                    # instead of dumping their bytes into the view.
                    res = self.run_git("diff", "--no-index", "--", os.devnull, file_path)
                    return res.stdout or res.stderr

            res = self.run_git("diff", "HEAD", "--", file_path)
            if not res.stdout.strip():
                res = self.run_git("diff", "--", file_path)
            if not res.stdout.strip():
                res = self.run_git("diff", "--cached", "--", file_path)
            return res.stdout
        else:
            res = self.run_git("diff", "HEAD")
            return res.stdout

    def git_diff_cached(self) -> str:
        res = self.run_git("diff", "--cached")
        return res.stdout

    def git_diff_commit(self, commit_hash: str) -> str:
        res = self.run_git("diff", commit_hash)
        return res.stdout

    def git_diff_commit_range(self, commit1: str, commit2: str) -> str:
        res = self.run_git("diff", commit1, commit2)
        return res.stdout

    def git_diff_staged_commit(self, commit_hash: str) -> str:
        res = self.run_git("diff", "--cached", commit_hash)
        return res.stdout

    def git_diff_staged_commit_range(self, commit1: str, commit2: str) -> str:
        res = self.run_git("diff", "--cached", commit1, commit2)
        return res.stdout

    def get_commit_diff(self, commit_hash: str) -> str:
        res = self.run_git("show", "--stat", "-p", commit_hash)
        return res.stdout

    # ==================== SYNC STATUS & USER ====================
    def get_sync_status(self) -> Dict[str, Any]:
        res_upstream = self.run_git("rev-parse", "--abbrev-ref", "@{upstream}")
        if res_upstream.returncode != 0:
            return {'ahead': 0, 'behind': 0, 'has_upstream': False, 'upstream': ''}

        upstream = res_upstream.stdout.strip()
        res_count = self.run_git("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        ahead, behind = 0, 0
        if res_count.returncode == 0:
            parts = res_count.stdout.strip().split()
            if len(parts) >= 2:
                ahead = int(parts[0])
                behind = int(parts[1])
        return {
            'ahead': ahead,
            'behind': behind,
            'has_upstream': True,
            'upstream': upstream
        }

    def get_user_info(self) -> Tuple[str, str]:
        res_name = self.run_git("config", "user.name")
        res_email = self.run_git("config", "user.email")
        name = res_name.stdout.strip()
        email = res_email.stdout.strip()
        if not name:
            name = run_git_command(["config", "--global", "user.name"]).stdout.strip()
        if not email:
            email = run_git_command(["config", "--global", "user.email"]).stdout.strip()
        return name, email

    def set_user_info(self, name: str, email: str, is_global: bool = True) -> bool:
        # --local must run inside the repo, otherwise it writes to the process cwd's repo
        flag = "--global" if is_global else "--local"
        r1 = self.run_git("config", flag, "user.name", name)
        r2 = self.run_git("config", flag, "user.email", email)
        return r1.returncode == 0 and r2.returncode == 0
