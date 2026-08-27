"""Testes para o QueueCog (/fila entrar, sair, listar, proximo, encerrar, limpar)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands
import pytest

from monitoria_bot.cogs.queue import QueueCog
from monitoria_bot.config import Config, load_config
from monitoria_bot.database import Database


@pytest.fixture
async def test_db(tmp_path: Path):
    db = Database(tmp_path / "queue_test.db")
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


async def test_fila_entrar_and_duplicate(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = QueueCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "30", "100", "200")
    await test_db.create_pending_student("10", "55", "Aluno Fila", "123")
    await test_db.activate_student("10", "55")

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 10
    member = MagicMock(spec=discord.Member)
    member.id = 55
    role = MagicMock(spec=discord.Role)
    role.id = 100
    member.roles = [role]
    interaction.user = member
    interaction.response = AsyncMock()

    # 1. Entra na fila com sucesso
    await cog.entrar.callback(cog, interaction, assunto="Teorema de Stokes")
    msg1 = interaction.response.send_message.call_args[0][0]
    assert "entrou na fila" in msg1

    # 2. Tenta entrar novamente
    interaction.response = AsyncMock()
    await cog.entrar.callback(cog, interaction, assunto="Outro assunto")
    msg2 = interaction.response.send_message.call_args[0][0]
    assert "já possui uma entrada ativa" in msg2


async def test_fila_sair(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = QueueCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "30", "100", "200")
    await test_db.create_pending_student("10", "55", "Aluno", "123")
    await test_db.activate_student("10", "55")
    await test_db.enqueue("10", "55", "Assunto")

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 10
    member = MagicMock(spec=discord.Member)
    member.id = 55
    interaction.user = member
    interaction.response = AsyncMock()

    await cog.sair.callback(cog, interaction)
    msg = interaction.response.send_message.call_args[0][0]
    assert "saiu da fila" in msg


async def test_fila_proximo_and_encerrar(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = QueueCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "30", "100", "200")
    await test_db.enqueue("10", "55", "Integral Tripla")

    # Monitor chama próximo
    interaction_monitor = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 10
    interaction_monitor.guild = guild
    monitor_member = MagicMock(spec=discord.Member)
    monitor_member.id = 999
    monitor_member.mention = "<@999>"
    monitor_role = MagicMock(spec=discord.Role)
    monitor_role.id = 200
    monitor_member.roles = [monitor_role]
    interaction_monitor.user = monitor_member
    interaction_monitor.response = AsyncMock()

    queue_ch = MagicMock(spec=discord.TextChannel)
    queue_ch.send = AsyncMock()
    guild.get_channel.return_value = queue_ch
    student_member = MagicMock(spec=discord.Member)
    student_member.mention = "<@55>"
    guild.get_member.return_value = student_member

    await cog.proximo.callback(cog, interaction_monitor)
    queue_ch.send.assert_awaited_once()
    msg_called = queue_ch.send.call_args[1].get("content")
    assert "<@55>" in msg_called
    assert "é a sua vez" in msg_called

    # Tenta chamar próximo sem encerrar o atual
    interaction_monitor.response = AsyncMock()
    await cog.proximo.callback(cog, interaction_monitor)
    msg_blocked = interaction_monitor.response.send_message.call_args[0][0]
    assert "Já existe um atendimento em andamento" in msg_blocked

    # Monitor encerra atendimento
    interaction_monitor.response = AsyncMock()
    await cog.encerrar.callback(cog, interaction_monitor)
    msg_end = interaction_monitor.response.send_message.call_args[0][0]
    assert "encerrado com sucesso" in msg_end
