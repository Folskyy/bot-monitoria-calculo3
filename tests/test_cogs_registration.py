"""Testes para o RegistrationCog (/cadastro, /meu-cadastro, /aluno-editar, /ajuda)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands
import pytest

from monitoria_bot.cogs.registration import RegistrationCog
from monitoria_bot.config import Config, load_config
from monitoria_bot.database import Database


@pytest.fixture
async def test_db(tmp_path: Path):
    db = Database(tmp_path / "reg_test.db")
    await db.init_db()
    yield db
    await db.close()


@pytest.fixture
def mock_config(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=dummy\nRA_REGEX=^[A-Za-z0-9]{1,32}$\n", encoding="utf-8")
    return load_config(require_token=True, env_file=env_file)


@pytest.fixture
def mock_bot():
    return MagicMock(spec=commands.Bot)


async def test_cadastro_opens_modal_unregistered(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = RegistrationCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "3", "4", "5")

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 10
    member = MagicMock(spec=discord.Member)
    member.id = 99
    interaction.user = member
    interaction.response = AsyncMock()

    await cog.cadastro.callback(cog, interaction)
    interaction.response.send_modal.assert_awaited_once()


async def test_meu_cadastro_displays_info(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = RegistrationCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "3", "4", "5")
    await test_db.create_pending_student("10", "99", "Lucas Silva", "009988", "Turma B")
    await test_db.activate_student("10", "99")

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 10
    member = MagicMock(spec=discord.Member)
    member.id = 99
    interaction.user = member
    interaction.response = AsyncMock()

    await cog.meu_cadastro.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Lucas Silva" in embed.fields[0].value
    assert "009988" in embed.fields[1].value


async def test_aluno_editar_non_monitor_forbidden(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = RegistrationCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "3", "4", "5")

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 10
    member = MagicMock(spec=discord.Member)
    member.id = 99
    member.guild_permissions.administrator = False
    member.roles = []  # sem cargo de monitor
    interaction.user = member
    interaction.response = AsyncMock()

    target_student = MagicMock(spec=discord.Member)

    await cog.aluno_editar.callback(cog, interaction, aluno=target_student)
    msg = interaction.response.send_message.call_args[0][0]
    assert "Permissão negada" in msg


async def test_ajuda_command(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = RegistrationCog(mock_bot, test_db, mock_config)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = AsyncMock()

    await cog.ajuda.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True
    assert "Central de Ajuda" in kwargs.get("embed").title
