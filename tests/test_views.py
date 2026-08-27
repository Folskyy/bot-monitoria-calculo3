"""Testes unitários para as views persistentes e modais de cadastro."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import discord
import pytest

from monitoria_bot.config import Config, load_config
from monitoria_bot.database import Database, GuildSettings, Student
from monitoria_bot.views.modals import RegistrationModal
from monitoria_bot.views.persistent import RegistrationView, build_welcome_embed


@pytest.fixture
async def test_db(tmp_path: Path):
    db_file = tmp_path / "test_views.db"
    db = Database(db_file)
    await db.init_db()
    yield db
    await db.close()


@pytest.fixture
def mock_config(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=dummy\nRA_REGEX=^[A-Za-z0-9]{1,32}$\n", encoding="utf-8")
    return load_config(require_token=True, env_file=env_file)


@pytest.fixture
def sample_settings():
    return GuildSettings(
        guild_id="111",
        welcome_channel_id="222",
        doubts_channel_id="333",
        queue_channel_id="444",
        student_role_id="555",
        monitor_role_id="666",
        welcome_message_id="777",
        office_hours_text="Seg e Qua 14h",
        timezone="America/Sao_Paulo",
        created_at="2026-08-27T00:00:00Z",
        updated_at="2026-08-27T00:00:00Z",
    )


def test_build_welcome_embed(sample_settings):
    embed = build_welcome_embed(sample_settings)
    assert "Monitoria de Cálculo 3" in embed.title
    field_names = [f.name for f in embed.fields]
    assert any("Como se Cadastrar" in name for name in field_names)
    assert any("Privacidade" in name for name in field_names)
    assert any("Regras" in name for name in field_names)


def test_registration_view_attributes(test_db, mock_config):
    view = RegistrationView(test_db, mock_config)
    assert view.timeout is None
    button = view.children[0]
    assert isinstance(button, discord.ui.Button)
    assert button.custom_id == "monitoria:btn_register"


async def test_registration_modal_success(test_db: Database, mock_config: Config, sample_settings: GuildSettings):
    await test_db.upsert_guild_settings(
        guild_id=sample_settings.guild_id,
        welcome_channel_id=sample_settings.welcome_channel_id,
        doubts_channel_id=sample_settings.doubts_channel_id,
        queue_channel_id=sample_settings.queue_channel_id,
        student_role_id=sample_settings.student_role_id,
        monitor_role_id=sample_settings.monitor_role_id,
    )

    modal = RegistrationModal(test_db, mock_config, sample_settings)
    modal.full_name_input._value = "Mariana Costa"
    modal.ra_input._value = "0045678"
    modal.class_name_input._value = "Turma C"

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 111
    member = MagicMock(spec=discord.Member)
    member.id = 888
    interaction.guild = guild
    interaction.user = member
    interaction.response = AsyncMock()

    role = MagicMock(spec=discord.Role)
    role.name = "Aluno"
    guild.get_role.return_value = role
    member.add_roles = AsyncMock()

    await modal.on_submit(interaction)

    member.add_roles.assert_awaited_once_with(role, reason="Cadastro de monitoria concluído")
    interaction.response.send_message.assert_awaited_once()
    msg_args = interaction.response.send_message.call_args[0][0]
    assert "concluído com sucesso" in msg_args

    student = await test_db.get_student("111", "888")
    assert student is not None
    assert student.status == "active"
    assert student.ra == "0045678"


async def test_registration_modal_invalid_ra(test_db: Database, mock_config: Config, sample_settings: GuildSettings):
    modal = RegistrationModal(test_db, mock_config, sample_settings)
    modal.full_name_input._value = "Mariana Costa"
    modal.ra_input._value = "RA com espacos e caracteres invalidos @#!"
    modal.class_name_input._value = ""

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 111
    member = MagicMock(spec=discord.Member)
    member.id = 888
    interaction.guild = guild
    interaction.user = member
    interaction.response = AsyncMock()

    await modal.on_submit(interaction)
    interaction.response.send_message.assert_awaited_once()
    msg_args = interaction.response.send_message.call_args[0][0]
    assert "Formato de RA inválido" in msg_args


async def test_registration_modal_duplicate_ra_by_other_user(
    test_db: Database, mock_config: Config, sample_settings: GuildSettings
):
    await test_db.upsert_guild_settings(
        guild_id="111", welcome_channel_id="2", doubts_channel_id="3",
        queue_channel_id="4", student_role_id="5", monitor_role_id="6"
    )
    # user 100 already registered RA 12345
    await test_db.create_pending_student("111", "100", "Aluno Existente", "12345")

    modal = RegistrationModal(test_db, mock_config, sample_settings)
    modal.full_name_input._value = "Outro Aluno"
    modal.ra_input._value = "12345"
    modal.class_name_input._value = ""

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 111
    member = MagicMock(spec=discord.Member)
    member.id = 200  # outro usuário
    interaction.guild = guild
    interaction.user = member
    interaction.response = AsyncMock()

    await modal.on_submit(interaction)
    interaction.response.send_message.assert_awaited_once()
    msg_args = interaction.response.send_message.call_args[0][0]
    assert "Este RA já foi cadastrado por outro usuário" in msg_args


async def test_registration_modal_discord_role_fail_preserves_pending(
    test_db: Database, mock_config: Config, sample_settings: GuildSettings
):
    await test_db.upsert_guild_settings(
        guild_id="111", welcome_channel_id="2", doubts_channel_id="3",
        queue_channel_id="4", student_role_id="555", monitor_role_id="6"
    )

    modal = RegistrationModal(test_db, mock_config, sample_settings)
    modal.full_name_input._value = "Aluno Com Falha Discord"
    modal.ra_input._value = "998877"
    modal.class_name_input._value = ""

    interaction = MagicMock(spec=discord.Interaction)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 111
    member = MagicMock(spec=discord.Member)
    member.id = 777
    interaction.guild = guild
    interaction.user = member
    interaction.response = AsyncMock()

    role = MagicMock(spec=discord.Role)
    guild.get_role.return_value = role
    # Simula erro de permissão do Discord ao atribuir cargo
    member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Sem permissão"))

    await modal.on_submit(interaction)

    student = await test_db.get_student("111", "777")
    assert student is not None
    assert student.status == "pending_role"
    msg_args = interaction.response.send_message.call_args[0][0]
    assert "estado pendente" in msg_args


async def test_registration_view_button_unregistered(test_db: Database, mock_config: Config):
    await test_db.upsert_guild_settings("111", "1", "2", "3", "4", "5")
    view = RegistrationView(test_db, mock_config)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 111
    member = MagicMock(spec=discord.Member)
    member.id = 999
    interaction.user = member
    interaction.response = AsyncMock()

    button = view.children[0]
    await button.callback(interaction)

    interaction.response.send_modal.assert_awaited_once()
