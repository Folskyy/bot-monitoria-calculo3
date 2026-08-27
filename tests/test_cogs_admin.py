"""Testes para o Cog AdminCog (/configurar e /boas-vindas)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import pytest

from monitoria_bot.cogs.admin import AdminCog
from monitoria_bot.config import Config, load_config
from monitoria_bot.database import Database


@pytest.fixture
async def test_db(tmp_path: Path):
    db = Database(tmp_path / "admin_test.db")
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
    bot = MagicMock(spec=commands.Bot)
    return bot


async def test_configurar_non_admin_forbidden(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = AdminCog(mock_bot, test_db, mock_config)

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = False
    interaction.guild = guild
    interaction.user = member
    interaction.response = AsyncMock()

    await cog.configurar.callback(
        cog,
        interaction,
        canal_boas_vindas=MagicMock(),
        canal_duvidas=MagicMock(),
        canal_fila=MagicMock(),
        cargo_aluno=MagicMock(),
        cargo_monitor=MagicMock(),
    )

    interaction.response.send_message.assert_awaited_once()
    msg = interaction.response.send_message.call_args[0][0]
    assert "Permissão negada" in msg


async def test_configurar_dangerous_role_rejected(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = AdminCog(mock_bot, test_db, mock_config)

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = True
    interaction.guild = guild
    interaction.user = member
    interaction.response = AsyncMock()

    # Cargo com permissão de ban
    role = MagicMock(spec=discord.Role)
    role.id = 123
    role.managed = False
    perms = discord.Permissions.none()
    perms.ban_members = True
    role.permissions = perms

    await cog.configurar.callback(
        cog,
        interaction,
        canal_boas_vindas=MagicMock(),
        canal_duvidas=MagicMock(),
        canal_fila=MagicMock(),
        cargo_aluno=role,
        cargo_monitor=MagicMock(),
    )

    msg = interaction.response.send_message.call_args[0][0]
    assert "Falha na validação do cargo Aluno" in msg


async def test_configurar_success(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = AdminCog(mock_bot, test_db, mock_config)

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = True
    interaction.guild = guild
    interaction.user = member
    interaction.response = AsyncMock()

    # Bot member
    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_role = MagicMock(spec=discord.Role)
    bot_role.__le__ = lambda self, other: False
    bot_member.top_role = bot_role
    guild.me = bot_member

    # Student role
    role_student = MagicMock(spec=discord.Role)
    role_student.id = 100
    role_student.mention = "<@&100>"
    role_student.managed = False
    role_student.permissions = discord.Permissions.none()

    role_monitor = MagicMock(spec=discord.Role)
    role_monitor.id = 200
    role_monitor.mention = "<@&200>"

    # Channels
    ch_welcome = MagicMock(spec=discord.TextChannel)
    ch_welcome.id = 10
    ch_welcome.mention = "<#10>"
    ch_welcome.guild = guild

    ch_doubts = MagicMock(spec=discord.TextChannel)
    ch_doubts.id = 20
    ch_doubts.mention = "<#20>"
    ch_doubts.guild = guild

    ch_queue = MagicMock(spec=discord.TextChannel)
    ch_queue.id = 30
    ch_queue.mention = "<#30>"
    ch_queue.guild = guild

    # Perms on channels
    full_perms = discord.Permissions.all()
    ch_welcome.permissions_for.return_value = full_perms
    ch_doubts.permissions_for.return_value = full_perms
    ch_queue.permissions_for.return_value = full_perms

    await cog.configurar.callback(
        cog,
        interaction,
        canal_boas_vindas=ch_welcome,
        canal_duvidas=ch_doubts,
        canal_fila=ch_queue,
        cargo_aluno=role_student,
        cargo_monitor=role_monitor,
        texto_horarios="Terças e Quintas 15h",
    )

    msg = interaction.response.send_message.call_args[0][0]
    assert "Configurações da monitoria atualizadas com sucesso" in msg

    saved = await test_db.get_guild_settings("12345")
    assert saved is not None
    assert saved.welcome_channel_id == "10"
    assert saved.doubts_channel_id == "20"
    assert saved.office_hours_text == "Terças e Quintas 15h"


async def test_boas_vindas_publish_new_and_edit_existing(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = AdminCog(mock_bot, test_db, mock_config)

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = True
    interaction.guild = guild
    interaction.user = member
    interaction.response = AsyncMock()

    # Pre-save settings
    await test_db.upsert_guild_settings("12345", "10", "20", "30", "100", "200")

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 10
    channel.mention = "<#10>"
    sent_msg = MagicMock(spec=discord.Message)
    sent_msg.id = 8888
    channel.send = AsyncMock(return_value=sent_msg)
    guild.get_channel.return_value = channel

    # 1. Primeira publicação cria mensagem nova
    await cog.boas_vindas.callback(cog, interaction)
    channel.send.assert_awaited_once()

    settings_after_pub = await test_db.get_guild_settings("12345")
    assert settings_after_pub is not None
    assert settings_after_pub.welcome_message_id == "8888"

    # 2. Segunda publicação tenta editar a mensagem existente
    channel.fetch_message = AsyncMock(return_value=sent_msg)
    sent_msg.edit = AsyncMock()

    interaction.response = AsyncMock()
    await cog.boas_vindas.callback(cog, interaction)
    sent_msg.edit.assert_awaited_once()
