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
          active INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          event TEXT NOT NULL,
          delivery_id TEXT NOT NULL UNIQUE,
          repository TEXT,
          trigger_type TEXT,
          ref TEXT,
          commit_sha TEXT,
          pull_request_number INTEGER,
          action TEXT,
          base_ref TEXT,
          head_ref TEXT,
          workspace_path TEXT,
          pipeline_file TEXT,
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
