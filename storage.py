import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VERSIONS_DIR = BASE_DIR / "versions"
VERSIONS_DIR.mkdir(parents=True, exist_ok=True)


def file_hash(file_path):
    """Calculate a SHA-256 fingerprint of a file."""
    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def save_version(file_path, filename=None):
    """Save a timestamped snapshot and return its metadata.

    file_path = the file to snapshot (may be a temporary staging file).
    filename  = the REAL name to store it under (defaults to the file's own name).
    """
    file_path = Path(file_path).resolve()

    if not file_path.is_file():
        raise FileNotFoundError("The file to snapshot does not exist.")

    if filename is None:
        filename = file_path.name

    # safety: never allow a path, only a plain filename
    if Path(filename).name != filename:
        raise ValueError("Invalid filename.")

    file_folder = VERSIONS_DIR / filename
    file_folder.mkdir(parents=True, exist_ok=True)

    digest = file_hash(file_path)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    version_name = f"{timestamp}__{filename}"
    destination = file_folder / version_name

    shutil.copy2(file_path, destination)

    return {
        "version": version_name,
        "filename": filename,
        "sha256": digest,
        "size_bytes": destination.stat().st_size,
        "created_at": datetime.fromtimestamp(
            destination.stat().st_mtime
        ).isoformat(timespec="seconds"),
    }


def list_versions(filename):
    """List a file's versions, newest first."""
    if not filename or Path(filename).name != filename:
        raise ValueError("Invalid filename.")

    file_folder = VERSIONS_DIR / filename

    if not file_folder.is_dir():
        return []

    return sorted(
        (
            item.name for item in file_folder.iterdir()
            if item.is_file()
        ),
        reverse=True,
    )


def get_version_path(filename, version_name):
    """Resolve a version while preventing path traversal."""
    if not filename or Path(filename).name != filename:
        raise ValueError("Invalid filename.")

    if not version_name or Path(version_name).name != version_name:
        raise ValueError("Invalid version name.")

    file_folder = VERSIONS_DIR / filename
    source = file_folder / version_name

    if not source.is_file():
        raise FileNotFoundError("Version not found.")

    return source


def restore_version(filename, version_name, restore_path):
    """Restore a snapshot to a chosen destination."""
    source = get_version_path(filename, version_name)
    restore_path = Path(restore_path).resolve()

    if source.resolve() == restore_path:
        raise ValueError("Source and destination cannot be the same.")

    restore_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, restore_path)

    return {
        "filename": filename,
        "version": version_name,
        "sha256": file_hash(restore_path),
        "size_bytes": restore_path.stat().st_size,
    }


# =========================================================
# CONTENT-ADDRESSED DEDUPLICATION
# Store each unique file content ONCE, named by its SHA-256.
# Identical uploads reuse the same stored "blob" = space saved.
# =========================================================

BLOBS_DIR = BASE_DIR / "blobs"
BLOBS_DIR.mkdir(parents=True, exist_ok=True)


def store_blob(file_path):
    """Store a file's content once, keyed by its SHA-256 hash.

    Returns (sha256, was_new, size_bytes):
      was_new = True  -> content was new, a blob was written
      was_new = False -> identical content already existed (space saved!)
    """
    file_path = Path(file_path).resolve()
    if not file_path.is_file():
        raise FileNotFoundError("The file to store does not exist.")

    digest = file_hash(file_path)
    size = file_path.stat().st_size
    blob_path = BLOBS_DIR / digest

    if blob_path.exists():
        # identical content already stored -> don't store again
        return digest, False, size

    shutil.copy2(file_path, blob_path)
    return digest, True, size


def blob_path_for(sha256):
    """Return the stored blob path for a given hash (or None)."""
    path = BLOBS_DIR / sha256
    return path if path.exists() else None


def physical_storage_used():
    """Total bytes actually stored in the blob store (deduplicated)."""
    total = 0
    for item in BLOBS_DIR.iterdir():
        if item.is_file():
            total += item.stat().st_size
    return total


if __name__ == "__main__":
    print("Time-Travel Storage engine")
    print("Versions directory:", VERSIONS_DIR)
    print("Blobs directory:", BLOBS_DIR)
    print("Storage engine loaded successfully.")