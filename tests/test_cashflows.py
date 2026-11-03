"""입출금 기록 API 테스트 — 임시 DB 로 저장·검증·삭제와 리밸런싱 저장 시 입출금 연동을 확인한다."""

import pytest

from database import connection, models
from web.app import create_app

CFG = {"web": {"host": "127.0.0.1", "port": 0, "password": "", "secret_key": "test",
               "ip_whitelist": [], "session_days": 30}}


@pytest.fixture()
def client(tmp_path):
    connection.configure(str(tmp_path / "t.db"))
    models.create_tables()
    return create_app(CFG).test_client()


def test_cashflow_crud(client):
    r = client.post("/api/cashflows", json={"flow_date": "2026-10-25", "amount": 1500, "memo": "10월 월급"})
    assert r.status_code == 201 and r.get_json()["message"] == "입금 기록을 저장했습니다."
    r = client.post("/api/cashflows", json={"flow_date": "2026-10-28", "amount": -200.456})
    assert r.get_json()["message"] == "출금 기록을 저장했습니다."
    flows = client.get("/api/cashflows").get_json()
    assert [f["amount"] for f in flows] == [-200.46, 1500.0]          # 날짜 내림차순, 센트 반올림
    assert flows[1]["memo"] == "10월 월급" and flows[1]["source"] == "manual"
    assert client.delete(f"/api/cashflows/{flows[0]['id']}").status_code == 200
    assert client.delete(f"/api/cashflows/{flows[0]['id']}").status_code == 404
    assert len(client.get("/api/cashflows").get_json()) == 1


@pytest.mark.parametrize("body", [
    {"flow_date": "2026-13-01", "amount": 100},
    {"flow_date": "2026-10-01", "amount": 0},
    {"flow_date": "2026-10-01", "amount": "abc"},
    {"amount": 100},
])
def test_cashflow_validation(client, body):
    r = client.post("/api/cashflows", json=body)
    assert r.status_code == 400 and r.get_json()["ok"] is False


def test_record_deposit_creates_cashflow(client):
    rec = {"rebalance_date": "2026-11-03", "holdings": [{"ticker": "SPYM", "shares": 10, "price": 90}], "cash": 50}
    assert client.post("/api/records", json={**rec, "deposit": 300}).status_code == 201
    flows = client.get("/api/cashflows").get_json()
    assert len(flows) == 1 and flows[0]["amount"] == 300 and flows[0]["flow_date"] == "2026-11-03"
    assert flows[0]["source"] == "rebalance"
    # 입금 칸이 기존 입출금 기록과 같으면(추가분 0) 새로 만들지 않음
    assert client.post("/api/records", json={**rec, "deposit": 0}).status_code == 201
    assert len(client.get("/api/cashflows").get_json()) == 1
