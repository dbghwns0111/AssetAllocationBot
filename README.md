# HAA Allocation

Wouter Keller의 **HAA(Hybrid Asset Allocation)** 전략으로 매월 리밸런싱 종목을 확인하고, 실제 매매를 기록하는 웹앱.
클라우드 PC에서 24시간 띄워두고 휴대폰·집 PC에서 **ZeroTier** 로 접속한다. 새 신호는 HAA 전용 텔레그램 봇이 알려준다.

| 화면 | 내용 |
|---|---|
| 이번 달 | 이번 달 모드(공격/혼합/방어), 목표 비중 도넛, 카나리아(TIP) 상태, 지난달 대비 변화, 모멘텀 순위 |
| 리밸런싱 | 보유 수량·현금 입력 → 목표 수량·매수/매도 계산 → 체결 내용 수정 후 기록 저장 |
| 기록 | 내 리밸런싱 타임라인·총자산 추이 / 전략 신호 24개월 이력·누적 수익률 |

## 전략 규칙

- **카나리아** TIP 의 13612U 모멘텀 ≤ 0 → 100% 방어자산
- **공격자산** SPY · IWM · VEA · VWO · VNQ · DBC · IEF · TLT 중 모멘텀 상위 4개에 25%씩 (상위 4개 중 모멘텀 ≤ 0 이면 그 몫은 방어자산)
- **방어자산** BIL · IEF 중 모멘텀이 높은 쪽
- **13612U** = (1 + 3 + 6 + 12개월 수익률) ÷ 4, 월말 수정종가 기준. 미국 장 마감(한국시간 새벽 5~6시) 후 확정

---

## 개발 PC

```bat
run.bat          :: 가상환경 생성 + 실행 + 브라우저 열기 (http://127.0.0.1:5001)
deploy.bat       :: 변경사항 커밋 + GitHub push
```

## 클라우드 PC (처음 한 번)

1. **설치**
   ```bat
   git clone https://github.com/<계정>/<저장소>.git C:\haa-allocation
   cd C:\haa-allocation
   ```
   `install_service.bat` 을 **우클릭 → 관리자로 실행**.
   - `.env` 가 없으면 메모장이 열린다 → `WEB_PASSWORD`, `WEB_SECRET_KEY`, 텔레그램 값 입력 후 저장·닫기
   - 하는 일: `.venv` 생성 + 패키지 설치 → 작업 스케줄러 `HAA-Allocation` 등록 (부팅 시 자동 시작, 죽으면 1분 후 재시작) → 방화벽 TCP 5001 을 ZeroTier 대역(`10.73.56.0/24`)에만 허용 → 시작
2. **접속** — ZeroTier 에 가입된 휴대폰/PC 에서 `http://<클라우드PC ZeroTier IP>:5001`
   - CryptoSplit(5000)과 같은 IP, 포트만 다름. 로그인 쿠키도 분리돼 있어 서로 로그아웃되지 않음
   - 휴대폰은 브라우저 메뉴 → "홈 화면에 추가" 하면 앱처럼 쓸 수 있음

## 클라우드 PC (업데이트)

개발 PC 에서 `deploy.bat` → 클라우드 PC 에서 `update.bat` 을 **관리자로 실행** (git pull + 패키지 갱신 + 서비스 재시작).

## 텔레그램 봇 만들기 (HAA 전용)

1. 텔레그램에서 `@BotFather` → `/newbot` → 이름 정하기 → **토큰** 받기
2. 만든 봇에게 아무 메시지나 보낸 뒤, 브라우저에서 `https://api.telegram.org/bot<토큰>/getUpdates` 열기 → `"chat":{"id": 숫자}` 가 **채팅 ID**
3. 클라우드 PC `.env` 에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 입력 → `update.bat`(관리자) 으로 재시작
4. 웹 → 설정(오른쪽 위 슬라이더 아이콘) → "테스트 메시지"

자동 알림: 매시 05분에 점검해서 새 달 신호가 확정되면 1회 발송. 봇 명령어: `/signal` `/preview` `/momentum` `/last` `/help`

## `.env` 설정

| 키 | 설명 |
|---|---|
| `HAA_HOST` | `0.0.0.0` = ZeroTier 로 외부 접속 허용, `127.0.0.1` = 서버 내부만 |
| `HAA_PORT` | 기본 5001 (CryptoSplit 5000 과 겹치지 않게) |
| `WEB_PASSWORD` | 로그인 비밀번호. 비우면 로그인 없음 — 외부 접속 시 반드시 설정 |
| `WEB_SECRET_KEY` | 세션 서명 키 (비우면 재시작마다 재로그인) |
| `WEB_IP_WHITELIST` | 허용 IP/대역, 쉼표 구분 (예: `10.73.56.0/24`). 127.0.0.1 은 항상 허용 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | HAA 전용 봇 |
| `DB_PATH` | 기록 DB (기본 `data/haa.db`) |

## 데이터

- 기록: `data/haa.db` (SQLite). 시작 시 + 매일 04:30 에 `data/backups/` 로 자동 백업 (14개 유지)
- 로그: `logs/haa.log`
- `data/`, `logs/`, `.env` 는 git 에 올라가지 않음 → `git pull` 해도 서버 기록은 그대로

## 서비스 제거

`uninstall_service.bat` 을 관리자로 실행. 이 프로젝트 `.venv` 로 실행된 프로세스만 종료하므로 CryptoSplit 에는 영향 없음.
> 반대로 CryptoSplit 의 `uninstall_service.bat` 은 모든 `pythonw.exe` 를 종료하므로 HAA 도 함께 꺼진다 (작업 스케줄러가 1분 후 다시 켬).
