# HAA 리밸런싱 도우미

Wouter Keller의 **HAA(Hybrid Asset Allocation)** 전략으로 월별 리밸런싱 종목을 확인하고, 실제 매매 내역을 기록하는 웹페이지.

- 카나리아 TIP 모멘텀이 0 이하 → 100% 방어자산 (BIL, IEF 중 모멘텀이 높은 쪽)
- 그 외 → 공격자산 8종(SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT) 중 13612U 모멘텀 상위 4개에 25%씩 (모멘텀 0 이하 종목 몫은 방어자산)
- 13612U 모멘텀 = (1 + 3 + 6 + 12개월 수익률) ÷ 4, 월말 수정종가 기준

## 실행 (Windows)

`run.bat` 더블클릭 → 처음 실행 시 `.venv` 생성 및 패키지 설치 후 브라우저가 열림 (기본 http://127.0.0.1:5000).

필요: Python 3.10 이상, 인터넷 (Yahoo Finance 가격 조회).

## 클라우드 PC(서버) 배포

```bat
git clone <저장소 URL> haa
cd haa
copy .env.example .env
notepad .env
run.bat
```

`.env` 설정:

| 키 | 설명 |
|---|---|
| `HAA_HOST` | `127.0.0.1` = 서버 내부에서만 접속 / `0.0.0.0` = 외부(다른 PC·휴대폰)에서 접속 |
| `HAA_PORT` | 포트 (기본 5000). 자동매매 프로그램과 겹치지 않게 |
| `HAA_USER`, `HAA_PASSWORD` | 비밀번호를 넣으면 접속 시 로그인 요구. **외부 접속 시 반드시 설정** |
| `HAA_DB_PATH` | 기록 DB 경로 (비우면 프로젝트 폴더의 `records.db`) |

외부 접속 시 추가 작업: Windows 방화벽에서 해당 포트 인바운드 허용 + 클라우드 업체 콘솔의 보안그룹/포트포워딩에서 해당 포트 개방.

### 업데이트

1. 실행 중인 서버 창 닫기
2. `update.bat` 실행 (`git pull` + 패키지 갱신)
3. `run.bat` 으로 다시 시작

### 데이터

- 기록은 `records.db`(SQLite) 한 파일에 저장되며 git 에 올라가지 않음. 백업은 이 파일만 복사.
- 로컬 PC와 서버의 기록은 별개. 서버를 기준으로 기록하는 것을 권장.
