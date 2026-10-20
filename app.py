from pathlib import Path
import os
import tempfile

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from storage import (
    BASE_DIR,
    VERSIONS_DIR,
    save_version,
    list_versions,
    get_version_path,
    restore_version,
    store_blob,
)

from db import (
    init_db,
    record_version,
    log_action,
    get_audit_log,
    record_blob_ref,
    storage_stats,
)

# create the database tables on startup (safe if they already exist)
init_db()

app = Flask(__name__)

UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/")
def home():
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/files")
def files():
    names = sorted(
        path.name
        for path in UPLOADS_DIR.iterdir()
        if path.is_file()
    )
    return jsonify({"files": names})


@app.route("/audit")
def audit():
    return jsonify({"audit": get_audit_log()})


@app.route("/stats")
def stats():
    return jsonify(storage_stats())


@app.route("/upload", methods=["POST"])
def upload():
    uploaded = request.files.get("file")

    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Choose a file first."}), 400

    filename = secure_filename(uploaded.filename)
    if not filename:
        return jsonify({"error": "Invalid filename."}), 400

    current_path = UPLOADS_DIR / filename
    temp_path = None

    try:
        # Stage the incoming file separately.
        with tempfile.NamedTemporaryFile(
            dir=UPLOADS_DIR,
            prefix=".upload-",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            uploaded.save(temp_file)

        # Snapshot a version under the REAL filename (not the temp name).
        metadata = save_version(temp_path, filename)

        # Record this version in the database + audit log.
        record_version(
            filename,
            metadata["version"],
            metadata["sha256"],
            metadata["size_bytes"],
            metadata["created_at"],
        )
        log_action("upload", filename, f"version {metadata['version']}")

        # Deduplicate: store content once, record whether it was new.
        sha, was_new, size = store_blob(temp_path)
        record_blob_ref(sha, size, was_new, filename)

        # Replace the current file only after the version is saved.
        os.replace(temp_path, current_path)
        temp_path = None

        return jsonify({
            "message": "Upload saved and version created.",
            "filename": filename,
            "version": metadata,
            "versions": list_versions(filename),
        })

    except Exception:
        app.logger.exception("Upload failed")
        return jsonify({"error": "Could not save the upload."}), 500

    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@app.route("/versions/<filename>")
def versions(filename):
    filename = secure_filename(filename)

    if not filename:
        return jsonify({"error": "Invalid filename."}), 400

    return jsonify({"versions": list_versions(filename)})


@app.route("/restore", methods=["POST"])
def restore():
    data = request.get_json(silent=True) or {}
    filename = secure_filename(data.get("filename", ""))
    version_name = data.get("version", "")

    if (
        not filename
        or not isinstance(version_name, str)
        or not version_name
    ):
        return jsonify({
            "error": "Filename and version are required."
        }), 400

    current_path = UPLOADS_DIR / filename

    try:
        get_version_path(filename, version_name)

        # Preserve the current state before restoring an older version.
        if current_path.is_file():
            save_version(current_path)

        restore_info = restore_version(
            filename, version_name, current_path
        )

        log_action("restore", filename, f"restored {version_name}")

        content = current_path.read_bytes().decode(
            "utf-8", errors="replace"
        )

        return jsonify({
            "message": "Version restored successfully.",
            "content": content,
            "restored": restore_info,
            "versions": list_versions(filename),
        })

    except FileNotFoundError:
        return jsonify({"error": "Version not found."}), 404
    except (ValueError, OSError):
        app.logger.exception("Restore failed")
        return jsonify({"error": "Could not restore this version."}), 400
    except Exception:
        app.logger.exception("Unexpected restore failure")
        return jsonify({"error": "Unexpected restore error."}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=False)