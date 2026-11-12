"""Runtime settings. API keys stay empty until the operator fills .env."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

_settings_logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "analytics.db"
CSV_DIR = DATA_DIR / "csv"
UPLOAD_DIR = DATA_DIR / "uploads"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
CHART_DIR = ARTIFACT_DIR / "charts"
LOG_DIR = PROJECT_ROOT / "logs"
AUDIT_PATH = LOG_DIR / "audit.jsonl"
TRACE_PATH = LOG_DIR / "traces.jsonl"

NVIDIA_HOST = "integrate.api.nvidia.com"
DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"
DEFAULT_BASE_URL = f"https://{NVIDIA_HOST}/v1"


def _pick(name: str, file_values: dict, default: str = "") -> str:
    env_val = os.getenv(name)
    file_val = file_values.get(name)
    if env_val is not None and str(env_val).strip() != "":
        return str(env_val).strip()
    if file_val is not None and str(file_val).strip() != "":
        return str(file_val).strip()
    if env_val is not None:
        return str(env_val).strip()
    return default


def _flag(value: str, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    nvidia_api_key: str
    nvidia_base_url: str
    nvidia_model: str
    nvidia_temperature: float
    nvidia_max_tokens: int
    nvidia_allow_hosts: tuple[str, ...]
    e2b_api_key: str
    db_connection_string: str
    langsmith_api_key: str
    hitl_enabled: bool
    sandbox_backend: str
    sandbox_timeout_seconds: int
    max_iterations: int
    max_tool_calls: int
    token_budget: int
    sql_context_rows: int = 20
    sql_fetch_rows: int = 200

    @property
    def nvidia_configured(self) -> bool:
        return bool(self.nvidia_api_key.strip())

    @property
    def use_sqlite(self) -> bool:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return True
        return not bool(self.db_connection_string.strip())


def _build_settings() -> Settings:
    file_values = {}
    if ENV_PATH.exists():
        loaded = dotenv_values(ENV_PATH)
        file_values = {k: v for k, v in loaded.items() if v is not None}

    def pick(name: str, default: str = "") -> str:
        return _pick(name, file_values, default)

    hosts = [NVIDIA_HOST]
    extra = pick("NVIDIA_ALLOW_HOSTS")
    if extra:
        hosts.extend(part.strip() for part in extra.split(",") if part.strip())

    temperature_raw = pick("NVIDIA_TEMPERATURE", "0")
    try:
        temperature = float(temperature_raw)
    except ValueError:
        temperature = 0.0

    settings = Settings(
        nvidia_api_key=pick("NVIDIA_API_KEY"),
        nvidia_base_url=pick("NVIDIA_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        nvidia_model=pick("NVIDIA_MODEL", DEFAULT_MODEL),
        nvidia_temperature=temperature,
        nvidia_max_tokens=_int(pick("NVIDIA_MAX_TOKENS", "1800"), 1800),
        nvidia_allow_hosts=tuple(dict.fromkeys(hosts)),
        e2b_api_key=pick("E2B_API_KEY"),
        db_connection_string=pick("DB_CONNECTION_STRING"),
        langsmith_api_key=pick("LANGSMITH_API_KEY"),
        hitl_enabled=_flag(pick("HITL_ENABLED"), False),
        sandbox_backend=pick("SANDBOX_BACKEND", "local") or "local",
        sandbox_timeout_seconds=_int(pick("SANDBOX_TIMEOUT_SECONDS", "30"), 30),
        max_iterations=_int(pick("MAX_ITERATIONS", "8"), 8),
        max_tool_calls=_int(pick("MAX_TOOL_CALLS", "10"), 10),
        token_budget=_int(pick("TOKEN_BUDGET", "12000"), 12000),
    )

    if temperature > 0:
        _settings_logger.warning(
            "NVIDIA_TEMPERATURE is %s — text-to-SQL accuracy is best at 0.", temperature
        )

    return settings


_settings_cache: Settings | None = None
_settings_lock = threading.Lock()
_settings_mtime: float = 0.0


def get_settings(*, reload: bool = False) -> Settings:
    global _settings_cache, _settings_mtime
    with _settings_lock:
        mtime = ENV_PATH.stat().st_mtime if ENV_PATH.exists() else 0.0
        if _settings_cache is None or reload or mtime != _settings_mtime:
            _settings_cache = _build_settings()
            _settings_mtime = mtime
        return _settings_cache


def invalidate_settings_cache() -> None:
    global _settings_cache
    with _settings_lock:
        _settings_cache = None


def assert_free_endpoint(base_url: str, allow_hosts: tuple[str, ...]) -> None:
    """Refuse paid providers. The default allow-list is NVIDIA's free API host."""
    host = (urlparse(base_url).hostname or "").lower()
    allowed = {item.lower() for item in allow_hosts}
    if host not in allowed:
        raise RuntimeError(
            f"Refusing to call {host or base_url}. This build only sends prompts to "
            f"NVIDIA's free API ({NVIDIA_HOST}). Point NVIDIA_BASE_URL back at that host, "
            "or set NVIDIA_ALLOW_HOSTS only for a free server you run yourself."
        )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)
