"""
generate_post.py
Claude API로 블로그 포스트 + 카테고리 자동 결정
"""

import os
import json
import sys
import anthropic
from datetime import datetime

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TOPIC             = os.getenv("POST_TOPIC", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── 카테고리 매핑 (Notion 태그 + 티스토리 카테고리 ID) ──────────────
# 티스토리 카테고리 ID는 관리자 > 카테고리에서 확인 가능
# Notion 태그는 자동 분류용
CATEGORY_MAP = {
    "python":       {"notion_tag": "🐍 Python/개발",    "tistory_id": "0"},
    "langchain":    {"notion_tag": "🤖 AI/LangChain",   "tistory_id": "0"},
    "discord":      {"notion_tag": "💬 Discord봇",      "tistory_id": "0"},
    "infra":        {"notion_tag": "🖥️ IT인프라",       "tistory_id": "0"},
    "quant":        {"notion_tag": "📈 퀀트/자동화",    "tistory_id": "0"},
    "linux":        {"notion_tag": "🐧 Linux/Server",   "tistory_id": "0"},
    "vmware":       {"notion_tag": "🖥️ IT인프라",       "tistory_id": "0"},
    "docker":       {"notion_tag": "🐳 Docker/DevOps",  "tistory_id": "0"},
    "fastapi":      {"notion_tag": "⚡ FastAPI/백엔드", "tistory_id": "0"},
    "vue":          {"notion_tag": "🎨 Frontend",       "tistory_id": "0"},
    "general":      {"notion_tag": "📝 일반",           "tistory_id": "0"},
}


SYSTEM_PROMPT = """
당신은 베테랑 IT 엔지니어 재일(jaeil.park)의 티스토리 블로그 포스트 작성 전문가입니다.

## 작성자 프로필
- Dell/HPE 서버, Brocade SAN, VMware, Proxmox 전문 IT 인프라 엔지니어
- Python, LangChain, Discord API, FastAPI, Vue.js 개발자
- 주요 프로젝트: Discord 업무이력 챗봇, Op-26M 퀀트봇, InfraView DCIM
- 독자층: IT 엔지니어, 개발자 (비기너 아님)

## 카테고리 분류 기준
주제를 분석해서 아래 중 가장 적합한 카테고리 키를 선택하세요:
- python: Python 개발, 스크립트, 라이브러리
- langchain: LangChain, AI, LLM, 벡터DB, RAG
- discord: Discord 봇, Discord API
- infra: 서버, 스토리지, SAN, VMware, Proxmox, 네트워크 장비
- quant: 퀀트, 자동화 봇, 업비트, 트레이딩
- linux: Linux, Ubuntu, Rocky, CentOS, 쉘 스크립트
- vmware: VMware, ESXi, vSphere, Proxmox
- docker: Docker, Kubernetes, DevOps, CI/CD
- fastapi: FastAPI, REST API, 백엔드
- vue: Vue.js, 프론트엔드, UI
- general: 위 어디에도 해당 없음

## 포스트 타입
1. 트러블슈팅: 에러/장애 → 원인파악 → 원인분석 → 조치방안 → 결과
2. 튜토리얼: 설치/구축 → Step-by-step + 코드블록
3. 개발 로그: 구현기 → 배경 → 문제 → 구현 → 결과
4. 개념 정리: 비교/리뷰 → 비교표 → 딥다이브 → 요약
5. 코드 스니펫: 핵심 코드 중심

## 출력 형식 (순수 JSON만, 마크다운 코드블록 없이)
{
  "category_key": "카테고리 키 (위 목록 중 하나)",
  "thumbnail_title": "썸네일 제목 (35자 내외, SEO 최적화)",
  "title": "포스트 전체 제목",
  "content_md": "마크다운 본문 전체",
  "tags": ["태그1", "태그2", ...],
  "post_type": "tutorial|troubleshooting|devlog|concept|snippet",
  "meta_description": "메타 설명 (80자 내외)"
}
"""


def markdown_to_html(md: str) -> str:
    try:
        import markdown as md_lib
        return md_lib.markdown(md, extensions=["fenced_code", "tables", "toc"])
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
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )
    if response.stop_reason == "max_tokens":
        raise ValueError(f"응답이 max_tokens({max_tokens})에서 잘림")
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def generate_post(topic: str) -> dict:
    print(f"🤖 Claude API로 포스트 생성 중: '{topic}'")

    user_message = f"""
다음 주제로 티스토리 블로그 포스트를 작성해주세요:

**주제**: {topic}

주제를 분석하여:
1. 가장 적합한 category_key를 선택하세요
2. 적절한 포스트 타입을 선택하세요
3. 실무에 바로 적용 가능한 포스트를 작성하세요

순수 JSON만 출력하세요. content_html 필드는 제외하세요.
"""

    last_error = None
    post_data = None
    for max_tokens in [8000, 6000, 4000]:
        try:
            raw = _call_api(user_message, max_tokens)
            post_data = json.loads(raw)
            break
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  ⚠️ 재시도 (max_tokens={max_tokens}): {e}")
            last_error = e
            continue
    else:
        raise RuntimeError(f"❌ 포스트 생성 실패: {last_error}")

    # 카테고리 키 검증 및 매핑
    category_key = post_data.get("category_key", "general")
    if category_key not in CATEGORY_MAP:
        category_key = "general"

    category_info = CATEGORY_MAP[category_key]
    post_data["category_key"]     = category_key
    post_data["notion_tag"]       = category_info["notion_tag"]
    post_data["tistory_category_id"] = category_info["tistory_id"]
    post_data["content_html"]     = markdown_to_html(post_data.get("content_md", ""))

    print(f"✅ 포스트 생성 완료: {post_data['title']}")
    print(f"   📂 카테고리: {category_key} → {category_info['notion_tag']}")
    return post_data


def save_output(post_data: dict, output_path: str = "post_output.json"):
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
    print(f"📂 카테고리: {post_data['notion_tag']}")
    print(f"🏷️  태그: {', '.join(post_data.get('tags', []))}")
    print("="*50)
