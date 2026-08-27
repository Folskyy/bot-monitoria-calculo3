"""Testes para o OfficeHoursCog (/horarios e /horarios-definir)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands
import pytest

from monitoria_bot.cogs.office_hours import OfficeHoursCog
from monitoria_bot.config import Config, load_config
from monitoria_bot.database import Database


@pytest.fixture
async def test_db(tmp_path: Path):
    db = Database(tmp_path / "hours_test.db")
    await db.init_db()
    yield db
    await db.close()


@pytest.fixture
def mock_config(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=dummy\n", encoding="utf-8")
    return load_config(require_token=True, env_file=env_file)


@pytest.fixture
def mock_bot():
    return MagicMock(spec=commands.Bot)


async def test_horarios_display(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = OfficeHoursCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings(
        "10", "1", "2", "3", "4", "5",
        office_hours_text="Segundas e Quartas das 14h às 16h",
        timezone_str="America/Sao_Paulo",
    )

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 10
    interaction.user = MagicMock(spec=discord.Member)
    interaction.response = AsyncMock()

    await cog.horarios.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Segundas e Quartas" in embed.description
    assert "America/Sao_Paulo" in embed.footer.text


async def test_horarios_definir_permission_and_update(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = OfficeHoursCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "3", "4", "5")

    # 1. Aluno sem cargo de monitor tenta alterar
    interaction_student = MagicMock(spec=discord.Interaction)
    interaction_student.guild = MagicMock(spec=discord.Guild)
    interaction_student.guild.id = 10
    student_member = MagicMock(spec=discord.Member)
    student_member.guild_permissions.administrator = False
    student_member.roles = []
    interaction_student.user = student_member
    interaction_student.response = AsyncMock()

    await cog.horarios_definir.callback(cog, interaction_student, texto="Novo Horário")
    msg = interaction_student.response.send_message.call_args[0][0]
    assert "Permissão negada" in msg

    # 2. Monitor altera
    interaction_monitor = MagicMock(spec=discord.Interaction)
    interaction_monitor.guild = MagicMock(spec=discord.Guild)
    interaction_monitor.guild.id = 10
    monitor_member = MagicMock(spec=discord.Member)
    monitor_member.guild_permissions.administrator = True
    interaction_monitor.user = monitor_member
    interaction_monitor.response = AsyncMock()

    await cog.horarios_definir.callback(cog, interaction_monitor, texto="Sexta das 10h às 12h")
    settings = await test_db.get_guild_settings("10")
    assert settings is not None
    assert settings.office_hours_text == "Sexta das 10h às 12h"
