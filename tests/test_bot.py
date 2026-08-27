"""Testes para a classe principal MonitoriaBot."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monitoria_bot.bot import INITIAL_EXTENSIONS, MonitoriaBot
from monitoria_bot.config import Config, load_config
from monitoria_bot.database import Database
from monitoria_bot.views.persistent import RegistrationView


@pytest.fixture
async def test_db(tmp_path: Path):
    db = Database(tmp_path / "bot_test.db")
    yield db
    await db.close()


@pytest.fixture
def mock_config(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=dummy_token\nDISCORD_GUILD_ID=123456\n", encoding="utf-8")
    return load_config(require_token=True, env_file=env_file)


async def test_bot_setup_hook_loads_extensions_and_views(test_db: Database, mock_config: Config):
    bot = MonitoriaBot(config=mock_config, db=test_db)

    bot.load_extension = AsyncMock()
    bot.add_view = MagicMock()
    bot.tree.copy_global_to = MagicMock()
    bot.tree.sync = AsyncMock()

    await bot.setup_hook()

    # Banco inicializado
    assert test_db._conn is not None

    # View persistente registrada
    bot.add_view.assert_called_once()
    registered_view = bot.add_view.call_args[0][0]
    assert isinstance(registered_view, RegistrationView)
    assert registered_view.timeout is None
    assert registered_view.children[0].custom_id == "monitoria:btn_register"

    # Todas as extensões carregadas
    assert bot.load_extension.await_count == len(INITIAL_EXTENSIONS)
    loaded = [call[0][0] for call in bot.load_extension.call_args_list]
    assert "monitoria_bot.cogs.admin" in loaded
    assert "monitoria_bot.cogs.registration" in loaded
    assert "monitoria_bot.cogs.queue" in loaded

    # Sincronização executada
    bot.tree.sync.assert_awaited_once()

    await bot.close()
