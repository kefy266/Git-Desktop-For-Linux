import os
import json
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple, Any
import requests

from git_service import run_git_command, github_auth_args

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "git-desktop-linux"
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
REPOS_FILE = os.path.join(CONFIG_DIR, "repos.json")

class GitHubService:
    KNOWN_EDITORS = [
        {"name": "Visual Studio Code", "cmd": "code", "icon": "com.visualstudio.code"},
        {"name": "VSCodium", "cmd": "codium", "icon": "com.vscodium.codium"},
        {"name": "Cursor", "cmd": "cursor", "icon": "cursor"},
        {"name": "Sublime Text", "cmd": "subl", "icon": "sublime-text"},
        {"name": "PyCharm", "cmd": "pycharm", "icon": "pycharm"},
        {"name": "Kate", "cmd": "kate", "icon": "kate"},
        {"name": "GNOME Builder", "cmd": "gnome-builder", "icon": "org.gnome.Builder"},
        {"name": "GNOME Text Editor", "cmd": "gnome-text-editor", "icon": "org.gnome.TextEditor"},
        {"name": "Gedit", "cmd": "gedit", "icon": "org.gnome.gedit"},
    ]

    def __init__(self):
        os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
        self.config = self._load_json(CONFIG_FILE, {
            "token": None,
            "preferred_editor": None
        })
        self.repos_data = self._load_json(REPOS_FILE, {
            "recent_repos": []
        })
        # Older versions wrote the token world-readable (0644); tighten it
        if os.path.exists(CONFIG_FILE):
            try:
                os.chmod(CONFIG_FILE, 0o600)
            except OSError:
                pass

    def _load_json(self, path: str, default: Any) -> Any:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, path: str, data: Any):
        # Write to a 0600 temp file and rename, so the token is never readable
        # by other users and a crash mid-write can't corrupt the config.
        tmp_path = f"{path}.tmp"
        try:
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception as e:
            print(f"Error saving {path}: {e}")

    # ==================== GITHUB AUTH ====================
    def get_token(self) -> Optional[str]:
        # 1. Custom token saved in config
        if self.config.get("token"):
            return self.config["token"]

        # 2. Check GitHub CLI (gh auth token), unless the user signed out here
        if not self.config.get("use_gh_cli", True):
            return None
        try:
            res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                                 stdin=subprocess.DEVNULL, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
        return None

    def set_token(self, token: Optional[str]):
        self.config["token"] = token.strip() if token else None
        if token:
            self.config["use_gh_cli"] = True
        self._save_json(CONFIG_FILE, self.config)

    def logout(self):
        # Without this flag, the gh CLI token would silently log the user back in
        self.config["use_gh_cli"] = False
        self.set_token(None)

    def get_user_profile(self, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetches the GitHub profile. Network call: run it off the GTK main thread."""
        token = token or self.get_token()
        if not token:
            return None

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitDesktopLinux"
        }
        try:
            res = requests.get("https://api.github.com/user", headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                return {
                    "login": data.get("login"),
                    "name": data.get("name") or data.get("login"),
                    "avatar_url": data.get("avatar_url"),
                    "html_url": data.get("html_url"),
                    "bio": data.get("bio", ""),
                    "public_repos": data.get("public_repos", 0),
                    "total_private_repos": data.get("total_private_repos", 0)
                }
        except Exception as e:
            print(f"GitHub API Error: {e}")
        return None

    # ==================== ONLINE REPOSITORIES ====================
    def get_user_repos(self, limit: int = 50) -> List[Dict[str, Any]]:
        token = self.get_token()
        if not token:
            return []

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitDesktopLinux"
        }
        try:
            url = f"https://api.github.com/user/repos?sort=updated&per_page={limit}"
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                repos = []
                for item in res.json():
                    repos.append({
                        "name": item.get("name"),
                        "full_name": item.get("full_name"),
                        "description": item.get("description") or "",
                        "clone_url": item.get("clone_url"),
                        "ssh_url": item.get("ssh_url"),
                        "is_private": item.get("private", False),
                        "stars": item.get("stargazers_count", 0),
                        "updated_at": item.get("updated_at", "")[:10]
                    })
                return repos
        except Exception as e:
            print(f"Error fetching repos: {e}")
        return []

    def clone_repo(self, repo_url: str, target_dir: str) -> Tuple[bool, str]:
        # Signed-in token lets private https://github.com repos clone without a prompt
        auth_args, auth_env = github_auth_args(self.get_token())
        res = run_git_command([*auth_args, "clone", "--", repo_url, target_dir], extra_env=auth_env)
        return res.returncode == 0, (res.stdout or res.stderr).strip()

    # ==================== LOCAL & RECENT REPOSITORIES ====================
    def get_recent_repos(self) -> List[Dict[str, str]]:
        recent = self.repos_data.get("recent_repos", [])
        # Filter out non-existing paths
        valid = []
        for r in recent:
            path = r.get("path")
            if path and os.path.isdir(path):
                valid.append(r)
        if len(valid) != len(recent):
            self.repos_data["recent_repos"] = valid
            self._save_json(REPOS_FILE, self.repos_data)
        return valid

    def add_recent_repo(self, path: str):
        abs_path = os.path.abspath(path)
        name = os.path.basename(abs_path)
        recent = self.get_recent_repos()
        # Remove if already exists
        recent = [r for r in recent if r.get("path") != abs_path]
        recent.insert(0, {"name": name, "path": abs_path})
        self.repos_data["recent_repos"] = recent[:20]  # keep top 20
        self._save_json(REPOS_FILE, self.repos_data)

    def remove_recent_repo(self, path: str):
        recent = self.get_recent_repos()
        recent = [r for r in recent if r.get("path") != path]
        self.repos_data["recent_repos"] = recent
        self._save_json(REPOS_FILE, self.repos_data)

    def init_new_repo(self, path: str, name: str, init_readme: bool = True) -> Tuple[bool, str]:
        name = name.strip()
        # Only a plain folder name: no "../", no sub-paths, no hidden dirs
        if not name or name in (".", "..") or os.sep in name or name.startswith("."):
            return False, f"Invalid repository name: '{name}'"
        target_dir = os.path.join(path, name)
        try:
            os.makedirs(target_dir, exist_ok=True)
            res = run_git_command(["init"], cwd=target_dir)
            if res.returncode != 0:
                return False, res.stderr

            if init_readme:
                readme_path = os.path.join(target_dir, "README.md")
                if not os.path.exists(readme_path):
                    with open(readme_path, "w", encoding="utf-8") as f:
                        f.write(f"# {name}\n\nInitialized with Git Desktop For Linux.\n")
                    run_git_command(["add", "README.md"], cwd=target_dir)
                    res = run_git_command(["commit", "-m", "Initial commit"], cwd=target_dir)
                    if res.returncode != 0:
                        # Typically: git user.name/user.email not set
                        self.add_recent_repo(target_dir)
                        return False, f"Repository created, but the initial commit failed:\n{res.stderr.strip()}"

            self.add_recent_repo(target_dir)
            return True, target_dir
        except Exception as e:
            return False, str(e)

    # ==================== IDE / EXTERNAL EDITORS ====================
    def detect_installed_editors(self) -> List[Dict[str, str]]:
        installed = []
        for ed in self.KNOWN_EDITORS:
            cmd_path = shutil.which(ed["cmd"])
            if cmd_path:
                installed.append({
                    "name": ed["name"],
                    "cmd": ed["cmd"],
                    "icon": ed["icon"],
                    "path": cmd_path
                })
        return installed

    def get_preferred_editor(self) -> Optional[Dict[str, str]]:
        installed = self.detect_installed_editors()
        if not installed:
            return None

        pref_cmd = self.config.get("preferred_editor")
        if pref_cmd:
            for ed in installed:
                if ed["cmd"] == pref_cmd:
                    return ed

        # Default preference order: code -> codium -> cursor -> kate
        return installed[0]

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set_setting(self, key: str, value: Any):
        self.config[key] = value
        self._save_json(CONFIG_FILE, self.config)

    def set_preferred_editor(self, cmd: str):
        self.config["preferred_editor"] = cmd
        self._save_json(CONFIG_FILE, self.config)

    def open_in_editor(self, repo_path: str, file_path: Optional[str] = None) -> bool:
        editor = self.get_preferred_editor()
        if not editor:
            return False

        target = os.path.join(repo_path, file_path) if file_path else repo_path
        try:
            subprocess.Popen([editor["cmd"], target], stdin=subprocess.DEVNULL, start_new_session=True)
            return True
        except Exception as e:
            print(f"Error launching editor: {e}")
            return False
