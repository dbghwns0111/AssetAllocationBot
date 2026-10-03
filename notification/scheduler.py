"""APScheduler 잡 — 월간 신호 알림 / DB 백업.

신호 알림은 "매월 1일 X시" 같은 고정 시각이 아니라 매시 05분에 점검한다:
월말 종가 확정 시각(미국 장 마감)이 서머타임에 따라 한국시간 05~06시로 바뀌고,
서버가 그 시각에 꺼져 있었어도 다음 점검에서 따라잡기 위함. 같은 적용 월은
notify_log 로 한 번만 보낸다.
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from database import notify_repo
from database.connection import backup_database
from notification import message_builder as mb
from strategy import backtest_service, haa, service
from utils.logger import get_logger

_log = get_logger("notification.scheduler")

KIND_SIGNAL = "monthly_signal"


def check_and_notify(notifier, force: bool = False) -> dict:
    """새 확정 신호가 있으면 텔레그램으로 1회 발송. force=True 면 무조건 발송."""
    if not notifier.enabled:
        return {"sent": False, "reason": "텔레그램이 설정되지 않았습니다."}

    now = service.now_ny()
    this_month = f"{now.year:04d}-{now.month:02d}"
    # 이번 달 신호를 이미 보냈고 오늘이 월말 마지막 평일이 아니면 새 신호가 나올 수 없음
    if (not force and notify_repo.was_sent(KIND_SIGNAL, this_month)
            and now.date() != haa.last_weekday(now.year, now.month)):
        return {"sent": False, "reason": "이미 발송함"}

    sig = service.get_signal()
    key = sig["apply_month"]
    if sig["stale"] and not force:
        return {"sent": False, "reason": "가격 데이터가 최신이 아님 (조회 실패)"}
    if not force and notify_repo.was_sent(KIND_SIGNAL, key):
        return {"sent": False, "reason": f"{key} 신호 이미 발송함"}

    ok = notifier.send(mb.build_signal(sig))
    if ok:
        notify_repo.mark_sent(KIND_SIGNAL, key, ",".join(f"{t}:{w}" for t, w in sig["weights"].items()))
        _log.info("월간 신호 발송: %s %s", key, sig["weights"])
    return {"sent": ok, "apply_month": key, "reason": None if ok else "텔레그램 전송 실패"}


class HAAScheduler:
    def __init__(self, cfg: dict, notifier):
        self.cfg = cfg
        self.notifier = notifier
        self.sched = BackgroundScheduler(timezone="Asia/Seoul")
        self.sched.add_job(self._job_signal, "cron", minute=5, id="signal_check",
                           max_instances=1, coalesce=True, misfire_grace_time=600)
        self.sched.add_job(self._job_backup, "cron", hour=4, minute=30, id="db_backup",
                           max_instances=1, coalesce=True, misfire_grace_time=3600)
        # 기본 백테스트 결과 갱신 — 미국 장 마감(한국 05~06시) 이후, 새 달 확정분도 여기서 반영
        self.sched.add_job(backtest_service.refresh_default, "cron", hour=6, minute=40, id="backtest_default",
                           max_instances=1, coalesce=True, misfire_grace_time=3600)

    def _job_signal(self):
        try:
            res = check_and_notify(self.notifier)
            if res.get("sent"):
                _log.info("신호 점검: 발송 %s", res.get("apply_month"))
        except Exception as e:
            _log.exception("신호 점검 실패: %s", e)

    def _job_backup(self):
        try:
            backup_database(self.cfg["database"]["backup_keep"])
        except Exception as e:
            _log.exception("DB 백업 실패: %s", e)
            if self.notifier.enabled:
                self.notifier.send(mb.build_error("DB 백업", e))

    def start(self):
        self.sched.start()
        _log.info("스케줄러 시작")

    def shutdown(self):
        self.sched.shutdown(wait=False)

    def next_runs(self) -> dict:
        out = {}
        for job in self.sched.get_jobs():
            nrt = getattr(job, "next_run_time", None)   # 스케줄러 시작 전 잡에는 속성이 없음
            out[job.id] = nrt.strftime("%Y-%m-%d %H:%M") if nrt else None
        return out
