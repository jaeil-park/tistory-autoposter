"""
tistory_poster.py - v13
Notion 저장 + HTML 코드블록 토글 포함
티스토리 HTML 모드에 바로 복붙 가능
"""

import os
import re
import json
import requests

NOTION_TOKEN    = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID  = os.environ["NOTION_PAGE_ID"]
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")


def notify_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=5)
    except Exception:
        pass


def post_to_tistory(title: str, content_html: str, tags: list, category_id: str = "0") -> str:
    post_data = {}
    try:
        with open("post_output.json", "r", encoding="utf-8") as f:
            post_data = json.load(f)
    except Exception:
        pass

    return post_to_notion(
        title           = title,
        content_md      = post_data.get("content_md", ""),
        content_html    = post_data.get("content_html", content_html),
        tags            = tags,
        thumbnail_title = post_data.get("thumbnail_title", ""),
        notion_tag      = post_data.get("notion_tag", "📝 일반"),
        category_key    = post_data.get("category_key", "general"),
        meta_desc       = post_data.get("meta_description", ""),
        post_type       = post_data.get("post_type", ""),
    )


def post_to_notion(title, content_md, content_html, tags,
                   thumbnail_title="", notion_tag="📝 일반",
                   category_key="general", meta_desc="", post_type="") -> str:

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    blocks = []

    # ── 1. 메타 정보 Callout ─────────────────────────────────
    meta_lines = []
    if thumbnail_title:
        meta_lines.append(f"🖼️ 썸네일: {thumbnail_title}")
    if notion_tag:
        meta_lines.append(f"📂 카테고리: {notion_tag}")
    if post_type:
        meta_lines.append(f"📋 타입: {post_type}")
    if tags:
        meta_lines.append(f"🏷️ 태그: {' '.join(['#'+t for t in tags[:10]])}")
    if meta_desc:
        meta_lines.append(f"🔍 메타: {meta_desc}")

    if meta_lines:
        blocks.append({
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": "\n".join(meta_lines)}}],
                "icon": {"emoji": "📋"}, "color": "blue_background"
            }
        })

    # ── 2. 티스토리 HTML 복붙용 토글 ────────────────────────
    # HTML을 2000자 단위로 청크 분할 (Notion 블록 제한)
    html_chunks = []
    chunk_size = 1900
    html_clean = content_html.replace("\n", " ")
    for i in range(0, len(html_clean), chunk_size):
        html_chunks.append(html_clean[i:i+chunk_size])

    # 토글 블록 안에 코드 청크 넣기
    toggle_children = []
    for idx, chunk in enumerate(html_chunks[:20]):  # 최대 20청크
        toggle_children.append({
            "object": "block", "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}],
                "language": "html"
            }
        })

    blocks.append({
        "object": "block", "type": "toggle",
        "toggle": {
            "rich_text": [{"type": "text", "text": {
                "content": "📋 티스토리 HTML 복붙용 코드 (클릭해서 열기)"
            }}],
            "color": "green_background",
            "children": toggle_children
        }
    })

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # ── 3. 본문 마크다운 블록 ────────────────────────────────
    supported_langs = {
        "python", "javascript", "typescript", "bash", "shell",
        "json", "yaml", "sql", "html", "css", "java", "go",
        "rust", "kotlin", "swift", "c", "cpp", "plain text"
    }

    lines = content_md.split('\n')
    i = 0
    code_buffer = []
    in_code = False
    code_lang = ""

    while i < len(lines) and len(blocks) < 95:
        line = lines[i]

        if line.startswith('```'):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip() or "plain text"
                code_buffer = []
            else:
                blocks.append({
                    "object": "block", "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {
                            "content": '\n'.join(code_buffer)[:1900]
                        }}],
                        "language": code_lang if code_lang in supported_langs else "plain text"
                    }
                })
                in_code = False
                code_buffer = []
            i += 1
            continue

        if in_code:
            code_buffer.append(line)
            i += 1
            continue

        stripped = line.strip()
        if line.startswith('### '):
            blocks.append({"object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]}})
        elif line.startswith('## '):
            blocks.append({"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]}})
        elif line.startswith('# '):
            blocks.append({"object": "block", "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]}})
        elif stripped == '---':
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif stripped:
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {
                    "content": stripped[:1900]
                }}]}
            })
        i += 1

    # ── 4. Notion API 호출 ───────────────────────────────────
    print(f"📝 Notion 저장 중: {title}")
    print(f"   📂 {notion_tag} ({category_key})")
    print(f"   📄 HTML 청크: {len(html_chunks)}개")

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json={
            "parent": {"page_id": NOTION_PAGE_ID},
            "icon": {"emoji": "📝"},
            "properties": {
                "title": {"title": [{"type": "text", "text": {
                    "content": f"[{category_key.upper()}] {title}"
                }}]}
            },
            "children": blocks[:100]
        },
        timeout=30
    )

    if resp.status_code != 200:
        raise Exception(f"Notion API 오류: {resp.status_code}\n{resp.text[:300]}")

    notion_url = resp.json().get("url", "")
    print(f"✅ Notion 저장 완료: {notion_url}")

    notify_discord(
        f"✅ **새 블로그 포스트 생성!**\n"
        f"📌 제목: {title}\n"
        f"📂 카테고리: {notion_tag}\n"
        f"📝 Notion: {notion_url}\n"
        f"→ Notion 열어서 HTML 토글 복사 → 티스토리 HTML 모드에 붙여넣기!"
    )
    return notion_url


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python tistory_poster.py <post_json_file>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        d = json.load(f)
    post_to_tistory(
        title=d["title"],
        content_html=d.get("content_html", ""),
        tags=d.get("tags", [])
    )
