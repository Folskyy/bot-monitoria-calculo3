PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    welcome_channel_id TEXT NOT NULL,
    doubts_channel_id TEXT NOT NULL,
    queue_channel_id TEXT NOT NULL,
    student_role_id TEXT NOT NULL,
    monitor_role_id TEXT NOT NULL,
    welcome_message_id TEXT,
    office_hours_text TEXT NOT NULL DEFAULT 'Horários ainda não informados.',
    timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS students (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    full_name TEXT NOT NULL CHECK (length(trim(full_name)) BETWEEN 1 AND 100),
    ra TEXT NOT NULL CHECK (length(ra) BETWEEN 1 AND 32),
    class_name TEXT CHECK (class_name IS NULL OR length(class_name) <= 80),
    status TEXT NOT NULL DEFAULT 'pending_role'
        CHECK (status IN ('pending_role', 'active')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (guild_id, user_id),
    UNIQUE (guild_id, ra),
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS doubts (
    id INTEGER PRIMARY KEY,
    guild_id TEXT NOT NULL,
    author_user_id TEXT NOT NULL,
    interaction_id TEXT NOT NULL UNIQUE,
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message_id TEXT UNIQUE,
    thread_id TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'creating'
        CHECK (status IN ('creating', 'open', 'resolved', 'error')),
    resolved_by_user_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    resolved_at TEXT,
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_doubts_author
    ON doubts (guild_id, author_user_id, status);

CREATE TABLE IF NOT EXISTS queue_entries (
    id INTEGER PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting'
        CHECK (status IN ('waiting', 'serving', 'completed', 'cancelled')),
    called_by_user_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    called_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_one_active_per_student
    ON queue_entries (guild_id, user_id)
    WHERE status IN ('waiting', 'serving');

CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_one_serving_per_guild
    ON queue_entries (guild_id)
    WHERE status = 'serving';

CREATE INDEX IF NOT EXISTS idx_queue_fifo
    ON queue_entries (guild_id, status, created_at, id);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY,
    guild_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    created_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_materials_guild ON materials (guild_id);

CREATE TABLE IF NOT EXISTS material_tags (
    material_id INTEGER NOT NULL,
    tag TEXT NOT NULL CHECK (length(tag) BETWEEN 1 AND 50),
    PRIMARY KEY (material_id, tag),
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_material_tags_tag ON material_tags (tag);

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 80),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (guild_id, name),
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_classes_guild ON classes (guild_id);

