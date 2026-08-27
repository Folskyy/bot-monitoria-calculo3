"""Testes para o DoubtsCog (/duvida criar, /duvida minhas e /duvida resolver)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands
import pytest

from monitoria_bot.cogs.doubts import DoubtsCog
from monitoria_bot.config import Config, load_config
from monitoria_bot.database import Database


@pytest.fixture
async def test_db(tmp_path: Path):
    db = Database(tmp_path / "doubts_test.db")
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


async def test_duvida_criar_unregistered_forbidden(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = DoubtsCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "20", "3", "100", "200")

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 10
    member = MagicMock(spec=discord.Member)
    member.id = 50
    member.guild_permissions.administrator = False
    member.roles = []
    interaction.user = member
    interaction.response = AsyncMock()

    await cog.criar.callback(cog, interaction, assunto="Cálculo", titulo="Dúvida", descricao="Detalhes")
    interaction.response.send_message.assert_awaited_once()
    msg = interaction.response.send_message.call_args[0][0]
    assert "realizar seu cadastro" in msg


async def test_duvida_criar_success(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = DoubtsCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "20", "3", "100", "200")
    await test_db.create_pending_student("10", "50", "Aluno Ativo", "12345")
    await test_db.activate_student("10", "50")

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 10
    interaction.guild = guild
    member = MagicMock(spec=discord.Member)
    member.id = 50
    member.mention = "<@50>"
    role = MagicMock(spec=discord.Role)
    role.id = 100
    member.roles = [role]
    interaction.user = member
    interaction.id = 999111
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 20
    channel.mention = "<#20>"
    guild.get_channel.return_value = channel

    sent_msg = MagicMock(spec=discord.Message)
    sent_msg.id = 7777
    created_thread = MagicMock(spec=discord.Thread)
    created_thread.id = 8888
    created_thread.mention = "<#8888>"
    sent_msg.create_thread = AsyncMock(return_value=created_thread)
    channel.send = AsyncMock(return_value=sent_msg)

    await cog.criar.callback(
        cog,
        interaction,
        assunto="Derivadas",
        titulo="Regra da Cadeia em R3",
        descricao="Como aplicar a árvore de dependências?",
    )

    channel.send.assert_awaited_once()
    sent_msg.create_thread.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()

    doubt = await test_db.get_doubt("10", 1)
    assert doubt is not None
    assert doubt.status == "open"
    assert doubt.message_id == "7777"
    assert doubt.thread_id == "8888"


async def test_duvida_resolver_permissions(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = DoubtsCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "20", "3", "100", "200")
    # Cria uma dúvida pertencente ao autor 50
    doubt = await test_db.create_doubt_started("10", "50", "int_1", "Assunto", "Titulo", "Desc", "20")
    await test_db.complete_doubt_creation("10", doubt.id, "msg_1", "th_1")

    # 1. Outro aluno tenta resolver -> Negado
    interaction_other = MagicMock(spec=discord.Interaction)
    interaction_other.guild = MagicMock(spec=discord.Guild)
    interaction_other.guild.id = 10
    other_member = MagicMock(spec=discord.Member)
    other_member.id = 999
    other_member.guild_permissions.administrator = False
    other_member.roles = []
    interaction_other.user = other_member
    interaction_other.response = AsyncMock()

    await cog.resolver.callback(cog, interaction_other, id=doubt.id)
    msg_fail = interaction_other.response.send_message.call_args[0][0]
    assert "Permissão negada" in msg_fail

    # 2. Autor resolve -> Sucesso
    interaction_author = MagicMock(spec=discord.Interaction)
    interaction_author.guild = MagicMock(spec=discord.Guild)
    interaction_author.guild.id = 10
    author_member = MagicMock(spec=discord.Member)
    author_member.id = 50
    author_member.mention = "<@50>"
    interaction_author.user = author_member
    interaction_author.response = AsyncMock()

    thread_mock = MagicMock(spec=discord.Thread)
    thread_mock.send = AsyncMock()
    thread_mock.edit = AsyncMock()
    interaction_author.guild.get_thread.return_value = thread_mock

    await cog.resolver.callback(cog, interaction_author, id=doubt.id)
    msg_ok = interaction_author.response.send_message.call_args[0][0]
    assert "marcada como resolvida" in msg_ok

    updated_doubt = await test_db.get_doubt("10", doubt.id)
    assert updated_doubt is not None
    assert updated_doubt.status == "resolved"
