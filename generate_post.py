"""
generate_post.py
Claude API를 사용해 티스토리 블로그 포스트를 자동 생성하는 스크립트
출력: post_output.json (title, content_html, tags, thumbnail_title)
"""

import os
import json
import sys
import anthropic
from datetime import datetime

# ── 환경변수 ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TOPIC             = os.getenv("POST_TOPIC", "")       # GitHub Actions input으로 받음

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


SYSTEM_PROMPT = """
당신은 베테랑 IT 엔지니어이자 개발자인 재일(jaeil.park)의 티스토리 블로그 포스트 작성 전문가입니다.

## 작성자 프로필
- Dell/HPE 서버, Brocade SAN, VMware, Proxmox 전문 IT 인프라 엔지니어
- Python, LangChain, Discord API, FastAPI, Vue.js 개발자
- 주요 프로젝트: Discord 업무이력 챗봇, Op-26M 퀀트봇, InfraView DCIM
- 블로그 독자층: IT 엔지니어, 개발자 (비기너 아님)

## 포스트 타입 분류 (자동 감지)
1. 트러블슈팅: 에러/장애 → [원인파악] → [원인분석] → [조치방안] → [결과]
2. 튜토리얼: 설치/구축 방법 → Step-by-step + 코드블록
3. 개발 로그: 프로젝트 구현기 → 배경 → 문제 → 구현 → 결과
4. 개념 정리: 비교/리뷰 → 비교표 → 딥다이브 → 요약
5. 코드 스니펫: 핵심 코드 공유 → 코드 중심 + 설명

## 출력 규칙 (반드시 준수)
- 마크다운 형식 (티스토리 HTML 모드용)
- 코드블록: ```언어명 + 상세 주석 포함
- 썸네일 제목: 30~45자, SEO 최적화
- SEO 태그: 10~15개 #해시태그
- 마무리 요약: 3줄 이내
- 참고 링크 섹션 포함
- 어투: 전문적이고 실무적, 군더더기 없음

## JSON 출력 형식 (반드시 이 형식만 출력, 마크다운 코드블록 없이)
{
  "thumbnail_title": "썸네일 제목 (35자 내외)",
  "title": "포스트 전체 제목 (SEO 최적화)",
  "content_md": "마크다운 본문 전체",
  "content_html": "<p>HTML 변환된 본문</p>",
  "tags": ["태그1", "태그2", ...],
  "post_type": "tutorial|troubleshooting|devlog|concept|snippet",
  "meta_description": "검색 노출용 메타 설명 (80자 내외)"
}
"""


def markdown_to_html(md: str) -> str:
    """마크다운을 HTML로 변환 (markdown 라이브러리 사용)"""
    try:
        import markdown
        return markdown.markdown(
            md,
            extensions=["fenced_code", "tables", "codehilite", "toc"]
        )
    except ImportError:
        # fallback: 기본 변환
        html = md
        # 코드블록
        import re
        html = re.sub(r"```(\w+)\n(.*?)```", r"<pre><code class='language-\1'>\2</code></pre>", html, flags=re.DOTALL)
        # 헤딩
        for i in range(6, 0, -1):
            html = re.sub(rf"^{'#'*i} (.+)$", rf"<h{i}>\1</h{i}>", html, flags=re.MULTILINE)
        # 굵게
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        # 줄바꿈
        html = html.replace("\n\n", "</p><p>")
        return f"<p>{html}</p>"


def generate_post(topic: str) -> dict:
    """Claude API로 블로그 포스트 생성"""
    print(f"🤖 Claude API로 포스트 생성 중: '{topic}'")

    user_message = f"""
다음 주제로 티스토리 블로그 포스트를 작성해주세요:

**주제**: {topic}

위 주제를 분석하여 적절한 포스트 타입을 선택하고, 
실무에 바로 적용 가능한 포스트를 JSON 형식으로 출력해주세요.
JSON만 출력하고, 다른 텍스트는 절대 포함하지 마세요.
content_html은 content_md를 HTML로 변환한 결과입니다.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = response.content[0].text.strip()

    # JSON 파싱 (혹시 코드블록으로 감싸진 경우 제거)
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    post_data = json.loads(raw)

    # content_html이 없거나 빈 경우 content_md에서 변환
    if not post_data.get("content_html"):
        post_data["content_html"] = markdown_to_html(post_data.get("content_md", ""))

    print(f"✅ 포스트 생성 완료: {post_data['title']}")
    return post_data


def save_output(post_data: dict, output_path: str = "post_output.json"):
    """생성된 포스트를 JSON 파일로 저장"""
    post_data["generated_at"] = datetime.now().isoformat()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(post_data, f, ensure_ascii=False, indent=2)
    print(f"💾 포스트 저장 완료: {output_path}")


if __name__ == "__main__":
    topic = TOPIC or (sys.argv[1] if len(sys.argv) > 1 else None)

    if not topic:
        print("❌ 주제를 입력해주세요.")
        print("사용법: python generate_post.py '주제' 또는 POST_TOPIC 환경변수 설정")
        sys.exit(1)

    post_data = generate_post(topic)
    save_output(post_data)

    # 요약 출력 (GitHub Actions 로그용)
    print("\n" + "="*50)
    print(f"📌 제목: {post_data['title']}")
    print(f"🖼️  썸네일: {post_data['thumbnail_title']}")
    print(f"🏷️  태그: {', '.join(post_data.get('tags', []))}")
    print(f"📋 타입: {post_data.get('post_type', 'N/A')}")
    print("="*50)
