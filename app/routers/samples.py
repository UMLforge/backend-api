"""Example diagrams. To add one, drop a JSON file into app/samples/ (same format as the others)."""
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

from ..errors import AppError

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
router = APIRouter(prefix="/api/samples", tags=["samples"])


@lru_cache
def _load() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAMPLES_DIR.glob("*.json"))}


@router.get("")
def list_samples() -> list[dict]:
    return [{"id": key, "title": s.get("title", key)} for key, s in _load().items()]


@router.get("/{sample_id}")
def get_sample(sample_id: str) -> dict:
    sample = _load().get(sample_id)
    if sample is None:
        raise AppError(404, "Sample not found", f"There is no sample called '{sample_id}'.")
    return sample
