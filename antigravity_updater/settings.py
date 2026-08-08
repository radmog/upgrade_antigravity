"""Configuração persistente e validada do atualizador."""

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Settings:
    channel: str = "stable"
    policy: str = "latest"
    retention: int = 2
    cache_ttl: int = 3600
    notifications: str = "off"
    log_level: str = "INFO"
    pin_hub: Optional[str] = None
    pin_ide: Optional[str] = None


FIELDS = frozenset(asdict(Settings()))
CHOICES = {
    "channel": ("stable", "preview"),
    "policy": ("latest", "notify-only"),
    "notifications": ("off", "auto", "desktop"),
    "log_level": ("DEBUG", "INFO", "WARNING", "ERROR"),
}


def validate(settings: Settings) -> Settings:
    for field, choices in CHOICES.items():
        if getattr(settings, field) not in choices:
            raise ValueError(f"Valor inválido para {field}: {getattr(settings, field)}")
    if type(settings.retention) is not int or settings.retention < 1 or settings.retention > 100:
        raise ValueError("retention precisa estar entre 1 e 100.")
    if type(settings.cache_ttl) is not int or settings.cache_ttl < 0 or settings.cache_ttl > 604800:
        raise ValueError("cache_ttl precisa estar entre 0 e 604800 segundos.")
    for field in ("pin_hub", "pin_ide"):
        value = getattr(settings, field)
        if value is not None and (not isinstance(value, str) or not value.strip() or "/" in value):
            raise ValueError(f"Valor inválido para {field}.")
    return settings


def from_dict(data: Dict[str, Any]) -> Settings:
    unknown = set(data) - FIELDS
    if unknown:
        raise ValueError(f"Chaves de configuração desconhecidas: {', '.join(sorted(unknown))}")
    try:
        settings = Settings(**data)
    except TypeError as error:
        raise ValueError(f"Configuração inválida: {error}") from error
    return validate(settings)


def load(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"O caminho de configuração não é um arquivo regular: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Não foi possível ler a configuração: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("A configuração precisa ser um objeto JSON.")
    return from_dict(data)


def save(
    path: Path,
    settings: Settings,
    mode: int = 0o600,
    directory_mode: int = 0o700,
) -> None:
    validate(settings)
    path.parent.mkdir(mode=directory_mode, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError(f"Diretório de configuração inseguro: {path.parent}")
    path.parent.chmod(directory_mode)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(asdict(settings), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_value(field: str, value: str) -> Any:
    if field not in FIELDS:
        raise ValueError(f"Chave de configuração desconhecida: {field}")
    if field in ("retention", "cache_ttl"):
        try:
            return int(value)
        except ValueError as error:
            raise ValueError(f"{field} precisa ser um número inteiro.") from error
    if field in ("pin_hub", "pin_ide") and value.lower() in ("none", "null", "off", ""):
        return None
    return value.upper() if field == "log_level" else value.lower()


def with_value(current: Settings, field: str, value: str) -> Settings:
    return validate(replace(current, **{field: parse_value(field, value)}))


def public_dict(settings: Settings) -> Dict[str, Any]:
    return asdict(settings)
