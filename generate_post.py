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
TOPIC             = os.getenv("POST_TOPIC", "")

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
- SEO 태그: 10~15개 해시태그 (# 없이 문자열만)
- 마무리 요약: 3줄 이내
- 참고 링크 섹션 포함
- 어투: 전문적이고 실무적, 군더더기 없음

## JSON 출력 형식 (이 형식만, 마크다운 코드블록 없이 순수 JSON)
{
  "thumbnail_title": "썸네일 제목 (35자 내외)",
  "title": "포스트 전체 제목 (SEO 최적화)",
  "content_md": "마크다운 본문 전체 (코드블록 포함)",
  "tags": ["태그1", "태그2"],
  "post_type": "tutorial|troubleshooting|devlog|concept|snippet",
  "meta_description": "검색 노출용 메타 설명 (80자 내외)"
}

content_html은 포함하지 마세요. JSON 외 텍스트도 절대 포함하지 마세요.
"""


def markdown_to_html(md: str) -> str:
    """마크다운을 HTML로 변환"""
    try:
        import markdown as md_lib
        return md_lib.markdown(
            md,
            extensions=["fenced_code", "tables", "toc"]
        )
    except ImportError:
        import re
        html = md
        html = re.sub(r"```(\w+)\n(.*?)```", r"<pre><code class='language-\1'>\2</code></pre>", html, flags=re.DOTALL)
        for i in range(6, 0, -1):
            html = re.sub(rf"^{'#'*i} (.+)$", rf"<h{i}>\1</h{i}>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = html.replace("\n\n", "</p><p>")
        return f"<p>{html}</p>"


def _call_api(user_message: str, max_tokens: int) -> str:
    """Claude API 호출 + 잘림 감지"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    if response.stop_reason == "max_tokens":
        raise ValueError(f"응답이 max_tokens({max_tokens})에서 잘림")

    raw = response.content[0].text.strip()

    # 코드블록 래핑 제거
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def generate_post(topic: str) -> dict:
    """Claude API로 블로그 포스트 생성 (content_html은 로컬 변환으로 토큰 절약)"""
    print(f"🤖 Claude API로 포스트 생성 중: '{topic}'")

    user_message = f"""
다음 주제로 티스토리 블로그 포스트를 작성해주세요:

**주제**: {topic}

위 주제를 분석하여 적절한 포스트 타입을 선택하고,
실무에 바로 적용 가능한 포스트를 JSON 형식으로 출력해주세요.

규칙:
- 순수 JSON만 출력 (마크다운 코드블록 래핑 금지)
- content_html 필드 제외 (로컬 변환 처리)
- content_md는 마크다운 전체 본문 (코드블록, 헤딩 포함)
"""

    last_error = None
    for max_tokens in [8000, 6000, 4000]:
        try:
            raw = _call_api(user_message, max_tokens)
            post_data = json.loads(raw)
            break
        except ValueError as e:
            print(f"⚠️ {e} → 재시도...")
            last_error = e
            continue
        except json.JSONDecodeError as e:
            print(f"❌ JSON 파싱 실패 (max_tokens={max_tokens}): {e}")
            print(f"   응답 앞부분: {raw[:200]}")
            last_error = e
            if max_tokens == 4000:
                raise
            continue
    else:
        raise RuntimeError(f"❌ 모든 재시도 실패: {last_error}")

    # content_html 로컬 변환
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
        sys.exit(1)

    post_data = generate_post(topic)
    save_output(post_data)

    print("\n" + "="*50)
    print(f"📌 제목: {post_data['title']}")
    print(f"🖼️  썸네일: {post_data['thumbnail_title']}")
    print(f"🏷️  태그: {', '.join(post_data.get('tags', []))}")
    print(f"📋 타입: {post_data.get('post_type', 'N/A')}")
    print("="*50)
