import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "chronovault.db"


def get_db():
    """Open a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dictionaries
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Create the tables if they don't already exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            filename  TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS versions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id     INTEGER NOT NULL,
            version_name TEXT NOT NULL,
            sha256      TEXT NOT NULL,
            size_bytes  INTEGER NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            action    TEXT NOT NULL,
            filename  TEXT,
            detail    TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS blob_refs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sha256     TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            was_new    INTEGER NOT NULL,
            filename   TEXT,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def get_or_create_file(filename):
    """Return the id of a file row, creating it if needed."""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM files WHERE filename = ?", (filename,)
    ).fetchone()

    if row is None:
        cur = conn.execute(
            "INSERT INTO files (filename, created_at) VALUES (?, ?)",
            (filename, _now()),
        )
        file_id = cur.lastrowid
    else:
        file_id = row["id"]

    conn.commit()
    conn.close()
    return file_id


def record_version(filename, version_name, sha256, size_bytes, created_at):
    """Insert a version record linked to its file."""
    file_id = get_or_create_file(filename)
    conn = get_db()
    conn.execute(
        """INSERT INTO versions
           (file_id, version_name, sha256, size_bytes, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (file_id, version_name, sha256, size_bytes, created_at),
    )
    conn.commit()
    conn.close()


def log_action(action, filename=None, detail=None):
    """Record an event in the audit log."""
    conn = get_db()
    conn.execute(
        """INSERT INTO audit_log (action, filename, detail, created_at)
           VALUES (?, ?, ?, ?)""",
        (action, filename, detail, _now()),
    )
    conn.commit()
    conn.close()


def record_blob_ref(sha256, size_bytes, was_new, filename):
    """Record every time content is stored or deduplicated."""
    conn = get_db()
    conn.execute(
        """INSERT INTO blob_refs (sha256, size_bytes, was_new, filename, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (sha256, size_bytes, 1 if was_new else 0, filename, _now()),
    )
    conn.commit()
    conn.close()


def storage_stats():
    """Compute logical vs physical storage and space saved by dedup."""
    conn = get_db()

    # logical = total size of every upload (as if nothing were deduplicated)
    logical = conn.execute(
        "SELECT COALESCE(SUM(size_bytes), 0) AS s FROM blob_refs"
    ).fetchone()["s"]

    # physical = size of only the unique blobs actually stored
    physical = conn.execute(
        "SELECT COALESCE(SUM(size_bytes), 0) AS s FROM blob_refs WHERE was_new = 1"
    ).fetchone()["s"]

    total_uploads = conn.execute(
        "SELECT COUNT(*) AS c FROM blob_refs"
    ).fetchone()["c"]

    deduped = conn.execute(
        "SELECT COUNT(*) AS c FROM blob_refs WHERE was_new = 0"
    ).fetchone()["c"]

    conn.close()

    saved = logical - physical
    percent = round((saved / logical) * 100, 1) if logical else 0.0

    return {
        "logical_bytes": logical,
        "physical_bytes": physical,
        "saved_bytes": saved,
        "saved_percent": percent,
        "total_uploads": total_uploads,
        "deduplicated_uploads": deduped,
    }


def get_versions(filename):
    """Return all version records for a file, newest first."""
    conn = get_db()
    rows = conn.execute(
        """SELECT v.version_name, v.sha256, v.size_bytes, v.created_at
           FROM versions v
           JOIN files f ON f.id = v.file_id
           WHERE f.filename = ?
           ORDER BY v.created_at DESC, v.id DESC""",
        (filename,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_audit_log(limit=50):
    """Return recent audit-log events."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- quick self-test ----
if __name__ == "__main__":
    init_db()
    print("Database created at:", DB_PATH)

    record_version("test.txt", "2026-01-01_00-00-00__test.txt",
                   "abc123", 42, _now())
    log_action("upload", "test.txt", "self-test record")

    print("Versions for test.txt:", get_versions("test.txt"))
    print("Audit log:", get_audit_log())
    print("db.py works!")