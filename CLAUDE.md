# CLAUDE.md

HAA(Hybrid Asset Allocation, Keller & Keuning 2023) 월간 리밸런싱 신호 확인 + 매매 기록 웹앱.
사용자는 실제로 HAA 에 투자 중이다. 개발 PC → GitHub push → 클라우드 PC pull 로 배포하고, 휴대폰·집 PC 에서 ZeroTier 로 접속한다.

## 유지보수 규칙

- **코드를 수정할 때마다 이 파일을 함께 최신화한다** (구조, API, 스키마, 실행/배포, 결정 사항). 배포·접속 절차가 바뀌면 README.md 도 갱신.
- 답변·UI·로그·텔레그램 문구는 한국어.
- 커밋: `feat:` / `fix:` / `docs:` / `refactor:` / `style:` 접두사 + 한국어 요약 한 줄, 본문에 원인·변경·검증. **커밋 후 push 까지** (원격 설정 후).
- 서버에 영향을 주는 변경(.env 키, requirements, DB 스키마)은 `update.bat` 만으로 반영돼야 한다. 스키마 변경은 `database/models.py` 에서 `CREATE TABLE IF NOT EXISTS` / `_add_column()` 으로만 (기존 `data/haa.db` 를 깨지 말 것).
- 의존성은 **순수 Python 패키지만**. numpy/pandas/yfinance(curl_cffi) 금지 — 운영 서버가 Windows Server 2012 R2 라 네이티브 휠 설치가 보장되지 않는다. 그래서 가격은 `market/prices.py` 가 Yahoo v8 chart API 를 requests 로 직접 호출한다.
- 서버 Python 은 **3.13** (개발 PC .venv 는 3.12). 코드는 3.9 이상 호환으로 유지. requirements 의 네이티브 확장은 markupsafe·charset_normalizer 뿐이며 cp313 win_amd64 휠 존재 확인함 (2026-10-03).
- 원격 저장소: https://github.com/dbghwns0111/AssetAllocationBot (브랜치 `main`).

## 운영 환경 (crypto-split-bot 과 같은 서버)

- 몽클라우드 클라우드 PC, Windows Server 2012 R2, PowerShell 4.0. CryptoSplit 자동매매 봇이 **포트 5000** 에서 이미 구동 중 → HAA 는 **5001**.
- 외부 접속: 인바운드 포트 개방 불가 → ZeroTier 가상망 `10.73.56.0/24`. 방화벽 규칙은 그 대역만 허용 (`install_service.ps1`).
- 상시 구동: 작업 스케줄러 `HAA-Allocation` (SYSTEM, 부팅 30초 후, 실패 시 1분 후 재시작) → `run_service.bat`(설치 시 생성, gitignore) → `.venv\Scripts\pythonw.exe main.py`.
- 봇과 환경 분리: HAA 는 자체 `.venv`. 텔레그램도 **HAA 전용 봇** (CryptoSplit 봇 채널 사용 금지 — 사용자 요청). 세션 쿠키 이름 `haa_session` (같은 IP 의 5000 번 쿠키와 충돌 방지).
- HAA 스크립트는 프로세스를 이름이 아니라 **이 프로젝트 `.venv` 경로**로 골라 종료한다 (CryptoSplit 을 죽이지 않도록).
- 웹 UI 는 CryptoSplit 과 **다른 독자 디자인**이다 (사용자 요청: 서버/배포/접속 방식만 참고, 화면 구조·스타일은 따라하지 말 것).

## 실행 / 검증

```bash
.venv/Scripts/python main.py                 # http://127.0.0.1:5001 (.env 없을 때)
.venv/Scripts/python -m pytest -q            # 전략 로직 테스트 (tests/test_haa.py)
node --check web/static/js/app.js
```
- 사용자 PC 의 전역 Anaconda 는 numpy/pandas ABI 충돌로 깨져 있음 → 반드시 `.venv`.
- 화면 확인: 임시 DB 로 별도 포트에 띄우고 헤드리스 Chrome 으로 캡처 (`DB_PATH=<temp> HAA_PORT=5099`). 폭 1920/1440/1366/1024 와 모바일을 모두 확인. 헤드리스 창은 최소 폭이 ~500px 라 모바일은 390px iframe 으로 감싸서 찍는다. 하위 탭은 `#records/history` 로 바로 연다.
- Windows bash 의 curl 로 한글 JSON 을 보내면 인코딩이 깨져 400 이 난다 — API 테스트는 Python requests/test_client 로.

## 구조

```
main.py                      진입점: .env → 로깅 → DB(마이그레이션·무결성·백업) → 포트 바인딩 → 스케줄러/텔레그램 → waitress
config/loader.py             .env → cfg dict (싱글턴)
market/prices.py             Yahoo chart API 일별 수정종가, 30분 캐시, 실패 시 이전 캐시(stale=True)
strategy/haa.py              순수 함수: 월말표, 13612U, allocate, 월말 확정 판정, 신호/이력
strategy/service.py          가격 조회 + 뉴욕 현재시각 주입
database/                    connection(WAL, 백업, 무결성) · models(DDL) · record_repo · auth_repo · notify_repo
notification/telegram.py     HAA 전용 봇 클라이언트 (HTML 전송, 400 이면 평문 재전송)
notification/message_builder.py  모든 메시지는 card() 경유 (이스케이프 일원화, <pre> 폭 36칸)
notification/scheduler.py    APScheduler: 매시 05분 신호 점검(check_and_notify), 04:30 DB 백업
notification/telegram_handler.py  long-polling 명령어 (/signal /preview /momentum /last /help), 설정된 chat_id 만 응답
web/app.py · auth.py         Flask 팩토리, 로그인/CSRF/IP 화이트리스트/브루트포스(5회→10분 잠금)
web/routes/api.py            REST API
web/templates/index.html     단일 페이지 (뷰 3개 + 설정 시트 + 다이얼로그)
web/static/js/app.js         프론트 로직 (프레임워크 없음), Chart.js 4.4.1 로컬 번들
web/static/css/app.css       디자인 토큰 + 컴포넌트
scripts/*.ps1 + 루트 *.bat   install_service / uninstall_service / update / deploy (bat 은 ps1 을 UTF-8 로 읽어 실행)
```

### 전략 로직 (`strategy/haa.py`)
- 유니버스: 카나리아 `TIP`, 공격 `SPY IWM VEA VWO VNQ DBC IEF TLT`, 방어 `BIL IEF`. 매매 대상 `TRADABLE` = 공격 + BIL.
- 월 달력은 SPY 기준, 각 월 마지막 거래일 종가. 13612U = (r1+r3+r6+r12)/4.
- TIP ≤ 0 → 방어 100%. 아니면 공격 상위 4개 25%씩, 그중 ≤ 0 은 방어자산으로 (같은 종목 비중 합산). 방어자산 = BIL/IEF 중 모멘텀 높은 쪽.
- mode: `offensive` / `mixed` / `defensive`.
- **월말 확정 판정** `month_complete()` (뉴욕 시각 기준): 뉴욕 날짜가 다음 달이면 확정. 같은 달이면 데이터가 그 달 마지막 평일이고 16:15 이후일 때만 확정. 휴장으로 끝나는 달은 다음 달 0시에 확정.
- 기본은 직전 확정 월 신호, `partial=1` 이면 진행 중인 달 최신가로 미리보기.
- `compute_signal` 은 지난달 신호(`prev`)와 편입/제외(`added`/`removed`)도 반환.
- **BIL → 현금 (사용자 운용 방식)**: 신호에는 BIL 그대로 표시하되 사용자는 BIL 을 사지 않고 같은 비중을 달러 현금으로 보유한다. `haa.CASH_PROXY = "BIL"`, 신호 응답에 `cash_proxy`, `cash_weight` 포함. 계산기는 `buyWeight()` 로 BIL 목표를 0 으로 두고 현금 카드에 목표 현금 표시(보유 BIL 은 매도로 표시). 텔레그램 메시지에 "→ 현금" 과 안내 문구. 신호 이력 수익률은 전략 그대로 BIL 수익률로 계산(현금 이자와 차이 있음).

### 텔레그램 신호 알림 (`notification/scheduler.py::check_and_notify`)
- 매시 05분 점검. 이번 뉴욕 월 신호를 이미 보냈고 오늘이 월말 마지막 평일이 아니면 가격 조회 없이 건너뜀.
- 신호의 `apply_month` 를 키로 `notify_log` 에 기록 → 같은 달 중복 발송 없음, 재시작에도 유지. stale 데이터면 발송 안 함.
- 첫 설치가 월 중간이면 그 달 신호가 한 번 발송된다 (의도).

### API
```
GET    /api/signal?partial=1&refresh=1   신호 + 모멘텀 + 최신가 + prev/added/removed + fetched_at/stale
GET    /api/history?months=24            월별 신호 + 그 달 전략 수익률(return, return_partial)
GET    /api/records                      리밸런싱 기록 (rebalance_date DESC)
POST   /api/records                      저장 (서버에서 검증·total/weight 재계산)
PATCH  /api/records/<id>                 메모 수정
DELETE /api/records/<id>
GET    /api/system                       텔레그램 상태, 마지막 신호 발송, 다음 점검 시각
POST   /api/telegram/test | /api/telegram/signal
```
오류는 `{"ok": false, "error": "..."}`. 로그인 활성 시 POST/PATCH/DELETE 는 `X-CSRF-Token` 필수 (프론트 `api()` 가 자동 부여).

### DB (`data/haa.db`)
- `records(id, rebalance_date, apply_month, signal_asof, mode, canary_momentum, weights JSON, holdings JSON, cash, total_value, memo, created_at)` — holdings = 체결 **후** `[{ticker, shares, price, value, weight}]`
- `login_attempts(ip PK, fail_count, window_start, locked_until, updated_at)`
- `notify_log(kind, key, detail, sent_at, PK(kind,key))`

### 프론트 (`web/static/js/app.js`, `css/app.css`)
- 화면: `#signal` / `#rebalance` / `#records/mine|history` (해시 라우팅). PC 는 앱바 세그먼트 탭, 720px 이하는 하단 플로팅 탭바. 설정은 오른쪽 시트.
- **전체 폭 반응형** (사용자 요청: 가운데 좁은 세로형 금지): `main` 폭 제한 없음, 여백 `--gutter`=clamp. 각 화면은 `.layout` + `grid-template-areas` 로 폭 구간별 재배치
  - 이번 달 `.sig-layout`: ≤720 1단 / 721+ 2단 / 1200+ 3단 / 1600+ 4단(모멘텀 막대 + 기간별 수익률 표를 나란히, 토글 숨김)
  - 리밸런싱 `.rb-layout`: 1100+ 본문 + 오른쪽 sticky 요약 (`grid-template-rows: auto 1fr`), 주문 카드는 auto-fill(최소 330px)
  - 기록 `.rec-layout`: 1100+ 차트(sticky) + 타임라인 / `.hist-layout`: 1500+ 차트 + 표
  - 카드 내부(도넛 범례, 모멘텀 행, 주문)는 `container-type: inline-size` 컨테이너 쿼리로 카드 폭 기준 반응
  - 배치용 `a-*` 클래스를 JS 가 지우지 않게 할 것 (히어로는 `classList` 로 mode 클래스만 교체)
- 히어로 하단 요약: 이번 달 리밸런싱 기록 여부 / 다음 신호 확정일(그 달 마지막 평일) / 마지막 리밸런싱.
- 라이트/다크: OS 설정 + 수동 토글(`data-theme`, localStorage `haa-theme`). 차트는 테마 변경 시 다시 그림.
- 색 규칙: 등락·매매는 한국식 (상승·매수 = 빨강 `--up`, 하락·매도 = 파랑 `--down`). 종목 색은 종목에 고정 (`--t-SPY` …, dataviz 검증 8색 + BIL 회색). 수치 텍스트는 잉크색 + ▲▼ 로 방향 표시.
- 계산기: 총자산 = Σ현재보유×현재가 + 현금 + 입출금. 목표 수량 = floor(총자산×비중÷현재가) (소수점 매매 시 4자리). "체결 후"를 직접 고치면 `S.rb.edited` 로 고정. 잔여 현금 = 현금 + 입출금 + 매도액 − 매수액 (체결가 기준).
- 직전 기록의 holdings/cash 로 계산기를 미리 채움.
