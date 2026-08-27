#!/usr/bin/env python3
"""Script utilitário para geração de backups consistentes do SQLite usando a SQLite Backup API."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys


def perform_backup(source_db: Path, backup_dir: Path) -> Path:
    """Executa o backup consistente do banco de dados utilizando a SQLite Backup API."""
    if not source_db.is_file():
        sys.stderr.write(f"Erro: O arquivo de banco de dados '{source_db}' não existe.\n")
        sys.exit(1)

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    backup_file = backup_dir / f"bot_backup_{timestamp}.db"

    sys.stdout.write(f"Iniciando backup de '{source_db}' para '{backup_file}'...\n")

    try:
        source_conn = sqlite3.connect(str(source_db))
        dest_conn = sqlite3.connect(str(backup_file))

        with dest_conn:
            source_conn.backup(dest_conn)

        dest_conn.close()
        source_conn.close()

        # Verificação de integridade no arquivo recém-gerado
        verify_conn = sqlite3.connect(str(backup_file))
        cursor = verify_conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        verify_conn.close()

        if not result or result[0] != "ok":
            sys.stderr.write(f"Erro: Falha na verificação de integridade do backup: {result}\n")
            sys.exit(2)

        sys.stdout.write(f"✅ Backup concluído com sucesso e verificado (integridade: ok): {backup_file}\n")
        return backup_file

    except Exception as e:
        sys.stderr.write(f"Erro durante o processo de backup: {e}\n")
        if backup_file.exists():
            backup_file.unlink(missing_ok=True)
        sys.exit(1)


def prune_old_backups(backup_dir: Path, retention_days: int = 7, min_keep: int = 3) -> None:
    """Remove backups mais antigos que o período de retenção, preservando no mínimo min_keep cópias."""
    if retention_days <= 0:
        return

    backup_files = sorted(
        backup_dir.glob("bot_backup_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if len(backup_files) <= min_keep:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    candidates = backup_files[min_keep:]

    for p in candidates:
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            sys.stdout.write(f"Removendo backup expirado pela política de retenção: {p.name}\n")
            p.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup consistente do SQLite para Bot de Monitoria de Cálculo 3.")
    parser.add_argument(
        "--db-path",
        default="./data/bot.db",
        help="Caminho do arquivo do banco SQLite de origem (Padrão: ./data/bot.db)",
    )
    parser.add_argument(
        "--backup-dir",
        default="./backups",
        help="Diretório onde os arquivos de backup serão armazenados (Padrão: ./backups)",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=7,
        help="Dias de retenção antes de purgar backups antigos (Padrão: 7, 0 desabilita)",
    )
    parser.add_argument(
        "--min-keep",
        type=int,
        default=3,
        help="Quantidade mínima de backups a preservar independentemente da idade (Padrão: 3)",
    )

    args = parser.parse_args()
    source_db = Path(args.db_path).resolve()
    backup_dir = Path(args.backup_dir).resolve()

    perform_backup(source_db, backup_dir)
    prune_old_backups(backup_dir, retention_days=args.retention_days, min_keep=args.min_keep)


if __name__ == "__main__":
    main()
