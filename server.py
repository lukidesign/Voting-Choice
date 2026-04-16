#!/usr/bin/env python3
"""iRun Logo 投票 - 本地开发服务（仅依赖 Python 标准库）

启动：python3 server.py [port]
默认端口 8765。投票数据保存在同目录 votes.json。
此文件用于本地预览；线上部署在 Vercel 上由 api/votes.py 处理。
两者实现的是相同的 REST 接口：
  GET    /api/votes
  POST   /api/votes
  DELETE /api/votes
"""
import json
import os
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "votes.json")
MAX_SELECT = 3
MAX_NAME_LEN = 20
VALID_IDS = {f"d{i}" for i in range(12)}

_lock = threading.Lock()


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"voters": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"voters": []}


def save_data(data):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 1_000_000:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return None

    def _serve_file(self, rel_path):
        safe_rel = os.path.normpath(rel_path).lstrip(os.sep)
        full = os.path.join(ROOT, safe_rel)
        if not full.startswith(ROOT) or not os.path.isfile(full):
            self.send_error(404, "Not Found")
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        try:
            with open(full, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store" if ext == ".html" else "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/votes":
            with _lock:
                self._json(200, load_data())
            return
        if path == "/" or path == "/index.html":
            self._serve_file("index.html")
            return
        if path.startswith("/"):
            self._serve_file(path[1:])
            return
        self.send_error(404, "Not Found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/votes":
            self.send_error(404, "Not Found")
            return

        payload = self._read_json_body()
        if not isinstance(payload, dict):
            self._json(400, {"error": "invalid_json"})
            return

        name = (payload.get("name") or "").strip()
        choices = payload.get("choices") or []
        if not name:
            self._json(400, {"error": "name_required"}); return
        if len(name) > MAX_NAME_LEN:
            self._json(400, {"error": "name_too_long"}); return
        if not isinstance(choices, list) or not (1 <= len(choices) <= MAX_SELECT):
            self._json(400, {"error": "bad_choices"}); return
        choices = list(dict.fromkeys(choices))
        for c in choices:
            if c not in VALID_IDS:
                self._json(400, {"error": "invalid_choice", "choice": c}); return

        overwrite = bool(payload.get("overwrite"))
        with _lock:
            data = load_data()
            idx = next((i for i, v in enumerate(data["voters"]) if v.get("name") == name), -1)
            if idx >= 0 and not overwrite:
                self._json(409, {"error": "name_exists", "name": name}); return
            record = {"name": name, "choices": choices, "time": int(time.time() * 1000)}
            if idx >= 0:
                data["voters"][idx] = record
            else:
                data["voters"].append(record)
            save_data(data)
        self._json(200, {"ok": True, "voters": data["voters"]})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path != "/api/votes":
            self.send_error(404, "Not Found")
            return
        payload = self._read_json_body() or {}
        required = os.environ.get("IRUN_RESET_TOKEN")
        if required and payload.get("token") != required:
            self._json(403, {"error": "forbidden"}); return
        with _lock:
            save_data({"voters": []})
        self._json(200, {"ok": True})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"iRun 投票服务已启动: http://localhost:{port}/  (数据文件: {DATA_FILE})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止服务")
        server.shutdown()


if __name__ == "__main__":
    main()
