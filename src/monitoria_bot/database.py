"""Módulo de persistência e gerenciamento do banco de dados SQLite com aiosqlite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.resources
from pathlib import Path
import sqlite3
from typing import Any

import aiosqlite


def utc_iso_now() -> str:
    """Retorna timestamp UTC atual no formato ISO 8601 uniforme."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class GuildSettings:
    guild_id: str
    welcome_channel_id: str
    doubts_channel_id: str
    queue_channel_id: str
    student_role_id: str
    monitor_role_id: str
    welcome_message_id: str | None
    office_hours_text: str
    timezone: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Student:
    guild_id: str
    user_id: str
    full_name: str
    ra: str
    class_name: str | None
    status: str  # 'pending_role' | 'active'
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Doubt:
    id: int
    guild_id: str
    author_user_id: str
    interaction_id: str
    subject: str
    title: str
    description: str
    channel_id: str
    message_id: str | None
    thread_id: str | None
    status: str  # 'creating' | 'open' | 'resolved' | 'error'
    resolved_by_user_id: str | None
    created_at: str
    updated_at: str
    resolved_at: str | None


@dataclass(frozen=True)
class QueueEntry:
    id: int
    guild_id: str
    user_id: str
    subject: str
    status: str  # 'waiting' | 'serving' | 'completed' | 'cancelled'
    called_by_user_id: str | None
    created_at: str
    called_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class Material:
    id: int
    guild_id: str
    title: str
    description: str
    url: str
    created_by_user_id: str
    created_at: str
    tags: list[str]


class Database:
    """Gerenciador assíncrono do banco SQLite local com lock de concorrência."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Abre a conexão com o banco e inicializa os pragmas obrigatórios."""
        if self._conn is not None:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row

        # Pragmas obrigatórios
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.execute("PRAGMA busy_timeout = 5000;")
        await self._conn.commit()

    async def close(self) -> None:
        """Fecha a conexão com o banco de dados com segurança."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def init_db(self) -> None:
        """Inicializa o banco de dados de forma idempotente verificando PRAGMA user_version."""
        await self.connect()
        assert self._conn is not None

        async with self._lock:
            async with self._conn.execute("PRAGMA user_version;") as cursor:
                row = await cursor.fetchone()
                current_version = row[0] if row else 0

            if current_version == 0:
                schema_text = importlib.resources.files("monitoria_bot").joinpath("schema.sql").read_text(encoding="utf-8")
                await self._conn.executescript(schema_text)
                await self._conn.execute("PRAGMA user_version = 1;")
                await self._conn.commit()

    # -------------------------------------------------------------------------
    # Guild Settings
    # -------------------------------------------------------------------------

    async def get_guild_settings(self, guild_id: str) -> GuildSettings | None:
        await self.connect()
        assert self._conn is not None
        query = (
            "SELECT guild_id, welcome_channel_id, doubts_channel_id, queue_channel_id, "
            "student_role_id, monitor_role_id, welcome_message_id, office_hours_text, "
            "timezone, created_at, updated_at "
            "FROM guild_settings WHERE guild_id = ?;"
        )
        async with self._conn.execute(query, (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return GuildSettings(**dict(row))

    async def upsert_guild_settings(
        self,
        guild_id: str,
        welcome_channel_id: str,
        doubts_channel_id: str,
        queue_channel_id: str,
        student_role_id: str,
        monitor_role_id: str,
        office_hours_text: str | None = None,
        timezone_str: str = "America/Sao_Paulo",
    ) -> GuildSettings:
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()

        async with self._lock:
            existing = await self.get_guild_settings(guild_id)
            if existing:
                hours = office_hours_text if office_hours_text is not None else existing.office_hours_text
                query = (
                    "UPDATE guild_settings SET "
                    "welcome_channel_id = ?, doubts_channel_id = ?, queue_channel_id = ?, "
                    "student_role_id = ?, monitor_role_id = ?, office_hours_text = ?, "
                    "timezone = ?, updated_at = ? "
                    "WHERE guild_id = ?;"
                )
                await self._conn.execute(
                    query,
                    (
                        welcome_channel_id,
                        doubts_channel_id,
                        queue_channel_id,
                        student_role_id,
                        monitor_role_id,
                        hours,
                        timezone_str,
                        now,
                        guild_id,
                    ),
                )
            else:
                hours = office_hours_text if office_hours_text is not None else "Horários ainda não informados."
                query = (
                    "INSERT INTO guild_settings ("
                    "guild_id, welcome_channel_id, doubts_channel_id, queue_channel_id, "
                    "student_role_id, monitor_role_id, office_hours_text, timezone, created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"
                )
                await self._conn.execute(
                    query,
                    (
                        guild_id,
                        welcome_channel_id,
                        doubts_channel_id,
                        queue_channel_id,
                        student_role_id,
                        monitor_role_id,
                        hours,
                        timezone_str,
                        now,
                        now,
                    ),
                )
            await self._conn.commit()

        updated = await self.get_guild_settings(guild_id)
        assert updated is not None
        return updated

    async def update_welcome_message_id(self, guild_id: str, message_id: str | None) -> None:
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()
        async with self._lock:
            await self._conn.execute(
                "UPDATE guild_settings SET welcome_message_id = ?, updated_at = ? WHERE guild_id = ?;",
                (message_id, now, guild_id),
            )
            await self._conn.commit()

    async def update_office_hours_text(self, guild_id: str, text: str) -> None:
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()
        async with self._lock:
            await self._conn.execute(
                "UPDATE guild_settings SET office_hours_text = ?, updated_at = ? WHERE guild_id = ?;",
                (text, now, guild_id),
            )
            await self._conn.commit()

    # -------------------------------------------------------------------------
    # Students
    # -------------------------------------------------------------------------

    async def get_student(self, guild_id: str, user_id: str) -> Student | None:
        await self.connect()
        assert self._conn is not None
        query = (
            "SELECT guild_id, user_id, full_name, ra, class_name, status, created_at, updated_at "
            "FROM students WHERE guild_id = ? AND user_id = ?;"
        )
        async with self._conn.execute(query, (guild_id, user_id)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Student(**dict(row))

    async def get_student_by_ra(self, guild_id: str, ra: str) -> Student | None:
        await self.connect()
        assert self._conn is not None
        query = (
            "SELECT guild_id, user_id, full_name, ra, class_name, status, created_at, updated_at "
            "FROM students WHERE guild_id = ? AND ra = ?;"
        )
        async with self._conn.execute(query, (guild_id, ra)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Student(**dict(row))

    async def create_pending_student(
        self,
        guild_id: str,
        user_id: str,
        full_name: str,
        ra: str,
        class_name: str | None = None,
    ) -> Student:
        """Cria ou atualiza cadastro no estado pending_role. Lança sqlite3.IntegrityError se RA pertencer a outro usuário."""
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()

        async with self._lock:
            existing = await self.get_student(guild_id, user_id)
            if existing:
                # Se já existe, atualiza nome/ra/turma mantendo ou resetando para pending_role
                query = (
                    "UPDATE students SET full_name = ?, ra = ?, class_name = ?, status = 'pending_role', updated_at = ? "
                    "WHERE guild_id = ? AND user_id = ?;"
                )
                await self._conn.execute(query, (full_name.strip(), ra.strip(), class_name.strip() if class_name else None, now, guild_id, user_id))
            else:
                query = (
                    "INSERT INTO students (guild_id, user_id, full_name, ra, class_name, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'pending_role', ?, ?);"
                )
                await self._conn.execute(
                    query,
                    (guild_id, user_id, full_name.strip(), ra.strip(), class_name.strip() if class_name else None, now, now),
                )
            await self._conn.commit()

        student = await self.get_student(guild_id, user_id)
        assert student is not None
        return student

    async def activate_student(self, guild_id: str, user_id: str) -> None:
        """Promove o cadastro para active após atribuição bem-sucedida de cargo no Discord."""
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()
        async with self._lock:
            await self._conn.execute(
                "UPDATE students SET status = 'active', updated_at = ? WHERE guild_id = ? AND user_id = ?;",
                (now, guild_id, user_id),
            )
            await self._conn.commit()

    async def update_student_profile(
        self,
        guild_id: str,
        user_id: str,
        full_name: str,
        ra: str,
        class_name: str | None = None,
    ) -> Student:
        """Edição administrativa/monitor de cadastro."""
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()
        async with self._lock:
            query = (
                "UPDATE students SET full_name = ?, ra = ?, class_name = ?, updated_at = ? "
                "WHERE guild_id = ? AND user_id = ?;"
            )
            await self._conn.execute(
                query,
                (full_name.strip(), ra.strip(), class_name.strip() if class_name else None, now, guild_id, user_id),
            )
            await self._conn.commit()

        student = await self.get_student(guild_id, user_id)
        assert student is not None
        return student

    async def delete_student(self, guild_id: str, user_id: str) -> bool:
        """Remove o cadastro do aluno (exercício de privacidade)."""
        await self.connect()
        assert self._conn is not None
        async with self._lock:
            async with self._conn.execute(
                "DELETE FROM students WHERE guild_id = ? AND user_id = ?;",
                (guild_id, user_id),
            ) as cursor:
                deleted = cursor.rowcount > 0
            await self._conn.commit()
            return deleted

    # -------------------------------------------------------------------------
    # Doubts
    # -------------------------------------------------------------------------

    async def get_doubt_by_interaction(self, interaction_id: str) -> Doubt | None:
        await self.connect()
        assert self._conn is not None
        query = "SELECT * FROM doubts WHERE interaction_id = ?;"
        async with self._conn.execute(query, (interaction_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Doubt(**dict(row))

    async def create_doubt_started(
        self,
        guild_id: str,
        author_user_id: str,
        interaction_id: str,
        subject: str,
        title: str,
        description: str,
        channel_id: str,
    ) -> Doubt:
        """Registra o início da criação de uma dúvida em status 'creating'."""
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()

        async with self._lock:
            existing = await self.get_doubt_by_interaction(interaction_id)
            if existing:
                return existing

            query = (
                "INSERT INTO doubts ("
                "guild_id, author_user_id, interaction_id, subject, title, description, channel_id, status, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, 'creating', ?, ?);"
            )
            async with self._conn.execute(
                query,
                (guild_id, author_user_id, interaction_id, subject.strip(), title.strip(), description.strip(), channel_id, now, now),
            ) as cursor:
                doubt_id = cursor.lastrowid
            await self._conn.commit()

        doubt = await self.get_doubt(guild_id, doubt_id)
        assert doubt is not None
        return doubt

    async def complete_doubt_creation(
        self,
        guild_id: str,
        doubt_id: int,
        message_id: str,
        thread_id: str,
    ) -> Doubt:
        """Atualiza a dúvida para 'open' com os identificadores do Discord."""
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()
        async with self._lock:
            query = (
                "UPDATE doubts SET message_id = ?, thread_id = ?, status = 'open', updated_at = ? "
                "WHERE id = ? AND guild_id = ?;"
            )
            await self._conn.execute(query, (message_id, thread_id, now, doubt_id, guild_id))
            await self._conn.commit()

        doubt = await self.get_doubt(guild_id, doubt_id)
        assert doubt is not None
        return doubt

    async def fail_doubt_creation(self, guild_id: str, doubt_id: int) -> Doubt:
        """Atualiza a dúvida para 'error' quando o Discord falha ao criar thread."""
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()
        async with self._lock:
            await self._conn.execute(
                "UPDATE doubts SET status = 'error', updated_at = ? WHERE id = ? AND guild_id = ?;",
                (now, doubt_id, guild_id),
            )
            await self._conn.commit()

        doubt = await self.get_doubt(guild_id, doubt_id)
        assert doubt is not None
        return doubt

    async def get_doubt(self, guild_id: str, doubt_id: int) -> Doubt | None:
        await self.connect()
        assert self._conn is not None
        query = "SELECT * FROM doubts WHERE id = ? AND guild_id = ?;"
        async with self._conn.execute(query, (doubt_id, guild_id)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Doubt(**dict(row))

    async def list_user_doubts(
        self,
        guild_id: str,
        author_user_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Doubt]:
        await self.connect()
        assert self._conn is not None
        query = (
            "SELECT * FROM doubts WHERE guild_id = ? AND author_user_id = ? "
            "ORDER BY id DESC LIMIT ? OFFSET ?;"
        )
        async with self._conn.execute(query, (guild_id, author_user_id, limit, offset)) as cursor:
            rows = await cursor.fetchall()
            return [Doubt(**dict(r)) for r in rows]

    async def resolve_doubt(
        self,
        guild_id: str,
        doubt_id: int,
        resolved_by_user_id: str,
    ) -> Doubt | None:
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()
        async with self._lock:
            doubt = await self.get_doubt(guild_id, doubt_id)
            if not doubt:
                return None

            if doubt.status != "resolved":
                query = (
                    "UPDATE doubts SET status = 'resolved', resolved_by_user_id = ?, resolved_at = ?, updated_at = ? "
                    "WHERE id = ? AND guild_id = ?;"
                )
                await self._conn.execute(query, (resolved_by_user_id, now, now, doubt_id, guild_id))
                await self._conn.commit()

        return await self.get_doubt(guild_id, doubt_id)

    # -------------------------------------------------------------------------
    # Queue
    # -------------------------------------------------------------------------

    async def get_active_queue_entry(self, guild_id: str, user_id: str) -> QueueEntry | None:
        """Retorna a entrada ativa do aluno na fila (waiting ou serving)."""
        await self.connect()
        assert self._conn is not None
        query = (
            "SELECT * FROM queue_entries WHERE guild_id = ? AND user_id = ? "
            "AND status IN ('waiting', 'serving');"
        )
        async with self._conn.execute(query, (guild_id, user_id)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return QueueEntry(**dict(row))

    async def enqueue(self, guild_id: str, user_id: str, subject: str) -> QueueEntry:
        """Adiciona aluno à fila. Lança ValueError se o aluno já possuir entrada ativa."""
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()

        async with self._lock:
            active = await self.get_active_queue_entry(guild_id, user_id)
            if active:
                raise ValueError("Você já possui uma entrada ativa na fila.")

            query = (
                "INSERT INTO queue_entries (guild_id, user_id, subject, status, created_at) "
                "VALUES (?, ?, ?, 'waiting', ?);"
            )
            async with self._conn.execute(query, (guild_id, user_id, subject.strip(), now)) as cursor:
                entry_id = cursor.lastrowid
            await self._conn.commit()

        entry = await self.get_queue_entry_by_id(guild_id, entry_id)
        assert entry is not None
        return entry

    async def get_queue_entry_by_id(self, guild_id: str, entry_id: int) -> QueueEntry | None:
        await self.connect()
        assert self._conn is not None
        query = "SELECT * FROM queue_entries WHERE id = ? AND guild_id = ?;"
        async with self._conn.execute(query, (entry_id, guild_id)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return QueueEntry(**dict(row))

    async def leave_queue(self, guild_id: str, user_id: str) -> bool:
        """Remove da fila o aluno que estiver no estado 'waiting'."""
        await self.connect()
        assert self._conn is not None
        async with self._lock:
            query = (
                "UPDATE queue_entries SET status = 'cancelled' "
                "WHERE guild_id = ? AND user_id = ? AND status = 'waiting';"
            )
            async with self._conn.execute(query, (guild_id, user_id)) as cursor:
                updated = cursor.rowcount > 0
            await self._conn.commit()
            return updated

    async def list_queue(self, guild_id: str) -> list[QueueEntry]:
        """Lista as entradas em espera em ordem FIFO (created_at ASC, id ASC)."""
        await self.connect()
        assert self._conn is not None
        query = (
            "SELECT * FROM queue_entries WHERE guild_id = ? AND status = 'waiting' "
            "ORDER BY created_at ASC, id ASC;"
        )
        async with self._conn.execute(query, (guild_id,)) as cursor:
            rows = await cursor.fetchall()
            return [QueueEntry(**dict(r)) for r in rows]

    async def get_active_serving(self, guild_id: str) -> QueueEntry | None:
        """Retorna o atendimento atualmente em andamento na guilda."""
        await self.connect()
        assert self._conn is not None
        query = "SELECT * FROM queue_entries WHERE guild_id = ? AND status = 'serving';"
        async with self._conn.execute(query, (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return QueueEntry(**dict(row))

    async def call_next(self, guild_id: str, monitor_user_id: str) -> tuple[QueueEntry | None, str | None]:
        """
        Chama o próximo da fila em transação atômica protegida por lock.
        Retorna (entry, None) ou (None, "already_serving") ou (None, "queue_empty").
        """
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()

        async with self._lock:
            # 1. Verifica se já há atendimento em andamento
            active_serving = await self.get_active_serving(guild_id)
            if active_serving:
                return None, "already_serving"

            # 2. Busca o primeiro da fila FIFO
            query_next = (
                "SELECT id FROM queue_entries WHERE guild_id = ? AND status = 'waiting' "
                "ORDER BY created_at ASC, id ASC LIMIT 1;"
            )
            async with self._conn.execute(query_next, (guild_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None, "queue_empty"
                next_id = row[0]

            # 3. Atualiza atomicamente para serving
            query_update = (
                "UPDATE queue_entries SET status = 'serving', called_by_user_id = ?, called_at = ? "
                "WHERE id = ? AND guild_id = ? AND status = 'waiting';"
            )
            await self._conn.execute(query_update, (monitor_user_id, now, next_id, guild_id))
            await self._conn.commit()

        entry = await self.get_queue_entry_by_id(guild_id, next_id)
        return entry, None

    async def finish_serving(self, guild_id: str) -> QueueEntry | None:
        """Encerra o atendimento em andamento marcando status como 'completed'."""
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()

        async with self._lock:
            serving = await self.get_active_serving(guild_id)
            if not serving:
                return None

            query = (
                "UPDATE queue_entries SET status = 'completed', finished_at = ? "
                "WHERE id = ? AND guild_id = ?;"
            )
            await self._conn.execute(query, (now, serving.id, guild_id))
            await self._conn.commit()

        return await self.get_queue_entry_by_id(guild_id, serving.id)

    async def clear_queue(self, guild_id: str) -> int:
        """Cancela todas as entradas pendentes e em atendimento da fila."""
        await self.connect()
        assert self._conn is not None
        async with self._lock:
            query = (
                "UPDATE queue_entries SET status = 'cancelled' "
                "WHERE guild_id = ? AND status IN ('waiting', 'serving');"
            )
            async with self._conn.execute(query, (guild_id,)) as cursor:
                count = cursor.rowcount
            await self._conn.commit()
            return count

    # -------------------------------------------------------------------------
    # Materials
    # -------------------------------------------------------------------------

    async def add_material(
        self,
        guild_id: str,
        title: str,
        url: str,
        tags: list[str],
        created_by_user_id: str,
        description: str = "",
    ) -> Material:
        await self.connect()
        assert self._conn is not None
        now = utc_iso_now()

        # Normaliza tags
        clean_tags = sorted(list({t.strip().lower() for t in tags if t.strip()}))

        async with self._lock:
            query = (
                "INSERT INTO materials (guild_id, title, description, url, created_by_user_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?);"
            )
            async with self._conn.execute(
                query,
                (guild_id, title.strip(), description.strip(), url.strip(), created_by_user_id, now),
            ) as cursor:
                material_id = cursor.lastrowid

            for tag in clean_tags:
                await self._conn.execute(
                    "INSERT INTO material_tags (material_id, tag) VALUES (?, ?);",
                    (material_id, tag[:50]),
                )
            await self._conn.commit()

        material = await self.get_material(guild_id, material_id)
        assert material is not None
        return material

    async def get_material(self, guild_id: str, material_id: int) -> Material | None:
        await self.connect()
        assert self._conn is not None
        query = "SELECT * FROM materials WHERE id = ? AND guild_id = ?;"
        async with self._conn.execute(query, (material_id, guild_id)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

        # Tags
        query_tags = "SELECT tag FROM material_tags WHERE material_id = ? ORDER BY tag;"
        async with self._conn.execute(query_tags, (material_id,)) as cursor:
            tag_rows = await cursor.fetchall()
            tags = [r[0] for r in tag_rows]

        d = dict(row)
        d["tags"] = tags
        return Material(**d)

    async def delete_material(self, guild_id: str, material_id: int) -> bool:
        await self.connect()
        assert self._conn is not None
        async with self._lock:
            async with self._conn.execute(
                "DELETE FROM materials WHERE id = ? AND guild_id = ?;",
                (material_id, guild_id),
            ) as cursor:
                deleted = cursor.rowcount > 0
            await self._conn.commit()
            return deleted

    async def search_materials(
        self,
        guild_id: str,
        term: str | None = None,
        tag: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Material]:
        await self.connect()
        assert self._conn is not None

        params: list[Any] = [guild_id]
        where_clauses = ["m.guild_id = ?"]

        join_clause = ""
        if tag and tag.strip():
            clean_tag = tag.strip().lower()
            join_clause = "JOIN material_tags mt ON m.id = mt.material_id"
            where_clauses.append("mt.tag = ?")
            params.append(clean_tag)

        if term and term.strip():
            clean_term = f"%{term.strip()}%"
            where_clauses.append("(m.title LIKE ? OR m.description LIKE ?)")
            params.extend([clean_term, clean_term])

        where_sql = " AND ".join(where_clauses)
        query = f"""
            SELECT DISTINCT m.id, m.guild_id, m.title, m.description, m.url, m.created_by_user_id, m.created_at
            FROM materials m
            {join_clause}
            WHERE {where_sql}
            ORDER BY m.id DESC
            LIMIT ? OFFSET ?;
        """
        params.extend([limit, offset])

        async with self._conn.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()

        results: list[Material] = []
        for r in rows:
            mat_id = r["id"]
            query_tags = "SELECT tag FROM material_tags WHERE material_id = ? ORDER BY tag;"
            async with self._conn.execute(query_tags, (mat_id,)) as cursor:
                tag_rows = await cursor.fetchall()
                tags = [tr[0] for tr in tag_rows]
            d = dict(r)
            d["tags"] = tags
            results.append(Material(**d))

        return results
