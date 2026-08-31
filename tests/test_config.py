"""Testes unitários para o módulo config."""

import os
from pathlib import Path
import pytest

from monitoria_bot.config import load_config, load_dotenv


def test_load_dotenv(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comentário\n"
        "DISCORD_TOKEN=secret_token_123\n"
        "DATABASE_PATH=/custom/path/bot.db\n"
        "LOG_LEVEL=DEBUG\n"
        "RA_REGEX=^[0-9]{5,10}$\n"
        'QUOTED_VAR="value_with_quotes"\n',
        encoding="utf-8",
    )

    # Limpa variáveis se existirem no ambiente
    for key in ["DISCORD_TOKEN", "DATABASE_PATH", "LOG_LEVEL", "RA_REGEX", "QUOTED_VAR"]:
        os.environ.pop(key, None)

    load_dotenv(env_file)

    assert os.environ.get("DISCORD_TOKEN") == "secret_token_123"
    assert os.environ.get("DATABASE_PATH") == "/custom/path/bot.db"
    assert os.environ.get("LOG_LEVEL") == "DEBUG"
    assert os.environ.get("RA_REGEX") == "^[0-9]{5,10}$"
    assert os.environ.get("QUOTED_VAR") == "value_with_quotes"


def test_load_dotenv_does_not_overwrite():
    os.environ["EXISTING_VAR"] = "original"
    # Carrega arquivo fictício
    load_dotenv()
    assert os.environ["EXISTING_VAR"] == "original"


def test_load_config_missing_token_exits():
    os.environ.pop("DISCORD_TOKEN", None)
    with pytest.raises(SystemExit) as exc_info:
        load_config(require_token=True, env_file="/nonexistent/.env")
    assert exc_info.value.code == 1


def test_load_config_success(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=my_bot_token\n"
        f"DATABASE_PATH={tmp_path}/data/test.db\n"
        "LOG_LEVEL=warning\n"
        "LOG_FILE=custom_bot.log\n"
        "RA_REGEX=^[A-Z0-9]{3,10}$\n"
        "DISCORD_GUILD_ID=123456789\n",
        encoding="utf-8",
    )
    for key in ["DISCORD_TOKEN", "DATABASE_PATH", "LOG_LEVEL", "LOG_FILE", "RA_REGEX", "DISCORD_GUILD_ID"]:
        os.environ.pop(key, None)

    cfg = load_config(require_token=True, env_file=env_file)
    assert cfg.discord_token == "my_bot_token"
    assert cfg.database_path == (tmp_path / "data" / "test.db").resolve()
    assert cfg.log_level == "WARNING"
    assert cfg.log_file == Path("custom_bot.log").resolve()
    assert cfg.ra_regex_str == "^[A-Z0-9]{3,10}$"
    assert cfg.ra_regex.match("ABC123")
    assert cfg.discord_guild_id == 123456789


def test_load_config_fallback_invalid_regex(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=token\n"
        "RA_REGEX=[invalid_regex(\n",
        encoding="utf-8",
    )
    for key in ["DISCORD_TOKEN", "RA_REGEX"]:
        os.environ.pop(key, None)

    cfg = load_config(require_token=True, env_file=env_file)
    assert cfg.ra_regex_str == r"^[A-Za-z0-9]{1,32}$"
    assert cfg.ra_regex.match("RA123456")
