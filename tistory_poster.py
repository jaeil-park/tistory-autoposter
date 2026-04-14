"""
tistory_poster.py - v14
Notion 저장 (단순화) + Make Webhook 트리거
"""

import os
import re
import json
import requests

NOTION_TOKEN    = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID  = os.environ["NOTION_PAGE_ID"]
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
MAKE_WEBHOOK    = os.getenv("MAKE_WEBHOOK", "")   # Make 자동화 트리거


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

    content_md      = post_data.get("content_md", "")
    content_html    = post_data.get("content_html", content_html)
    thumbnail_title = post_data.get("thumbnail_title", "")
    notion_tag      = post_data.get("notion_tag", "📝 일반")
    category_key    = post_data.get("category_key", "general")
    meta_desc       = post_data.get("meta_description", "")
    post_type       = post_data.get("post_type", "")

    # Notion 저장
    notion_url = save_to_notion(
        title=title, content_md=content_md, content_html=content_html,
        tags=tags, thumbnail_title=thumbnail_title, notion_tag=notion_tag,
        category_key=category_key, meta_desc=meta_desc, post_type=post_type,
    )

    # Make Webhook 트리거 (티스토리 자동 발행)
    if MAKE_WEBHOOK:
        trigger_make(
            title=title, content_html=content_html, tags=tags,
            notion_url=notion_url, notion_tag=notion_tag,
            thumbnail_title=thumbnail_title, meta_desc=meta_desc,
        )

    return notion_url


def save_to_notion(title, content_md, content_html, tags,
                   thumbnail_title="", notion_tag="📝 일반",
                   category_key="general", meta_desc="", post_type="") -> str:

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    blocks = []

    # ── 메타 정보 ────────────────────────────────────────────
    meta_lines = []
    if thumbnail_title: meta_lines.append(f"🖼️ 썸네일: {thumbnail_title}")
    if notion_tag:      meta_lines.append(f"📂 카테고리: {notion_tag}")
    if post_type:       meta_lines.append(f"📋 타입: {post_type}")
    if tags:            meta_lines.append(f"🏷️ 태그: {' '.join(['#'+t for t in tags[:10]])}")
    if meta_desc:       meta_lines.append(f"🔍 메타: {meta_desc}")

    if meta_lines:
        blocks.append({
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": "\n".join(meta_lines)}}],
                "icon": {"emoji": "📋"}, "color": "blue_background"
            }
        })

    # ── 티스토리 HTML (단일 코드블록) ────────────────────────
    # 2000자 초과 시 분할하되 하나의 섹션으로 표시
    blocks.append({"object": "block", "type": "divider", "divider": {}})
    blocks.append({
        "object": "block", "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {
            "content": "📋 티스토리 HTML (복사 후 HTML 모드에 붙여넣기)"
        }}]}
    })

    html_clean = content_html.replace("\n", " ")
    chunk_size = 1900
    for i in range(0, min(len(html_clean), chunk_size * 20), chunk_size):
        chunk = html_clean[i:i+chunk_size]
        blocks.append({
            "object": "block", "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}],
                "language": "html"
            }
        })

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # ── 본문 마크다운 ─────────────────────────────────────────
    supported_langs = {
        "python","javascript","typescript","bash","shell","json","yaml",
        "sql","html","css","java","go","rust","kotlin","swift","c","cpp","plain text"
    }
    lines = content_md.split('\n')
    i = 0
    code_buf = []
    in_code = False
    code_lang = ""

    while i < len(lines) and len(blocks) < 95:
        line = lines[i]
        if line.startswith('```'):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip() or "plain text"
                code_buf = []
            else:
                blocks.append({
                    "object": "block", "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": '\n'.join(code_buf)[:1900]}}],
                        "language": code_lang if code_lang in supported_langs else "plain text"
                    }
                })
                in_code = False
                code_buf = []
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        s = line.strip()
        if line.startswith('### '):
            blocks.append({"object":"block","type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":line[4:].strip()}}]}})
        elif line.startswith('## '):
            blocks.append({"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":line[3:].strip()}}]}})
        elif line.startswith('# '):
            blocks.append({"object":"block","type":"heading_1","heading_1":{"rich_text":[{"type":"text","text":{"content":line[2:].strip()}}]}})
        elif s == '---':
            blocks.append({"object":"block","type":"divider","divider":{}})
        elif s:
            blocks.append({"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":s[:1900]}}]}})
        i += 1

    # ── Notion 페이지 생성 ───────────────────────────────────
    print(f"📝 Notion 저장: {title}")
    print(f"   📂 {notion_tag} ({category_key})")

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json={
            "parent": {"page_id": NOTION_PAGE_ID},
            "icon": {"emoji": "📝"},
            "properties": {
                "title": {"title": [{"type":"text","text":{
                    "content": f"[{category_key.upper()}] {title}"
                }}]}
            },
            "children": blocks[:100]
        },
        timeout=30
    )

    if resp.status_code != 200:
        raise Exception(f"Notion 오류: {resp.status_code}\n{resp.text[:200]}")

    notion_url = resp.json().get("url", "")
    print(f"✅ Notion 저장 완료: {notion_url}")
    return notion_url


def trigger_make(title, content_html, tags, notion_url,
                 notion_tag="", thumbnail_title="", meta_desc=""):
    """Make Webhook으로 티스토리 자동 발행 트리거"""
    print("🔗 Make Webhook 트리거...")
    try:
        resp = requests.post(MAKE_WEBHOOK, json={
            "title":           title,
            "content_html":    content_html,
            "tags":            ",".join(tags[:10]),
            "notion_url":      notion_url,
            "notion_tag":      notion_tag,
            "thumbnail_title": thumbnail_title,
            "meta_description": meta_desc,
        }, timeout=15)
        print(f"  ✅ Make 트리거 완료: {resp.status_code}")

        notify_discord(
            f"✅ **티스토리 포스팅 자동화 완료!**\n"
            f"📌 제목: {title}\n"
            f"📂 카테고리: {notion_tag}\n"
            f"📝 Notion: {notion_url}\n"
            f"🚀 Make가 티스토리에 자동 발행 중..."
        )
    except Exception as e:
        print(f"  ⚠️ Make 트리거 실패: {e}")
        notify_discord(
            f"📝 **Notion 저장 완료** (Make 트리거 실패)\n"
            f"📌 제목: {title}\n"
            f"📂 카테고리: {notion_tag}\n"
            f"📝 Notion: {notion_url}"
        )


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        d = json.load(f)
    post_to_tistory(title=d["title"], content_html=d.get("content_html",""), tags=d.get("tags",[]))
