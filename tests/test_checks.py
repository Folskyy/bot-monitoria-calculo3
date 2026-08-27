"""Testes unitários para o módulo checks de autorizações e cargos."""

from unittest.mock import MagicMock
import discord
import pytest

from monitoria_bot.checks import (
    can_access_student_feature,
    is_admin,
    is_monitor_or_admin,
    validate_bot_channel_permissions,
    validate_student_role,
)
from monitoria_bot.database import GuildSettings, Student


def create_mock_settings():
    return GuildSettings(
        guild_id="guild_1",
        welcome_channel_id="10",
        doubts_channel_id="20",
        queue_channel_id="30",
        student_role_id="100",
        monitor_role_id="200",
        welcome_message_id="500",
        office_hours_text="Seg e Qua 14h",
        timezone="America/Sao_Paulo",
        created_at="2026-08-27T00:00:00Z",
        updated_at="2026-08-27T00:00:00Z",
    )


def test_validate_student_role_rejects_everyone():
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    role = MagicMock(spec=discord.Role)
    role.id = 999

    valid, err = validate_student_role(guild, role)
    assert valid is False
    assert "@everyone" in err


def test_validate_student_role_rejects_managed():
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    role = MagicMock(spec=discord.Role)
    role.id = 100
    role.managed = True

    valid, err = validate_student_role(guild, role)
    assert valid is False
    assert "gerenciado por integração" in err


def test_validate_student_role_rejects_dangerous_perms():
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    role = MagicMock(spec=discord.Role)
    role.id = 100
    role.managed = False

    perms = discord.Permissions.none()
    perms.ban_members = True
    role.permissions = perms

    valid, err = validate_student_role(guild, role)
    assert valid is False
    assert "Banir Membros" in err


def test_validate_student_role_rejects_bot_hierarchy_too_low():
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True

    bot_role = MagicMock(spec=discord.Role)
    bot_role.name = "BotRole"
    role = MagicMock(spec=discord.Role)
    role.name = "Aluno"
    role.id = 100
    role.managed = False
    role.permissions = discord.Permissions.none()

    # bot_role <= role
    bot_role.__le__ = lambda self, other: True
    bot_member.top_role = bot_role
    guild.me = bot_member

    valid, err = validate_student_role(guild, role)
    assert valid is False
    assert "acima" in err


def test_validate_student_role_success():
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True

    bot_role = MagicMock(spec=discord.Role)
    bot_role.name = "BotRole"
    role = MagicMock(spec=discord.Role)
    role.name = "Aluno"
    role.id = 100
    role.managed = False
    role.permissions = discord.Permissions.none()

    bot_role.__le__ = lambda self, other: False
    bot_member.top_role = bot_role
    guild.me = bot_member

    valid, err = validate_student_role(guild, role)
    assert valid is True
    assert err == ""


def test_validate_bot_channel_permissions():
    channel = MagicMock(spec=discord.TextChannel)
    guild = MagicMock(spec=discord.Guild)
    channel.guild = guild
    channel.mention = "#duvidas"

    bot_member = MagicMock(spec=discord.Member)
    guild.me = bot_member

    perms = discord.Permissions.none()
    channel.permissions_for.return_value = perms

    # Sem permissão de ver canal
    valid, err = validate_bot_channel_permissions(channel)
    assert valid is False
    assert "ver o canal" in err

    # Permissão de ver e enviar
    perms.view_channel = True
    perms.send_messages = True
    valid, err = validate_bot_channel_permissions(channel, is_doubts=False)
    assert valid is True

    # Canal de dúvidas precisa de threads
    valid_doubt, err_doubt = validate_bot_channel_permissions(channel, is_doubts=True)
    assert valid_doubt is False
    assert "threads públicas" in err_doubt


def test_authorization_checks():
    settings = create_mock_settings()

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    member = MagicMock(spec=discord.Member)
    interaction.user = member

    # Não admin, sem cargo monitor
    member.guild_permissions.administrator = False
    member.roles = []
    assert is_admin(interaction) is False
    assert is_monitor_or_admin(interaction, settings) is False

    # Monitor
    monitor_role = MagicMock(spec=discord.Role)
    monitor_role.id = 200
    member.roles = [monitor_role]
    assert is_monitor_or_admin(interaction, settings) is True

    # Monitor pode acessar feature de aluno
    can_access, _ = can_access_student_feature(interaction, student=None, settings=settings)
    assert can_access is True

    # Aluno não cadastrado
    member.roles = []
    can_access_unreg, err = can_access_student_feature(interaction, student=None, settings=settings)
    assert can_access_unreg is False
    assert "realizar seu cadastro" in err

    # Aluno com cadastro ativo mas sem cargo no Discord
    student = Student("guild_1", "user_1", "Nome", "12345", None, "active", "now", "now")
    can_access_norole, err_norole = can_access_student_feature(interaction, student, settings)
    assert can_access_norole is False
    assert "não possui o cargo de Aluno" in err_norole

    # Aluno com cargo atribuído
    student_role = MagicMock(spec=discord.Role)
    student_role.id = 100
    member.roles = [student_role]
    can_access_ok, err_ok = can_access_student_feature(interaction, student, settings)
    assert can_access_ok is True
    assert err_ok == ""
