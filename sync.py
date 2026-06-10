"""
云端同步模块：GitHub 作为数据持久层
- pull_db(): 启动时从 GitHub 拉取最新数据
- push_db(): 保存后推送数据到 GitHub
"""
import os, subprocess, sys

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_DIR, "experiment_data")


def _run_git(args: list[str]) -> tuple[bool, str]:
    """执行 git 命令"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=REPO_DIR,
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def is_git_available() -> bool:
    ok, _ = _run_git(["--version"])
    return ok


def pull_db() -> bool:
    """从 GitHub 拉取最新数据（覆盖本地）"""
    if not is_git_available():
        return False
    # Stash 本地修改，pull，再恢复
    _run_git(["stash"])
    _run_git(["pull", "origin", "main"])
    _run_git(["stash", "pop"])
    return True


def push_db(message: str = "auto-save") -> bool:
    """推送数据到 GitHub"""
    if not is_git_available():
        return False
    _run_git(["add", "experiment_data/"])
    _run_git(["commit", "-m", message])
    # 只推数据文件，不强制
    _run_git(["push", "origin", "main"])
    return True


def check_cloud_env() -> bool:
    """检测是否在 Streamlit Cloud 环境"""
    return os.getenv("STREAMLIT_SHARING_MODE") is not None
