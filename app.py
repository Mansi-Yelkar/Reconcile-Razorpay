"""
app.py — Main Entrypoint for Hugging Face Spaces (Gradio SDK Compatible)
Mounts Reconcile Flask engine onto FastAPI & Gradio for ZeroGPU / CPU compatibility on HF Spaces.
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

# Ensure backend path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import FastAPI
from starlette.middleware.wsgi import WSGIMiddleware
import gradio as gr

from backend.app import app as flask_app
from backend.db import init_db

# Initialize SQLite Database
init_db()

# Create FastAPI wrapper
fastapi_app = FastAPI(title="Reconcile API Engine")

# Mount Flask app to handle all web routes, CSS, JS, and REST APIs at /app
fastapi_app.mount("/app", WSGIMiddleware(flask_app))

# Build Gradio UI container
with gr.Blocks(title="Reconcile — AI Revenue Recovery Orchestrator", theme=gr.themes.Soft()) as demo:
    gr.HTML("""
    <div style="background: #0f172a; padding: 16px 24px; border-radius: 12px; color: #ffffff; display: flex; justify-content: space-between; align-items: center; font-family: sans-serif; margin-bottom: 12px;">
      <div>
        <h2 style="margin: 0; font-size: 1.4rem; color: #ffffff;">⚡ reconcile</h2>
        <p style="margin: 2px 0 0; font-size: 0.85rem; color: #94a3b8;">Razorpay AI Buildathon Track 3 • AI Revenue Recovery Orchestrator</p>
      </div>
      <a href="/app/" target="_blank" style="background: #c3f53c; color: #0f172a; padding: 8px 16px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 0.85rem;">Open Fullscreen Dashboard ↗</a>
    </div>
    """)
    
    gr.HTML("""
    <iframe src="/app/" style="width:100%; height:920px; border:1px solid #e2e8f0; border-radius:12px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);"></iframe>
    """)

# Mount Gradio app onto FastAPI
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    import uvicorn
    print(f"Starting Reconcile Engine on http://0.0.0.0:{port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
