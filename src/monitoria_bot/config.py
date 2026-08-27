"""Módulo de carregamento e validação de configurações."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Carrega variáveis do arquivo .env sem sobrescrever variáveis já existentes no ambiente."""
    env_path = Path(path)
    if not env_path.is_file():
        return

    try:
        with env_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        sys.stderr.write(f"Aviso: Não foi possível ler o arquivo {env_path}: {e}\n")


@dataclass(frozen=True)
class Config:
    discord_token: str
    database_path: Path
    log_level: str
    ra_regex: re.Pattern[str]
    ra_regex_str: str
    discord_guild_id: int | None


def load_config(require_token: bool = True, env_file: str | Path = ".env") -> Config:
    """Carrega as configurações do ambiente e valida parâmetros essenciais."""
    load_dotenv(env_file)

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if require_token and not token:
        sys.stderr.write("Erro: A variável de ambiente DISCORD_TOKEN não foi informada.\n")
        sys.exit(1)

    db_path_raw = os.getenv("DATABASE_PATH", "./data/bot.db").strip()
    db_path = Path(db_path_raw).expanduser().resolve()

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = "INFO"

    ra_regex_str = os.getenv("RA_REGEX", r"^[A-Za-z0-9]{1,32}$").strip()
    try:
        ra_regex = re.compile(ra_regex_str)
    except re.error as e:
        sys.stderr.write(f"Aviso: RA_REGEX inválido ('{ra_regex_str}'): {e}. Usando padrão alfanumérico.\n")
        ra_regex_str = r"^[A-Za-z0-9]{1,32}$"
        ra_regex = re.compile(ra_regex_str)

    guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    guild_id: int | None = None
    if guild_id_raw:
        try:
            guild_id = int(guild_id_raw)
        except ValueError:
            sys.stderr.write(f"Aviso: DISCORD_GUILD_ID inválido ('{guild_id_raw}'). Ignorando.\n")

    return Config(
        discord_token=token,
        database_path=db_path,
        log_level=log_level,
        ra_regex=ra_regex,
        ra_regex_str=ra_regex_str,
        discord_guild_id=guild_id,
    )
