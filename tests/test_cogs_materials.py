"""Testes para o MaterialsCog (/material adicionar, remover, buscar)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands
import pytest

from monitoria_bot.cogs.materials import MaterialsCog, is_valid_http_url
from monitoria_bot.config import Config, load_config
from monitoria_bot.database import Database


@pytest.fixture
async def test_db(tmp_path: Path):
    db = Database(tmp_path / "mat_test.db")
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


def test_url_validation():
    assert is_valid_http_url("https://usp.br/calculo3") is True
    assert is_valid_http_url("http://example.com/lista.pdf") is True
    assert is_valid_http_url("ftp://ftp.example.com") is False
    assert is_valid_http_url("javascript:alert(1)") is False
    assert is_valid_http_url("apenas_texto") is False
    assert is_valid_http_url("") is False


async def test_material_adicionar_and_remover(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = MaterialsCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "3", "100", "200")

    interaction_monitor = MagicMock(spec=discord.Interaction)
    interaction_monitor.guild = MagicMock(spec=discord.Guild)
    interaction_monitor.guild.id = 10
    monitor_member = MagicMock(spec=discord.Member)
    monitor_member.id = 999
    monitor_member.guild_permissions.administrator = True
    interaction_monitor.user = monitor_member
    interaction_monitor.response = AsyncMock()

    # 1. URL Inválida
    await cog.adicionar.callback(
        cog,
        interaction_monitor,
        titulo="Aula 1",
        url="ftp://invalido.com",
        tags="calculo",
    )
    msg_err = interaction_monitor.response.send_message.call_args[0][0]
    assert "URL inválida" in msg_err

    # 2. Sucesso
    interaction_monitor.response = AsyncMock()
    await cog.adicionar.callback(
        cog,
        interaction_monitor,
        titulo="Apostila de Integrais Triplas",
        url="https://drive.google.com/apostila",
        tags="integrais, cálculo 3, p2",
        descricao="Capítulo 15",
    )
    msg_ok = interaction_monitor.response.send_message.call_args[0][0]
    assert "cadastrado com sucesso" in msg_ok

    saved = await test_db.search_materials("10", tag="p2")
    assert len(saved) == 1
    assert saved[0].title == "Apostila de Integrais Triplas"

    # 3. Remoção
    interaction_monitor.response = AsyncMock()
    await cog.remover.callback(cog, interaction_monitor, id=saved[0].id)
    msg_del = interaction_monitor.response.send_message.call_args[0][0]
    assert "excluído com sucesso" in msg_del
    assert len(await test_db.search_materials("10", tag="p2")) == 0


async def test_material_buscar_registered_student(test_db: Database, mock_config: Config, mock_bot: commands.Bot):
    cog = MaterialsCog(mock_bot, test_db, mock_config)
    await test_db.upsert_guild_settings("10", "1", "2", "3", "100", "200")
    await test_db.create_pending_student("10", "44", "Aluno Registrado", "123")
    await test_db.activate_student("10", "44")

    # Adiciona material no banco
    await test_db.add_material("10", "Lista Teorema de Gauss", "https://site.com/gauss", ["gauss", "vetorial"], "999")

    interaction_student = MagicMock(spec=discord.Interaction)
    interaction_student.guild = MagicMock(spec=discord.Guild)
    interaction_student.guild.id = 10
    student_member = MagicMock(spec=discord.Member)
    student_member.id = 44
    role = MagicMock(spec=discord.Role)
    role.id = 100
    student_member.roles = [role]
    interaction_student.user = student_member
    interaction_student.response = AsyncMock()

    await cog.buscar.callback(cog, interaction_student, termo="Gauss")
    interaction_student.response.send_message.assert_awaited_once()
    embed = interaction_student.response.send_message.call_args[1].get("embed")
    assert embed is not None
    assert "Lista Teorema de Gauss" in embed.fields[0].name
