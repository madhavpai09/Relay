from __future__ import annotations

import sqlite3
import threading

from .config import DATA_DIR, DATABASE_PATH


DATA_DIR.mkdir(parents=True, exist_ok=True)

db_lock = threading.RLock()
connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
connection.row_factory = sqlite3.Row

with db_lock:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS repositories (
          id TEXT PRIMARY KEY,
          full_name TEXT NOT NULL UNIQUE,
          provider TEXT NOT NULL,
          local_path TEXT NOT NULL,
          default_branch TEXT,
          pipeline_file TEXT NOT NULL,
          language TEXT,
          active INTEGER NOT NULL,
          verified INTEGER NOT NULL DEFAULT 0,
          verified_at TEXT,
          verification_message TEXT,
          last_pipeline_path TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          event TEXT NOT NULL,
          delivery_id TEXT NOT NULL UNIQUE,
          repository TEXT,
          trigger_type TEXT,
          language TEXT,
          ref TEXT,
          commit_sha TEXT,
          pull_request_number INTEGER,
          action TEXT,
          base_ref TEXT,
          head_ref TEXT,
          workspace_path TEXT,
          pipeline_file TEXT,
          assigned_worker_id TEXT,
          assigned_worker_name TEXT,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          started_at TEXT,
          completed_at TEXT,
          payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS job_logs (
          id TEXT PRIMARY KEY,
          job_id TEXT NOT NULL,
          timestamp TEXT NOT NULL,
          level TEXT NOT NULL,
          message TEXT NOT NULL,
          FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_repositories_full_name ON repositories(full_name);
        CREATE INDEX IF NOT EXISTS idx_jobs_delivery_id ON jobs(delivery_id);
        CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id);
        """
    )


def _ensure_column(table: str, column: str, definition: str) -> None:
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


with db_lock:
    _ensure_column("repositories", "language", "TEXT")
    _ensure_column("repositories", "verified", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column("repositories", "verified_at", "TEXT")
    _ensure_column("repositories", "verification_message", "TEXT")
    _ensure_column("repositories", "last_pipeline_path", "TEXT")
    _ensure_column("jobs", "language", "TEXT")
    _ensure_column("jobs", "assigned_worker_id", "TEXT")
    _ensure_column("jobs", "assigned_worker_name", "TEXT")
    connection.commit()


def fetch_one(query: str, params: tuple | dict = ()) -> sqlite3.Row | None:
    with db_lock:
        return connection.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
    with db_lock:
        return connection.execute(query, params).fetchall()


def execute(query: str, params: tuple | dict = ()) -> None:
    with db_lock:
        connection.execute(query, params)
        connection.commit()


def executescript(script: str) -> None:
    with db_lock:
        connection.executescript(script)
        connection.commit()


def transaction() -> sqlite3.Connection:
    return connection
