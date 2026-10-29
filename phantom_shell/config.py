from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    ollama_url: str = "http://localhost:11434"
    model: str = "gemma4:e4b"
    poll_seconds: int = 5
    cpu_threshold: float = 85.0
    cpu_consecutive_samples: int = 3
    memory_threshold: float = 90.0
    disk_free_threshold: float = 10.0
    process_memory_delta_bytes: int = 262144000
    history_retention_days: int = 30
    story_mode: bool = False
    plain_mode: bool = False
    log_level: str = "WARNING"
    database: Path = Path.home() / ".phantom-shell" / "history.sqlite3"
    timeout_seconds: int = 90

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        values: dict = {}
        config_path = path or Path(os.getenv("PHANTOM_CONFIG", Path.home() / ".phantom-shell" / "config.toml"))
        if config_path.exists():
            with config_path.open("rb") as handle:
                values = tomllib.load(handle)
            values = values.get("phantom", values)
        aliases = {
            "ollama_url": "PHANTOM_OLLAMA_URL", "model": "PHANTOM_MODEL",
            "poll_seconds": "PHANTOM_POLL_SECONDS", "cpu_threshold": "PHANTOM_CPU_THRESHOLD",
            "memory_threshold": "PHANTOM_MEMORY_THRESHOLD", "disk_free_threshold": "PHANTOM_DISK_FREE_THRESHOLD",
            "cpu_consecutive_samples": "PHANTOM_CPU_CONSECUTIVE_SAMPLES",
            "process_memory_delta_bytes": "PHANTOM_PROCESS_MEMORY_DELTA_BYTES",
            "history_retention_days": "PHANTOM_HISTORY_RETENTION_DAYS",
            "timeout_seconds": "PHANTOM_TIMEOUT_SECONDS", "database": "PHANTOM_DATABASE",
            "story_mode": "PHANTOM_STORY_MODE", "plain_mode": "PHANTOM_PLAIN_MODE",
            "log_level": "PHANTOM_LOG_LEVEL",
        }
        for key, env in aliases.items():
            if env in os.environ:
                raw = os.environ[env]
                expected = type(getattr(cls(), key))
                if expected is bool:
                    if raw.lower() not in {"true", "false", "1", "0", "yes", "no"}:
                        raise ValueError(f"{env} must be true or false")
                    values[key] = raw.lower() in {"true", "1", "yes"}
                else:
                    values[key] = expected(raw)
        known = {field for field in cls.__dataclass_fields__}
        unknown = set(values) - known
        if unknown:
            raise ValueError("Unknown configuration key(s): " + ", ".join(sorted(unknown)))
        if "database" in values:
            values["database"] = Path(values["database"])
        config = cls(**{k: v for k, v in values.items() if k in known})
        if type(config.poll_seconds) is not int or type(config.cpu_consecutive_samples) is not int or type(config.history_retention_days) is not int or type(config.process_memory_delta_bytes) is not int:
            raise ValueError("polling, sample count, memory delta and retention settings must be integers")
        if any(type(getattr(config, key)) not in (int, float) for key in ("cpu_threshold", "memory_threshold", "disk_free_threshold")):
            raise ValueError("resource thresholds must be numbers")
        parsed_url = urlparse(config.ollama_url)
        if parsed_url.scheme not in {"http", "https"} or parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed_url.username or parsed_url.password or parsed_url.path not in {"", "/"} or parsed_url.query or parsed_url.fragment:
            raise ValueError("ollama_url must point to localhost so prompts remain on this machine")
        if not isinstance(config.model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", config.model):
            raise ValueError("model must be a valid local Ollama model tag")
        if config.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        if not 1 <= config.poll_seconds <= 3600:
            raise ValueError("poll_seconds must be between 1 and 3600")
        for key in ("cpu_threshold", "memory_threshold", "disk_free_threshold"):
            if not 0 <= getattr(config, key) <= 100:
                raise ValueError(f"{key} must be between 0 and 100")
        if config.cpu_consecutive_samples < 1:
            raise ValueError("cpu_consecutive_samples must be at least 1")
        if config.process_memory_delta_bytes < 1 or not 1 <= config.history_retention_days <= 3650:
            raise ValueError("process_memory_delta_bytes and history_retention_days must be positive and bounded")
        if not 1 <= config.timeout_seconds <= 900:
            raise ValueError("timeout_seconds must be between 1 and 900")
        return config
