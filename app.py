import hmac
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

import haa

BASE = Path(__file__).parent


def load_env(path: Path):
    """.env 파일(KEY=VALUE)을 환경변수로 읽기. 이미 설정된 환경변수가 우선."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(BASE / ".env")

HOST = os.environ.get("HAA_HOST", "127.0.0.1")
PORT = int(os.environ.get("HAA_PORT", "5000"))
DB_PATH = Path(os.environ.get("HAA_DB_PATH") or BASE / "records.db")
AUTH_USER = os.environ.get("HAA_USER", "admin")
AUTH_PASSWORD = os.environ.get("HAA_PASSWORD", "")

app = Flask(__name__, static_folder="static", static_url_path="/static")


@app.before_request
def require_auth():
    """HAA_PASSWORD 가 설정되어 있으면 모든 요청에 Basic 인증 요구."""
    if not AUTH_PASSWORD:
        return None
    a = request.authorization
    if a and hmac.compare_digest(a.username or "", AUTH_USER) and hmac.compare_digest(a.password or "", AUTH_PASSWORD):
        return None
    return Response("인증이 필요합니다.", 401, {"WWW-Authenticate": 'Basic realm="HAA", charset="UTF-8"'})


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rebalance_date TEXT NOT NULL,
                apply_month TEXT,
                signal_asof TEXT,
                mode TEXT,
                canary_momentum REAL,
                weights TEXT,
                holdings TEXT,
                cash REAL,
                total_value REAL,
                memo TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def row_to_dict(row):
    d = dict(row)
    d["weights"] = json.loads(d["weights"] or "{}")
    d["holdings"] = json.loads(d["holdings"] or "[]")
    return d


@app.get("/")
def index():
    return send_from_directory(BASE / "static", "index.html")


@app.get("/api/signal")
def api_signal():
    try:
        sig = haa.compute_signal(
            use_partial=request.args.get("partial") == "1",
            force=request.args.get("refresh") == "1",
        )
        return jsonify(sig)
    except Exception as e:  # 네트워크/데이터 오류를 화면에 표시
        return jsonify({"error": str(e)}), 502


@app.get("/api/history")
def api_history():
    try:
        return jsonify(haa.signal_history(int(request.args.get("months", 24))))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/records")
def list_records():
    with db() as conn:
        rows = conn.execute("SELECT * FROM records ORDER BY rebalance_date DESC, id DESC").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.post("/api/records")
def create_record():
    d = request.get_json(force=True)
    if not d.get("rebalance_date"):
        return jsonify({"error": "리밸런싱 날짜가 필요합니다."}), 400
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO records (rebalance_date, apply_month, signal_asof, mode, canary_momentum,
                                    weights, holdings, cash, total_value, memo, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                d["rebalance_date"],
                d.get("apply_month"),
                d.get("signal_asof"),
                d.get("mode"),
                d.get("canary_momentum"),
                json.dumps(d.get("weights", {})),
                json.dumps(d.get("holdings", [])),
                d.get("cash", 0),
                d.get("total_value", 0),
                d.get("memo", ""),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        rid = cur.lastrowid
    return jsonify({"id": rid}), 201


@app.patch("/api/records/<int:rid>")
def update_memo(rid):
    memo = request.get_json(force=True).get("memo", "")
    with db() as conn:
        conn.execute("UPDATE records SET memo=? WHERE id=?", (memo, rid))
    return jsonify({"ok": True})


@app.delete("/api/records/<int:rid>")
def delete_record(rid):
    with db() as conn:
        conn.execute("DELETE FROM records WHERE id=?", (rid,))
    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    if HOST not in ("127.0.0.1", "localhost") and not AUTH_PASSWORD:
        print("[경고] 외부 접속이 허용된 상태인데 HAA_PASSWORD 가 비어 있습니다. .env 에 비밀번호를 설정하세요.")
    print(f"HAA 리밸런싱 도우미: http://{HOST}:{PORT}  (DB: {DB_PATH})")
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=4)
    except ImportError:
        app.run(host=HOST, port=PORT, debug=False)
