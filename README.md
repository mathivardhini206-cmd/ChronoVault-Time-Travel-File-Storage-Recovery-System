# ChronoVault — Time-Travel Storage & Recovery

A local-first file versioning and recovery platform. Every save creates a timestamped, SHA-256-verified snapshot stored in a content-addressed blob store with deduplication, so identical content is stored only once.

## Features
- Point-in-time recovery (restore any past version)
- SHA-256 integrity hashing
- Content-addressed deduplication
- SQLite metadata database (files, versions, audit log)
- Storage analytics (logical vs physical size, space saved)
- Audit log of all uploads and restores
- Glassmorphism dashboard (dark theme)

## Tech Stack
Backend: Python, Flask. Storage: content-addressed blobs + SHA-256. Database: SQLite. Frontend: HTML, CSS, JavaScript.

## Run locally
python3 -m venv venv && source venv/bin/activate && pip install flask && python app.py

Then open http://127.0.0.1:5055
