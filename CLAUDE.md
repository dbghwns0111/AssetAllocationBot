# CLAUDE.md

HAA(Hybrid Asset Allocation, Keller & Keuning 2023) 월별 리밸런싱 신호 확인 + 매매 기록용 로컬 웹앱.
사용자는 실제로 HAA에 투자 중이며, 이 앱을 클라우드 PC(Windows, 자동매매 프로그램이 이미 돌고 있음)에서 GitHub pull 받아 띄운다.

## 유지보수 규칙

- **코드를 수정할 때마다 이 파일을 함께 최신화한다** (구조, API, 데이터 스키마, 실행/배포 방법, 결정 사항). 배포 절차가 바뀌면 README.md 도 같이 갱신.
- 답변과 UI 문구는 한국어.
- 서버에 영향을 주는 변경(.env 키, requirements, DB 스키마)은 `update.bat` 만으로 반영되도록 유지. DB 스키마 변경 시 기존 `records.db` 를 깨지 않도록 `init_db()` 에서 마이그레이션(ALTER TABLE ADD COLUMN 등) 처리.

## 실행

```bash
.venv/Scripts/python app.py          # 서버 (http://127.0.0.1:5000)
```
- 사용자 PC의 전역 Anaconda 는 numpy 2.x / pandas 2.2 충돌로 pandas import 가 실패함 → 반드시 프로젝트 `.venv` 사용.
- `run.bat`: venv 생성 + `pip install -r requirements.txt` + 브라우저 열기 + 서버 실행.
- `update.bat`: 서버용. `git pull --ff-only` + 패키지 갱신.
- 서버는 waitress 로 실행 (없으면 Flask 개발 서버로 대체).
- .bat 파일은 ASCII 문자만, CRLF 줄바꿈 유지 (`.gitattributes` 에서 강제). 한글 echo 넣지 말 것.

## 구조

| 파일 | 역할 |
|---|---|
| `haa.py` | 전략 계산. yfinance 로 일별 수정종가(5년) 다운로드, 30분 메모리 캐시 |
| `app.py` | Flask 서버, `.env` 로딩, Basic 인증, SQLite 기록 CRUD |
| `static/index.html`, `app.js`, `style.css` | 프레임워크 없는 vanilla JS 단일 페이지 |
| `.env.example` | 설정 템플릿 (`.env` 는 gitignore) |

### 전략 로직 (`haa.py`)
- 유니버스: 카나리아 `TIP`, 공격 `SPY IWM VEA VWO VNQ DBC IEF TLT`, 방어 `BIL IEF`.
- 13612U = (r1 + r3 + r6 + r12) / 4, 월별 데이터는 각 월의 마지막 거래일 종가 (`to_monthly`, 인덱스 = 실제 마지막 거래일).
- TIP 모멘텀 ≤ 0 → 방어자산 100%. 아니면 공격 상위 4개 25%씩, 그 중 모멘텀 ≤ 0 은 방어자산으로 대체 (같은 종목 비중 합산).
- 방어자산 = BIL/IEF 중 모멘텀 높은 쪽.
- mode: `offensive`(상위 4개 모두 양수) / `mixed`(일부 방어) / `defensive`(카나리아 음수).
- 기본은 직전 **완료된** 월말 신호. `partial=1` 이면 진행 중인 당월 최신가로 미리보기 (UI 에 "미확정" 표시).
- `signal_history`: 과거 월별 신호 + 다음 달 전략 수익률(수수료·세금 제외).

### API (`app.py`)
- `GET /api/signal?partial=1&refresh=1` — 신호, 모멘텀 표, 최신가(`prices`)
- `GET /api/history?months=24`
- `GET/POST /api/records`, `PATCH /api/records/<id>` (memo 만), `DELETE /api/records/<id>`
- 오류 시 `{"error": ...}` + 4xx/5xx, 프론트는 상단 빨간 박스로 표시.

### 설정 (`.env`, 환경변수가 우선)
`HAA_HOST`(기본 127.0.0.1), `HAA_PORT`(5000), `HAA_USER`(admin), `HAA_PASSWORD`(비어 있으면 인증 없음), `HAA_DB_PATH`(기본 ./records.db).
외부 바인딩인데 비밀번호가 없으면 시작 시 경고 출력.

### DB (`records.db`, SQLite, gitignore)
`records(id, rebalance_date, apply_month, signal_asof, mode, canary_momentum, weights JSON, holdings JSON, cash, total_value, memo, created_at)`
- `holdings`: `[{ticker, shares, price(체결가), value, weight}]` — 체결 **후** 보유 상태.
- 계산기는 가장 최근 기록(rebalance_date 내림차순)의 holdings/cash 로 현재 보유를 미리 채움.

### 프론트 (`static/app.js`)
- 계산기: 현재 보유 + 현금 + 입출금 → 총자산 × 목표비중 ÷ 현재가 = 목표 수량 (정수 내림, 소수점 매매 옵션 시 소수 4자리 내림).
- "체결 후 보유"·"체결가"는 사용자가 수정 가능 (`state.edited` 로 수동 수정 여부 추적). 잔여 현금 = 현금 + 입출금 + Σ(현재 − 체결 후) × 체결가.
- 색상: 한국식 (상승 빨강 `--pos`, 하락 파랑 `--neg`), 다크모드 지원.
- 금액 단위 USD (미국 상장 ETF 기준).

## 검증

테스트 스위트는 없음. 변경 후 Flask test client 로 확인:
```bash
.venv/Scripts/python -c "import app; c=app.app.test_client(); print(c.get('/api/signal').get_json()['weights'])"
node --check static/app.js
```
