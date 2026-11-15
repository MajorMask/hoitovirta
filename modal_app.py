"""Deploy Hoitovirta on Modal (workspace majormask):  python3 -m modal deploy modal_app.py
Secrets come from the Modal secret 'hoitovirta' (created by setup.sh from .env). .env is excluded from the image,
so keys never ship inside it. One container only: the event store keeps its read model and the simulator in memory
(everything is also written to Aiven PostgreSQL, schema 'hv', so a restart reloads it)."""
import shlex
import subprocess

import modal

IGNORE = [".env", "*.env", "**/.env", "__pycache__", "**/__pycache__", ".venv", ".venv/**", "**/.venv/**", ".git", "sources",
          "archive", "submission", "demo-video", "**/*.db", "**/*.db-wal", "**/*.db-shm", "tracker", "docs"]

image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install_from_requirements("requirements.txt")
         .add_local_dir(".", remote_path="/root/hoitovirta", ignore=IGNORE))
app = modal.App("hoitovirta", image=image)


@app.function(secrets=[modal.Secret.from_name("hoitovirta")], max_containers=1, min_containers=1, scaledown_window=3600, timeout=24 * 3600)
@modal.concurrent(max_inputs=100)
@modal.web_server(8000, startup_timeout=240)
def web():
    cmd = "python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level warning"
    subprocess.Popen(shlex.split(cmd), cwd="/root/hoitovirta")
