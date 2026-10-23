#!/usr/bin/env python3
"""Local-only control server for the review dashboard.

Serves the self-contained dashboard and exposes a tiny JSON API used by the
"暂停/恢复自动复盘" switch. Bind is hard-coded to 127.0.0.1.

This is not needed for GitHub Pages; Pages can only show the baked-in status.
"""

from __future__ import annotations

import json
import subprocess
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
STATE = BASE / "state" / "auto_review.json"
DASHBOARD = BASE / "dashboard.html"
BUILDER = BASE / "build_dashboard.py"
TASKS = ["DSH-Daily-Review", "DSH-US-Review"]
DEFAULT_PORT = 8777
HOST = "127.0.0.1"


def read_state() -> dict:
    if not STATE.exists():
        return {"paused": False, "updatedAt": "", "reason": ""}
    try:
        return json.loads(STATE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"paused": False, "updatedAt": "", "reason": "unreadable state"}


def write_state(paused: bool, reason: str) -> dict:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    obj = {
        "paused": bool(paused),
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reason": reason,
    }
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE)
    return obj


def task_state(task_name: str) -> tuple[bool, str]:
    """Return (exists, state text) using PowerShell's Get-ScheduledTask."""
    command = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
        f"$t=Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue; if($t){{$t.State}}",
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=15)
        text = (proc.stdout or "").strip()
        return bool(text), text
    except Exception:
        return False, ""


def all_task_states() -> list[dict]:
    out = []
    for task_name in TASKS:
        exists, state = task_state(task_name)
        out.append({"name": task_name, "exists": exists, "state": state})
    return out


def set_tasks(paused: bool) -> tuple[bool, str]:
    flag = "/DISABLE" if paused else "/ENABLE"
    changed = 0
    messages = []
    for task_name in TASKS:
        exists, _ = task_state(task_name)
        if not exists:
            messages.append(f"{task_name}: not found")
            continue
        try:
            proc = subprocess.run(
                ["schtasks.exe", "/Change", "/TN", task_name, flag],
                capture_output=True, text=True, timeout=20,
            )
            if proc.returncode == 0:
                changed += 1
            else:
                messages.append(f"{task_name}: {(proc.stderr or proc.stdout or '').strip()}")
        except Exception as exc:
            messages.append(f"{task_name}: {exc}")
    return changed > 0, "; ".join(messages)


def rebuild() -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [sys.executable, str(BUILDER), "--offline"],
            cwd=str(BASE), capture_output=True, text=True, timeout=120,
        )
        return proc.returncode == 0, (proc.stdout or proc.stderr or "").strip()
    except Exception as exc:
        return False, str(exc)


def status() -> dict:
    state = read_state()
    tasks = all_task_states()
    existing = [t for t in tasks if t["exists"]]
    summary = " + ".join(f"{t['name'].replace('DSH-', '')}:{t['state']}" for t in existing) if existing else "not registered"
    return {
        "paused": bool(state.get("paused")),
        "updatedAt": state.get("updatedAt", ""),
        "reason": state.get("reason", ""),
        "taskExists": bool(existing),
        "taskState": summary,
        "taskSummary": summary,
        "tasks": tasks,
        "dashboard": str(DASHBOARD),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "DSHReviewControl/1.0"

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _file(self, path: Path, content_type: str):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _allowed(self) -> bool:
        # Same-origin browser calls have an Origin; allow empty (curl/local tools)
        # and reject any other website trying to drive the switch.
        origin = (self.headers.get("Origin") or "").strip()
        host = (self.headers.get("Host") or "").strip()
        if not origin:
            return True
        return origin in (f"http://{host}", f"http://127.0.0.1:{DEFAULT_PORT}", f"http://localhost:{DEFAULT_PORT}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html", "/dashboard.html"):
            self._file(DASHBOARD, "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._json(200, status())
            return
        if path == "/reports/latest.md":
            self._file(BASE / "reports" / "latest.md", "text/markdown; charset=utf-8")
            return
        if path in ("/preview_my.png", "/dashboard.png"):
            self._file(BASE / path.lstrip("/"), "image/png")
            return
        self.send_error(404, "not found")

    def do_POST(self):
        if not self._allowed():
            self._json(403, {"ok": False, "error": "origin not allowed"})
            return
        path = urlparse(self.path).path
        if path not in ("/api/pause", "/api/resume"):
            self._json(404, {"ok": False, "error": "unknown API"})
            return
        # Body is intentionally ignored; only the two named actions exist.
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            try:
                self.rfile.read(length)
            except Exception:
                pass
        paused = path.endswith("pause")
        state = write_state(paused, "dashboard switch")
        task_ok, task_msg = set_tasks(paused)
        build_ok, build_msg = rebuild()
        payload = status()
        payload.update({
            "ok": True,
            "taskChanged": task_ok,
            "taskMessage": task_msg,
            "dashboardRebuilt": build_ok,
            "buildMessage": "" if build_ok else build_msg,
        })
        self._json(200, payload)

    def log_message(self, fmt, *args):
        # Keep the console quiet; the UI is the source of truth.
        pass


def main() -> int:
    port = DEFAULT_PORT
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (ValueError, IndexError):
            port = DEFAULT_PORT
    url = f"http://{HOST}:{port}/"
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"[control] {url}")
    print(f"[control] state: {STATE}")
    print("[control] Ctrl+C to stop")
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
