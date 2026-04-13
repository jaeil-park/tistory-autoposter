# 🤖 Tistory Auto-Poster

Claude API + Playwright + GitHub Actions로 티스토리 블로그 완전 자동화

## 📐 아키텍처

```
GitHub Actions (수동 / 스케줄)
        ↓
generate_post.py    →  Claude API로 포스트 자동 생성
        ↓
tistory_poster.py   →  Playwright 카카오 로그인 → 티스토리 발행
        ↓
Discord Webhook     →  완료/실패 알림
```

## 🚀 셋업 가이드

### 1단계: Repository Secrets 등록

`GitHub Repository → Settings → Secrets and variables → Actions → New repository secret`

| Secret 이름          | 값                              |
|---------------------|--------------------------------|
| `ANTHROPIC_API_KEY` | Claude API 키                   |
| `KAKAO_EMAIL`       | 카카오 계정 이메일               |
| `KAKAO_PASSWORD`    | 카카오 계정 비밀번호             |
| `TISTORY_BLOG`      | 블로그명 (xxx.tistory.com → xxx) |
| `DISCORD_WEBHOOK`   | Discord Webhook URL (선택)      |

### 2단계: Repository Variables 등록

`Settings → Secrets and variables → Variables → New repository variable`

| Variable 이름    | 값 예시                              |
|----------------|-------------------------------------|
| `DEFAULT_TOPIC` | `Python 자동화 최신 트렌드 정리 2026` |

### 3단계: 로컬 테스트 (선택)

```bash
# 의존성 설치
pip install -r requirements.txt
playwright install chromium

# .env 파일 생성
cp .env.example .env
# .env 파일 편집 후:

# 포스트 생성 단독 테스트
python generate_post.py "LangChain FAISS 벡터 검색 구현"

# 전체 파이프라인 테스트
python run.py "LangChain FAISS 벡터 검색 구현"
```

### 4단계: GitHub Actions 실행

**수동 실행:**
`Actions → 🤖 Tistory Auto-Poster → Run workflow → 주제 입력 → Run`

**자동 실행:**
매주 월·수·금 오전 9시 KST에 `DEFAULT_TOPIC`으로 자동 발행

## 📁 파일 구조

```
tistory-autoposter/
├── .github/
│   └── workflows/
│       └── auto-post.yml    # GitHub Actions 워크플로우
├── generate_post.py         # Claude API 포스트 생성
├── tistory_poster.py        # Playwright 티스토리 발행
├── run.py                   # 메인 실행 스크립트
├── requirements.txt         # Python 의존성
├── .env.example             # 환경변수 템플릿
└── README.md
```

## ⚠️ 주의사항

- `.env` 파일은 절대 커밋하지 마세요 (`.gitignore`에 추가)
- 티스토리 UI가 변경될 경우 `tistory_poster.py`의 CSS 셀렉터 수정 필요
- GitHub Actions 무료 플랜: 월 2,000분 제공 (포스팅 1회 약 3~5분 소요)

## 🔧 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 로그인 실패 | 카카오 2FA 활성화 | 카카오 계정 보안 설정에서 자동화 환경 예외 처리 |
| 에디터 입력 실패 | 티스토리 UI 업데이트 | `error_screenshot.png` 확인 후 셀렉터 수정 |
| Claude API 오류 | API 키 만료/한도 초과 | Anthropic 콘솔에서 확인 |
