# PythonAnywhere WSGI entry point for the UMLforge backend.
#
# Paste this whole file into the WSGI configuration file linked on PythonAnywhere's "Web" tab
# (/var/www/<username>_pythonanywhere_com_wsgi.py) and set REPO below.
# PythonAnywhere runs WSGI apps; the backend is FastAPI (ASGI), so it is wrapped with a2wsgi.
import os
import sys
from pathlib import Path

REPO = Path("/home/YOUR_PA_USERNAME/backend-api")  # <-- where you cloned this repo

# Settings come from <repo>/.env (KEY=value lines; see .env.example).
env_file = REPO / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.split(" #", 1)[0]  # drop trailing "  # comment"
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

os.environ.setdefault("DB_PATH", str(REPO / "data" / "umlforge.db"))

# In-process AI needs the ai-service code on disk; without it, run with AI disabled instead of crashing.
if os.environ.get("AI_SERVICE_URL", "inprocess") == "inprocess":
    ai_path = Path(os.environ.get("AI_SERVICE_PATH") or REPO.parent / "ai-service")
    if (ai_path / "app" / "main.py").exists():
        os.environ["AI_SERVICE_URL"], os.environ["AI_SERVICE_PATH"] = "inprocess", str(ai_path)
    else:
        os.environ["AI_SERVICE_URL"] = "http://127.0.0.1:9"  # nothing there -> /api/ai/status says unavailable

sys.path.insert(0, str(REPO))

from a2wsgi import ASGIMiddleware  # noqa: E402
from app.main import app  # noqa: E402

application = ASGIMiddleware(app)
