"""
tistory_poster.py - v12
Notion 저장 + 카테고리 자동 분류
"""

import os
import json
import requests

NOTION_TOKEN   = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID = os.environ["NOTION_PAGE_ID"]
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")


def notify_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=5)
    except Exception:
        pass


def post_to_tistory(title: str, content_html: str, tags: list, category_id: str = "0") -> str:
    # post_output.json에서 전체 데이터 읽기
    post_data = {}
    try:
        with open("post_output.json", "r", encoding="utf-8") as f:
            post_data = json.load(f)
    except Exception:
        pass

    content_md      = post_data.get("content_md", content_html)
    thumbnail_title = post_data.get("thumbnail_title", "")
    notion_tag      = post_data.get("notion_tag", "📝 일반")
    category_key    = post_data.get("category_key", "general")
    meta_desc       = post_data.get("meta_description", "")
    post_type       = post_data.get("post_type", "")

    return post_to_notion(
        title=title,
        content_md=content_md,
        tags=tags,
        thumbnail_title=thumbnail_title,
        notion_tag=notion_tag,
        category_key=category_key,
        meta_desc=meta_desc,
        post_type=post_type,
    )


def post_to_notion(title, content_md, tags, thumbnail_title="",
                   notion_tag="📝 일반", category_key="general",
                   meta_desc="", post_type="") -> str:

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    # ── Notion 블록 생성 ─────────────────────────────────────
    blocks = []

    # 메타 정보 callout
    meta_lines = []
    if thumbnail_title:
        meta_lines.append(f"🖼️ 썸네일: {thumbnail_title}")
    if notion_tag:
        meta_lines.append(f"📂 카테고리: {notion_tag}")
    if post_type:
        meta_lines.append(f"📋 타입: {post_type}")
    if tags:
        meta_lines.append(f"🏷️ 태그: {' '.join(['#' + t for t in tags[:10]])}")
    if meta_desc:
        meta_lines.append(f"🔍 메타: {meta_desc}")

    if meta_lines:
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": "\n".join(meta_lines)}}],
                "icon": {"emoji": "📋"},
                "color": "blue_background"
            }
        })
        blocks.append({"object": "block", "type": "divider", "divider": {}})

    # 본문 파싱
    import re
    lines = content_md.split('\n')
    i = 0
    code_buffer = []
    in_code = False
    code_lang = ""
    supported_langs = {
        "python", "javascript", "typescript", "bash", "shell",
        "json", "yaml", "sql", "html", "css", "java", "go",
        "rust", "kotlin", "swift", "c", "cpp", "plain text"
    }

    while i < len(lines):
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
                        "rich_text": [{"type": "text", "text": {"content": '\n'.join(code_buffer)[:1900]}}],
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

        if line.startswith('### '):
            blocks.append({"object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]}})
        elif line.startswith('## '):
            blocks.append({"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]}})
        elif line.startswith('# '):
            blocks.append({"object": "block", "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]}})
        elif line.strip() == '---':
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif line.strip():
            text = line.strip()[:1900]
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}
            })
        i += 1

    # ── Notion API 호출 ──────────────────────────────────────
    print(f"📝 Notion 저장 중: {title}")
    print(f"   📂 {notion_tag} ({category_key})")

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json={
            "parent": {"page_id": NOTION_PAGE_ID},
            "icon": {"emoji": "📝"},
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": f"[{category_key.upper()}] {title}"}}]}
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
        f"→ 확인 후 티스토리에 복붙하세요!"
    )
    return notion_url


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python tistory_poster.py <post_json_file>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        d = json.load(f)
    post_to_tistory(title=d["title"], content_html=d.get("content_html",""), tags=d.get("tags",[]))
