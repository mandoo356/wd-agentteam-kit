# 위드드림 AI 에이전트팀 — 스타터킷

「에이전트팀 만들기 과정」 수강생용 스타터킷입니다. 프로그램을 내려받아 설치하는 게 아니라, **명령어 한 줄**로 설치합니다.

## 설치 (한 줄)

1. 시작 메뉴에서 **PowerShell** 을 엽니다. (Windows PowerShell / 관리자 권한 필요 없음)
2. 아래 한 줄을 붙여넣고 Enter. (붙여넣기는 **마우스 오른쪽 클릭**)

```powershell
irm https://raw.githubusercontent.com/mandoo356/wd-agentteam-kit/main/install.ps1 | iex
```

## 이 한 줄이 하는 일

| 단계 | 내용 | 걸리는 시간 |
|---|---|---|
| 1 | 깃허브에서 스타터킷을 받는다 (약 3MB, `node_modules`·비밀키 없음) | 수 초 |
| 2 | `C:\Agent\01_KIT\starter-kit` 에 표준 설치한다. `C:\Agent\MyData\` 도 같이 만든다 | 수 초 |
| 3 | 환경점검을 이어서 돌린다 — Node·Git·Python·Claude Code 가 없으면 **명령어(winget/npm)로 설치** | 없는 것에 따라 몇 분 |

기존 설치가 있으면 덮어쓰지 않습니다. 인터넷이 켜져 있어야 합니다.

## 설치 후

- `C:\Agent\01_KIT\starter-kit\README.md` — 폴더 설명과 카드 사용법
- `C:\Agent\MyData\` — **제안서 3개·블로그 글 3개·회사 로고**를 수업 전에 넣어 두는 곳 (`Proposal\` 제안서 · `Blog\` 블로그 · `Logo\` 로고 · `Profile\` 프로필)
- `프롬프트카드.md` — 강의장에서 모듈 0~6 순서대로
- 가상 오피스(`office/`)는 모듈 5에서 `npm ci` 로 의존성을 내려받습니다 (약 690MB, 인터넷 속도에 따라 다름)

## 이 저장소에 없는 것

`.env`(슬랙 열쇠), 로그인 상태, `node_modules`, 캐시·로그는 들어 있지 않습니다. 보안상 정상입니다.

---
위드드림컨설팅 교육용 · `starter-kit/` 원본은 강사 PC에서 `03_깃허브_배포_갱신.bat` 으로 갱신됩니다.
