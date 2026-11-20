"""Monitoring for the admin dashboard: request stats, recent errors, system resources, storage.

Everything is kept in this process's memory (no extra service). Numbers reset when the backend restarts;
the dashboard shows the uptime so that's visible. System figures come from /proc and /sys (Linux:
Docker, PythonAnywhere); on other systems they're reported as unavailable instead of failing.
"""
import os
import platform
import shutil
import sys
import time
from collections import deque
from pathlib import Path

STARTED = time.time()
_requests: deque = deque(maxlen=20_000)  # (timestamp, ms, status, area)
_errors: deque = deque(maxlen=100)       # recent failures with developer details
_counts = {"total": 0, "rate_limited": 0}


def area_of(path: str) -> str:
    """Groups URLs into areas for the dashboard: /api/ai/review -> 'ai', /api/shares/x -> 'shares'."""
    parts = path.strip("/").split("/")
    return parts[1] if len(parts) > 1 and parts[0] == "api" else "static"


def record_request(path: str, status: int, ms: float) -> None:
    _counts["total"] += 1
    if status == 429:
        _counts["rate_limited"] += 1
    _requests.append((time.time(), ms, status, area_of(path)))


def record_error(status: int, path: str, title: str, details: str = "", level: str = "error") -> None:
    _errors.appendleft({"at": time.time(), "status": status, "path": path, "title": title, "details": details, "level": level})


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(len(values) * 0.95))], 1)


def traffic() -> dict:
    now = time.time()
    last_5m = [r for r in _requests if now - r[0] <= 300]
    last_1m = [r for r in last_5m if now - r[0] <= 60]
    per_minute = []  # last 30 minutes, oldest first
    for m in range(29, -1, -1):
        bucket = [r for r in _requests if m * 60 <= now - r[0] < (m + 1) * 60]
        per_minute.append({"minute": m, "requests": len(bucket), "errors": sum(r[2] >= 500 for r in bucket),
                           "p95_ms": _p95([r[1] for r in bucket])})
    areas: dict[str, dict] = {}
    for _, ms, status, area in last_5m:
        a = areas.setdefault(area, {"requests": 0, "errors": 0, "ms": []})
        a["requests"] += 1
        a["errors"] += status >= 500
        a["ms"].append(ms)
    return {
        "uptime_s": round(now - STARTED),
        "total": _counts["total"],
        "rate_limited_total": _counts["rate_limited"],
        "per_min": len(last_1m),
        "errors_5m": sum(r[2] >= 500 for r in last_5m),
        "client_errors_5m": sum(400 <= r[2] < 500 for r in last_5m),
        "p95_ms_5m": _p95([r[1] for r in last_5m]),
        "areas": {k: {"requests": v["requests"], "errors": v["errors"], "p95_ms": _p95(v["ms"])} for k, v in sorted(areas.items())},
        "history": per_minute,
    }


def recent_errors(limit: int = 50) -> list[dict]:
    return list(_errors)[:limit]


# ---- system resources ------------------------------------------------------------------------

_last_cpu: tuple[float, float] | None = None  # (busy, total) jiffies from the previous reading


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text()
    except OSError:
        return None


def _cpu_percent() -> float | None:
    """CPU use since the previous call (the dashboard polls, so this is 'over the last few seconds')."""
    global _last_cpu
    stat = _read("/proc/stat")
    if not stat:
        return None
    fields = [float(x) for x in stat.splitlines()[0].split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    total = sum(fields)
    busy = total - idle
    prev, _last_cpu = _last_cpu, (busy, total)
    if not prev or total == prev[1]:
        return None
    return round(100 * (busy - prev[0]) / (total - prev[1]), 1)


def _meminfo() -> dict:
    info = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        key, _, rest = line.partition(":")
        if rest.strip().endswith("kB"):
            info[key] = int(rest.split()[0]) * 1024
    return info


def _process_rss() -> int | None:
    for line in (_read("/proc/self/status") or "").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return None


def _cgroup_memory() -> dict | None:
    """Container memory use/limit (cgroup v2), e.g. inside Docker with a memory limit."""
    current, limit = _read("/sys/fs/cgroup/memory.current"), _read("/sys/fs/cgroup/memory.max")
    if not current:
        return None
    limit = limit.strip() if limit else "max"
    return {"used": int(current), "limit": None if limit == "max" else int(limit)}


def system(data_dir: str) -> dict:
    mem = _meminfo()
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        load = None
    try:
        disk = shutil.disk_usage(data_dir if Path(data_dir).exists() else "/")
        disk = {"total": disk.total, "used": disk.used, "free": disk.free}
    except OSError:
        disk = None
    return {
        "host": platform.node(), "os": f"{platform.system()} {platform.release()}", "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(), "cpu_percent": _cpu_percent(), "load": load,
        "memory": {"total": mem["MemTotal"], "available": mem.get("MemAvailable", 0)} if "MemTotal" in mem else None,
        "container_memory": _cgroup_memory(),
        "process_rss": _process_rss(),
        "disk": disk,
    }


def storage(db, data_dir: str) -> dict:
    """Database kind, size and row counts. Times the queries too (database latency)."""
    started = time.perf_counter()
    counts = {}
    for table, sql in [("diagrams", "SELECT COUNT(*) AS n FROM diagrams"),
                       ("active_links", "SELECT COUNT(*) AS n FROM shares WHERE expires_at >= ?"),
                       ("expired_links", "SELECT COUNT(*) AS n FROM shares WHERE expires_at < ?"),
                       ("admin_users", "SELECT COUNT(*) AS n FROM admin_users")]:
        rows, _ = db.run(sql, (time.time(),) if "?" in sql else ())
        counts[table] = rows[0]["n"]
    latency_ms = round((time.perf_counter() - started) * 1000 / 4, 1)
    if db.postgres:
        rows, _ = db.run("SELECT pg_database_size(current_database()) AS size")
        size = rows[0]["size"]
    else:
        size = sum(p.stat().st_size for p in Path(db.path).parent.glob(Path(db.path).name + "*") if p.is_file())
    return {"kind": "PostgreSQL" if db.postgres else "SQLite", "size_bytes": size, "query_ms": latency_ms,
            "data_dir": data_dir, **counts}
