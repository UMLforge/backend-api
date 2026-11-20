"""Runs the ai-service inside the backend process (AI_SERVICE_URL=inprocess).

Used on hosts that give you one web app (e.g. PythonAnywhere free). The code stays a separate service:
the backend still talks to it over HTTP, just through an in-memory transport instead of the network.
Both services have a package called `app`, so the ai-service is loaded under the name `umlforge_ai`.
"""
import importlib
import importlib.util
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "ai-service"  # repo layout: backend/ next to ai-service/


def load_ai_app(path: str = ""):
    pkg_dir = Path(path or DEFAULT_PATH) / "app"
    if "umlforge_ai" not in sys.modules:
        spec = importlib.util.spec_from_file_location("umlforge_ai", pkg_dir / "__init__.py",
                                                      submodule_search_locations=[str(pkg_dir)])
        module = importlib.util.module_from_spec(spec)
        sys.modules["umlforge_ai"] = module
        spec.loader.exec_module(module)
    return importlib.import_module("umlforge_ai.main").app
