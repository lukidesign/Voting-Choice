"""Vercel Serverless Function: /api/votes

GET    -> 返回所有投票
POST   -> 提交投票 { name, choices, overwrite? }
DELETE -> 清空所有投票（可选 token）

数据存储：Vercel KV（Upstash Redis REST API）
环境变量：KV_REST_API_URL, KV_REST_API_TOKEN —— 在 Vercel 控制台连接 KV 存储后自动注入
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.request
import urllib.error

KV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")
KEY = "irun:votes:v1"

MAX_SELECT = 3
MAX_NAME_LEN = 20
VALID_IDS = {f"d{i}" for i in range(12)}


def kv_get():
    """读取存储的投票数据。KV 未配置时返回空（用于本地预览）。"""
    if not KV_URL or not KV_TOKEN:
        return {"voters": []}
    req = urllib.request.Request(
        f"{KV_URL}/get/{KEY}",
        headers={"Authorization": f"Bearer {KV_TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            val = data.get("result")
            if not val:
                return {"voters": []}
            return json.loads(val)
    except Exception:
        return {"voters": []}


def kv_set(data):
    if not KV_URL or not KV_TOKEN:
        raise RuntimeError("KV not configured")
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{KV_URL}/set/{KEY}",
        data=payload,
        headers={
            "Authorization": f"Bearer {KV_TOKEN}",
            "Content-Type": "text/plain",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=5)


class handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                return None
            # Vercel Lambda may strip Content-Length; fall back to read-all
            raw = self.rfile.read(length) if length > 0 else self.rfile.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def do_OPTIONS(self):
        self._json(204, {})

    def do_GET(self):
        self._json(200, kv_get())

    def do_POST(self):
        payload = self._read_body()
        if not isinstance(payload, dict):
            self._json(400, {"error": "invalid_json"})
            return

        name = (payload.get("name") or "").strip()
        choices = payload.get("choices") or []

        if not name:
            self._json(400, {"error": "name_required"})
            return
        if len(name) > MAX_NAME_LEN:
            self._json(400, {"error": "name_too_long"})
            return
        if not isinstance(choices, list) or not (1 <= len(choices) <= MAX_SELECT):
            self._json(400, {"error": "bad_choices"})
            return

        choices = list(dict.fromkeys(choices))
        for c in choices:
            if c not in VALID_IDS:
                self._json(400, {"error": "invalid_choice", "choice": c})
                return

        overwrite = bool(payload.get("overwrite"))
        data = kv_get()
        idx = next((i for i, v in enumerate(data["voters"]) if v.get("name") == name), -1)
        if idx >= 0 and not overwrite:
            self._json(409, {"error": "name_exists", "name": name})
            return

        record = {"name": name, "choices": choices, "time": int(time.time() * 1000)}
        if idx >= 0:
            data["voters"][idx] = record
        else:
            data["voters"].append(record)

        try:
            kv_set(data)
        except Exception:
            self._json(500, {"error": "kv_write_failed"})
            return

        self._json(200, {"ok": True, "voters": data["voters"]})

    def do_DELETE(self):
        payload = self._read_body() or {}
        required = os.environ.get("IRUN_RESET_TOKEN")
        if required and payload.get("token") != required:
            self._json(403, {"error": "forbidden"})
            return
        try:
            kv_set({"voters": []})
        except Exception:
            self._json(500, {"error": "kv_write_failed"})
            return
        self._json(200, {"ok": True})
