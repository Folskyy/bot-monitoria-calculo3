"""Testes unitários e de integração para o módulo database."""

from pathlib import Path
import sqlite3
import pytest

from monitoria_bot.database import Database


@pytest.fixture
async def test_db(tmp_path: Path):
    db_file = tmp_path / "test_bot.db"
    db = Database(db_file)
    await db.init_db()
    yield db
    await db.close()


async def test_init_db_idempotency_and_version(tmp_path: Path):
    db_file = tmp_path / "idempotent.db"
    db = Database(db_file)
    await db.init_db()

    # Reexecutar init_db não deve quebrar nem resetar
    await db.init_db()
    assert db._conn is not None

    async with db._conn.execute("PRAGMA user_version;") as cursor:
        row = await cursor.fetchone()
        assert row[0] == 1

    await db.close()


async def test_persistence_across_reconnect(tmp_path: Path):
    db_file = tmp_path / "reconnect.db"
    db1 = Database(db_file)
    await db1.init_db()
    await db1.upsert_guild_settings(
        guild_id="guild_1",
        welcome_channel_id="101",
        doubts_channel_id="102",
        queue_channel_id="103",
        student_role_id="201",
        monitor_role_id="202",
    )
    await db1.close()

    # Reabre em nova instância
    db2 = Database(db_file)
    await db2.init_db()
    settings = await db2.get_guild_settings("guild_1")
    assert settings is not None
    assert settings.welcome_channel_id == "101"
    assert settings.doubts_channel_id == "102"
    await db2.close()


async def test_multi_guild_isolation(test_db: Database):
    # Configura duas guildas
    await test_db.upsert_guild_settings("guild_A", "1", "2", "3", "4", "5")
    await test_db.upsert_guild_settings("guild_B", "10", "20", "30", "40", "50")

    # Mesmo RA pode existir em guildas diferentes
    student_a = await test_db.create_pending_student("guild_A", "user_1", "Aluno Um", "00123")
    student_b = await test_db.create_pending_student("guild_B", "user_2", "Aluno Dois", "00123")

    assert student_a.ra == "00123"
    assert student_b.ra == "00123"

    # Isolamento de consultas
    assert await test_db.get_student("guild_A", "user_2") is None
    assert await test_db.get_student("guild_B", "user_1") is None


async def test_student_registration_and_leading_zeros(test_db: Database):
    await test_db.upsert_guild_settings("g1", "1", "2", "3", "4", "5")

    # RA preserva zeros à esquerda
    student = await test_db.create_pending_student("g1", "u1", " Carlos Silva ", " 000789 ", " Turma A ")
    assert student.status == "pending_role"
    assert student.ra == "000789"
    assert student.full_name == "Carlos Silva"
    assert student.class_name == "Turma A"

    # Ativação do cargo
    await test_db.activate_student("g1", "u1")
    updated = await test_db.get_student("g1", "u1")
    assert updated is not None
    assert updated.status == "active"

    # Duplicidade de RA no mesmo servidor deve falhar
    with pytest.raises(sqlite3.IntegrityError):
        await test_db.create_pending_student("g1", "u2", "Outro Aluno", "000789")


async def test_doubt_lifecycle(test_db: Database):
    await test_db.upsert_guild_settings("g1", "1", "2", "3", "4", "5")

    # Inicia criação
    doubt = await test_db.create_doubt_started(
        guild_id="g1",
        author_user_id="u1",
        interaction_id="inter_123",
        subject="Derivadas Parciais",
        title="Dúvida no plano tangente",
        description="Como achar o vetor normal?",
        channel_id="2",
    )
    assert doubt.status == "creating"

    # Idempotência com mesma interacao
    retry_doubt = await test_db.create_doubt_started(
        guild_id="g1",
        author_user_id="u1",
        interaction_id="inter_123",
        subject="Outro",
        title="Outro",
        description="Outro",
        channel_id="2",
    )
    assert retry_doubt.id == doubt.id

    # Conclui criação
    completed = await test_db.complete_doubt_creation("g1", doubt.id, "msg_999", "th_888")
    assert completed.status == "open"
    assert completed.message_id == "msg_999"
    assert completed.thread_id == "th_888"

    # Resolver dúvida
    resolved = await test_db.resolve_doubt("g1", doubt.id, "monitor_1")
    assert resolved is not None
    assert resolved.status == "resolved"
    assert resolved.resolved_by_user_id == "monitor_1"
    assert resolved.resolved_at is not None

    # Repetir resolução é seguro (idempotente)
    re_resolved = await test_db.resolve_doubt("g1", doubt.id, "monitor_1")
    assert re_resolved is not None
    assert re_resolved.status == "resolved"


async def test_doubt_fail_creation(test_db: Database):
    await test_db.upsert_guild_settings("g1", "1", "2", "3", "4", "5")
    doubt = await test_db.create_doubt_started("g1", "u1", "inter_fail", "Assunto", "Titulo", "Desc", "2")
    failed = await test_db.fail_doubt_creation("g1", doubt.id)
    assert failed.status == "error"


async def test_queue_operations_and_fifo(test_db: Database):
    await test_db.upsert_guild_settings("g1", "1", "2", "3", "4", "5")

    # Alunos entram na fila
    q1 = await test_db.enqueue("g1", "student_1", "Multiplicadores de Lagrange")
    q2 = await test_db.enqueue("g1", "student_2", "Integrais Duplas")

    # Aluno não pode entrar duas vezes
    with pytest.raises(ValueError):
        await test_db.enqueue("g1", "student_1", "Outro assunto")

    # Listagem FIFO
    waiting = await test_db.list_queue("g1")
    assert len(waiting) == 2
    assert waiting[0].id == q1.id
    assert waiting[1].id == q2.id

    # Chamar próximo aluno
    called, err = await test_db.call_next("g1", "monitor_m")
    assert err is None
    assert called is not None
    assert called.id == q1.id
    assert called.status == "serving"
    assert called.called_by_user_id == "monitor_m"

    # Tentar chamar próximo enquanto já há alguém em atendimento deve ser bloqueado
    called_again, err = await test_db.call_next("g1", "monitor_m")
    assert called_again is None
    assert err == "already_serving"

    # Encerrar atendimento atual
    finished = await test_db.finish_serving("g1")
    assert finished is not None
    assert finished.status == "completed"

    # Chamar o segundo da fila
    called_2, err = await test_db.call_next("g1", "monitor_m")
    assert err is None
    assert called_2 is not None
    assert called_2.id == q2.id

    # Encerrar segundo
    await test_db.finish_serving("g1")

    # Fila vazia
    called_empty, err = await test_db.call_next("g1", "monitor_m")
    assert called_empty is None
    assert err == "queue_empty"


async def test_queue_leave_and_clear(test_db: Database):
    await test_db.upsert_guild_settings("g1", "1", "2", "3", "4", "5")
    await test_db.enqueue("g1", "u1", "Dúvida A")
    await test_db.enqueue("g1", "u2", "Dúvida B")

    # u1 desiste e sai da fila
    assert await test_db.leave_queue("g1", "u1") is True
    assert await test_db.leave_queue("g1", "u1") is False  # já saiu

    waiting = await test_db.list_queue("g1")
    assert len(waiting) == 1
    assert waiting[0].user_id == "u2"

    # Limpar fila administrativamente
    cancelled_count = await test_db.clear_queue("g1")
    assert cancelled_count == 1
    assert len(await test_db.list_queue("g1")) == 0


async def test_materials_and_tag_search(test_db: Database):
    await test_db.upsert_guild_settings("g1", "1", "2", "3", "4", "5")

    # Adicionar material
    mat1 = await test_db.add_material(
        guild_id="g1",
        title="Notas de Aula - Integrais Múltiplas",
        url="https://exemplo.com/materiais/integrais",
        tags=["Cálculo 3", "integrais", "teoria"],
        created_by_user_id="monitor_1",
        description="Resumo do capítulo 14",
    )
    assert mat1.tags == ["cálculo 3", "integrais", "teoria"]

    mat2 = await test_db.add_material(
        guild_id="g1",
        title="Lista de Exercícios 1",
        url="https://exemplo.com/listas/l1",
        tags=["exercicios", "cálculo 3"],
        created_by_user_id="monitor_1",
    )

    # Busca por tag
    tag_results = await test_db.search_materials("g1", tag="integrais")
    assert len(tag_results) == 1
    assert tag_results[0].id == mat1.id

    # Busca por termo
    term_results = await test_db.search_materials("g1", term="exercícios")
    assert len(term_results) == 1
    assert term_results[0].id == mat2.id

    # Busca combinada
    combined = await test_db.search_materials("g1", term="Resumo", tag="teoria")
    assert len(combined) == 1
    assert combined[0].id == mat1.id

    # Remoção e efeito cascata nas tags
    assert await test_db.delete_material("g1", mat1.id) is True
    assert await test_db.get_material("g1", mat1.id) is None
    assert len(await test_db.search_materials("g1", tag="teoria")) == 0


async def test_get_classes_defaults_and_custom(test_db: Database):
    await test_db.upsert_guild_settings("g1", "1", "2", "3", "4", "5")

    # Primeira busca gera as turmas padrão
    classes = await test_db.get_classes("g1")
    class_names = [c.name for c in classes]
    assert "Engenharia de Computação" in class_names
    assert "Engenharia Civil" in class_names
    assert "Engenharia Eletrônica" in class_names
    assert len(classes) == 3

    # Adicionar turma personalizada
    added = await test_db.add_class("g1", "Engenharia Mecânica")
    assert added.name == "Engenharia Mecânica"

    # Segunda busca deve conter a nova turma
    updated_classes = await test_db.get_classes("g1")
    assert len(updated_classes) == 4
    assert any(c.name == "Engenharia Mecânica" for c in updated_classes)


async def test_add_class_deduplication(test_db: Database):
    await test_db.upsert_guild_settings("g1", "1", "2", "3", "4", "5")

    c1 = await test_db.add_class("g1", "Engenharia Química")
    c2 = await test_db.add_class("g1", "engenharia química")

    assert c1.id == c2.id
    assert c1.name == "Engenharia Química"

