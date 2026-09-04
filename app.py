"""
app.py — Main Entrypoint for Hugging Face Spaces & Local Deployment
Runs the Reconcile Flask engine on port 7860 (or $PORT).
"""

import os
import sys

# Ensure root and backend path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.app import app as flask_app
from backend.db import init_db

# Initialize SQLite database
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"Starting Reconcile Production Engine on http://0.0.0.0:{port}", flush=True)
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
