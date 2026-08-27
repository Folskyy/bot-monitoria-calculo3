"""Testes para o script utilitário de backup do SQLite."""

from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest

from monitoria_bot.database import Database
from scripts.backup_db import perform_backup, prune_old_backups


@pytest.fixture
async def sample_db_with_wal(tmp_path: Path):
    db_file = tmp_path / "live_bot.db"
    db = Database(db_file)
    await db.init_db()
    await db.upsert_guild_settings("100", "1", "2", "3", "4", "5")
    await db.create_pending_student("100", "u1", "Aluno Teste", "009911")
    await db.close()
    return db_file


def test_perform_backup_success_and_integrity(sample_db_with_wal: Path, tmp_path: Path):
    backup_dir = tmp_path / "backups"
    backup_file = perform_backup(sample_db_with_wal, backup_dir)

    assert backup_file.is_file()
    assert backup_file.name.startswith("bot_backup_")

    # Verifica integridade e conteúdo do backup
    conn = sqlite3.connect(str(backup_file))
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    assert cursor.fetchone()[0] == "ok"

    cursor.execute("SELECT full_name, ra FROM students WHERE user_id = 'u1';")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "Aluno Teste"
    assert row[1] == "009911"
    conn.close()


def test_prune_old_backups(tmp_path: Path):
    backup_dir = tmp_path / "backups_prune"
    backup_dir.mkdir(parents=True)

    # Cria 5 arquivos de backup fictícios
    files = []
    for i in range(5):
        f = backup_dir / f"bot_backup_2026080{i}_000000Z.db"
        f.write_text("data")
        files.append(f)

    # Prune com min_keep=2 e retention_days=0 (nenhum apagado)
    prune_old_backups(backup_dir, retention_days=0, min_keep=2)
    assert len(list(backup_dir.glob("bot_backup_*.db"))) == 5


def test_backup_cli_execution(sample_db_with_wal: Path, tmp_path: Path):
    backup_dir = tmp_path / "cli_backups"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/backup_db.py",
            "--db-path", str(sample_db_with_wal),
            "--backup-dir", str(backup_dir),
            "--retention-days", "7",
            "--min-keep", "2",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Backup concluído com sucesso" in result.stdout
    assert len(list(backup_dir.glob("bot_backup_*.db"))) == 1
