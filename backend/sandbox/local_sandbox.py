"""One-shot Python process with an import allow-list and a file jail.

This is not a VM. It is the stand-in for E2B / Docker --network=none on a machine
that has neither. Direct network, process, and database imports are rejected,
and file access is limited to the workspace plus the interpreter's own libraries.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.config import CHART_DIR, get_settings
from backend.security.ast_guard import check_python

_RUNNER = textwrap.dedent(
    r'''
    import importlib.abc
    import os
    import sys
    import sysconfig

    SANDBOX_ROOT = os.path.realpath(os.environ["SANDBOX_ROOT"])
    READ_ROOTS = {SANDBOX_ROOT}
    for prefix in (sys.prefix, getattr(sys, "base_prefix", sys.prefix), os.path.dirname(sys.executable)):
        if prefix:
            READ_ROOTS.add(os.path.realpath(prefix))
    for path in sysconfig.get_paths().values():
        if isinstance(path, str) and path:
            READ_ROOTS.add(os.path.realpath(path))
    DEVICE_READS = {"/dev/urandom", "/dev/null", "/dev/zero"}

    def _inside(path, roots):
        try:
            real = os.path.realpath(path)
        except Exception:
            return False
        if real in DEVICE_READS and roots is READ_ROOTS:
            return True
        for root in roots:
            if real == root or real.startswith(root + os.sep):
                return True
        return False

    def _assert_read(path):
        if not _inside(path, READ_ROOTS):
            raise PermissionError("read blocked outside the sandbox: %s" % path)

    def _assert_write(path):
        if not _inside(path, {SANDBOX_ROOT}):
            raise PermissionError("write blocked outside the sandbox: %s" % path)

    def _writes(mode):
        if isinstance(mode, int):
            flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
            return bool(mode & flags)
        return any(flag in str(mode) for flag in ("w", "a", "x", "+"))

    import builtins
    import io as _io

    _real_open = builtins.open

    def _safe_open(file, mode="r", *args, **kwargs):
        if not isinstance(file, (str, bytes, os.PathLike)):
            return _real_open(file, mode, *args, **kwargs)
        path = os.fspath(file)
        if _writes(mode):
            _assert_write(path)
        else:
            _assert_read(path)
        return _real_open(file, mode, *args, **kwargs)

    builtins.open = _safe_open
    _io.open = _safe_open

    _real_os_open = os.open

    def _safe_os_open(path, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is not None:
            raise PermissionError("dir_fd is blocked")
        if _writes(flags):
            _assert_write(path)
        else:
            _assert_read(path)
        return _real_os_open(path, flags, mode)

    os.open = _safe_os_open

    def _blocked(*_args, **_kwargs):
        raise PermissionError("this operation is blocked in the sandbox")

    for _name in (
        "system", "popen", "execv", "execve", "execvp", "execvpe",
        "spawnv", "spawnve", "spawnvp", "spawnvpe", "remove", "unlink",
        "rmdir", "removedirs", "rename", "renames", "replace", "link",
        "symlink", "kill", "killpg",
    ):
        if hasattr(os, _name):
            setattr(os, _name, _blocked)

    def _neuter(module_name, names):
        try:
            module = __import__(module_name, fromlist=["*"] if "." in module_name else [])
        except Exception:
            return
        for name in names:
            if hasattr(module, name):
                setattr(module, name, _blocked)

    _neuter("socket", ("socket", "create_connection", "create_server", "socketpair"))
    _neuter("sqlite3", ("connect",))
    _neuter("subprocess", ("Popen", "run", "call", "check_call", "check_output"))
    _neuter("shutil", ("rmtree", "move", "copy", "copy2", "copytree", "chown"))
    _neuter("urllib.request", ("urlopen", "urlretrieve"))

    class _Banner(importlib.abc.MetaPathFinder):
        banned = {
            "socket", "requests", "urllib3", "subprocess", "multiprocessing",
            "pty", "pickle", "shelve", "ftplib", "smtplib", "imaplib", "poplib",
            "xmlrpc", "webbrowser", "socketserver", "httpx", "aiohttp", "pip",
            "ensurepip", "telnetlib", "nntplib", "cgi", "code", "codeop",
            "sqlite3", "ctypes",
        }

        def find_spec(self, fullname, path, target=None):
            root = fullname.split(".", 1)[0]
            if fullname not in self.banned and root not in self.banned:
                return None
            # Block the import only when user code asks for it. numpy and
            # matplotlib import pickle and ctypes while they load.
            frame = sys._getframe()
            while frame is not None:
                filename = frame.f_code.co_filename or ""
                if "importlib" in filename or filename.endswith("runner.py"):
                    frame = frame.f_back
                    continue
                if filename.endswith("user_code.py"):
                    raise ImportError("import of %s is blocked in the sandbox" % fullname)
                return None
            return None

    sys.meta_path.insert(0, _Banner())

    try:
        import resource
        cpu = int(os.environ.get("SANDBOX_CPU_SECONDS", "20"))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
    except Exception:
        pass

    os.environ["MPLBACKEND"] = "Agg"
    user_globals = {"__name__": "__main__"}
    exit_code = 0
    try:
        source = _safe_open("user_code.py", "r", encoding="utf-8").read()
        exec(compile(source, "user_code.py", "exec"), user_globals)
    except SystemExit as exc:
        exit_code = int(exc.code or 0)
    except Exception as exc:
        sys.stderr.write("ERROR: %s: %s\n" % (type(exc).__name__, exc))
        exit_code = 1
    finally:
        if "matplotlib" in sys.modules:
            try:
                import matplotlib.pyplot as plt
                figure = plt.gcf()
                if figure.axes and not os.path.exists("chart.png"):
                    figure.savefig("chart.png", bbox_inches="tight")
                plt.close("all")
            except Exception:
                pass
    raise SystemExit(exit_code)
    '''
).lstrip()


@dataclass
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    chart_path: str | None
    error: str | None


def execute_in_sandbox(code: str, workspace: Path, *, timeout: int | None = None, skip_ast: bool = False) -> SandboxResult:
    settings = get_settings()
    if settings.sandbox_backend != "local":
        return SandboxResult(
            ok=False,
            stdout="",
            stderr="",
            chart_path=None,
            error="Only the local sandbox is enabled. E2B and Docker are not used in this build.",
        )
    if settings.e2b_api_key:
        # The key is ignored on purpose. Do not construct an E2B client.
        pass
    if not skip_ast:
        errors = check_python(code)
        if errors:
            return SandboxResult(False, "", "\n".join(errors), None, "\n".join(errors))

    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "user_code.py").write_text(code, encoding="utf-8")
    (workspace / "runner.py").write_text(_RUNNER, encoding="utf-8")
    limit = timeout or settings.sandbox_timeout_seconds
    env = _child_env(workspace, limit)
    proc = subprocess.Popen(
        [sys.executable, "-I", "runner.py"],
        cwd=workspace,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        _kill(proc)
        return SandboxResult(False, "", "Sandbox timed out.", None, "Sandbox timed out.")
    stdout = (stdout or "")[:8000]
    stderr = (stderr or "")[:8000]
    chart = _publish_chart(workspace)
    if proc.returncode not in (0, None) and proc.returncode < 0:
        killed = -proc.returncode
        if killed in {signal.SIGXCPU, signal.SIGKILL, signal.SIGTERM}:
            message = "Sandbox timed out."
            return SandboxResult(False, stdout, stderr or message, chart, message)
    ok = proc.returncode == 0
    error = None if ok else (stderr.strip() or "Python execution failed.")
    return SandboxResult(ok, stdout, stderr, chart, error)


def _child_env(workspace: Path, timeout: int) -> dict[str, str]:
    blocked_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "DSN")
    blocked_names = {
        "NVIDIA_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "E2B_API_KEY",
        "LANGSMITH_API_KEY",
        "DB_CONNECTION_STRING",
        "PYTHONPATH",
        "PYTHONHOME",
    }
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if key in blocked_names or any(marker in upper for marker in blocked_markers):
            continue
        env[key] = value
    root = str(workspace.resolve())
    env.update(
        {
            "HOME": root,
            "TMPDIR": root,
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": root,
            "SANDBOX_ROOT": root,
            "SANDBOX_CPU_SECONDS": str(max(1, timeout)),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": env.get("LANG", "C.UTF-8"),
        }
    )
    return env


def _kill(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _publish_chart(workspace: Path) -> str | None:
    source = workspace / "chart.png"
    if not source.is_file() or source.stat().st_size < 32:
        return None
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    target = CHART_DIR / f"chart_{uuid.uuid4().hex}.png"
    target.write_bytes(source.read_bytes())
    return str(target)
