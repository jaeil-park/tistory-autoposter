"""
tistory_poster.py - v15
Notion 저장 + 집 서버 Webhook 트리거
집 서버에서 Playwright로 티스토리 자동 발행
"""

import os
import re
import json
import hmac
import hashlib
import requests

NOTION_TOKEN     = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID   = os.environ["NOTION_PAGE_ID"]
DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK", "")
HOME_SERVER_URL  = os.getenv("HOME_SERVER_URL", "")    # 예: https://poster.jaeil.dev
WEBHOOK_SECRET   = os.getenv("WEBHOOK_SECRET", "")     # 집 서버와 공유하는 시크릿


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

    # 집 서버 Webhook 호출 (티스토리 자동 발행)
    if HOME_SERVER_URL and WEBHOOK_SECRET:
        trigger_home_server(
            title=title, content_html=content_html, tags=tags,
            notion_url=notion_url, notion_tag=notion_tag,
            thumbnail_title=thumbnail_title,
        )
    else:
        # 집 서버 미설정 시 Discord로 알림만
        notify_discord(
            f"📝 **Notion 저장 완료**\n"
            f"📌 {title}\n📂 {notion_tag}\n📝 {notion_url}\n"
            f"⚠️ HOME_SERVER_URL 미설정 — Notion에서 수동 복붙 필요"
        )

    return notion_url


def trigger_home_server(title, content_html, tags, notion_url, notion_tag, thumbnail_title):
    """집 서버 Webhook 호출 (HMAC 서명 포함)"""
    payload = json.dumps({
        "title":           title,
        "content_html":    content_html,
        "tags":            ",".join(tags[:10]),
        "notion_url":      notion_url,
        "notion_tag":      notion_tag,
        "thumbnail_title": thumbnail_title,
    }, ensure_ascii=False).encode()

    # HMAC 서명
    signature = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()

    print(f"🏠 집 서버 Webhook 호출: {HOME_SERVER_URL}")
    try:
        resp = requests.post(
            f"{HOME_SERVER_URL}/webhook/post",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
            timeout=15
        )
        print(f"  ✅ 응답: {resp.status_code} — {resp.json().get('message', '')}")
        notify_discord(
            f"🚀 **티스토리 자동 발행 시작!**\n"
            f"📌 {title}\n📂 {notion_tag}\n"
            f"📝 Notion: {notion_url}\n"
            f"⏳ 집 서버에서 발행 중... (완료 시 Discord 알림)"
        )
    except Exception as e:
        print(f"  ❌ 집 서버 호출 실패: {e}")
        notify_discord(
            f"⚠️ **집 서버 연결 실패**\n"
            f"📌 {title}\n"
            f"📝 Notion에서 수동 복붙: {notion_url}\n오류: {str(e)[:100]}"
        )


def save_to_notion(title, content_md, content_html, tags,
                   thumbnail_title="", notion_tag="📝 일반",
                   category_key="general", meta_desc="", post_type="") -> str:

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    blocks = []

    # 메타 정보
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

    # HTML 코드블록
    blocks.append({"object": "block", "type": "divider", "divider": {}})
    blocks.append({
        "object": "block", "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {
            "content": "📋 티스토리 HTML (복사 후 HTML 모드에 붙여넣기)"
        }}]}
    })
    html_clean = content_html.replace("\n", " ")
    for i in range(0, min(len(html_clean), 1900 * 20), 1900):
        blocks.append({
            "object": "block", "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": html_clean[i:i+1900]}}],
                "language": "html"
            }
        })

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # 본문 마크다운
    supported_langs = {
        "python","javascript","typescript","bash","shell","json","yaml",
        "sql","html","css","java","go","rust","kotlin","swift","c","cpp","plain text"
    }
    lines = content_md.split('\n')
    i = 0
    code_buf, in_code, code_lang = [], False, ""
    while i < len(lines) and len(blocks) < 95:
        line = lines[i]
        if line.startswith('```'):
            if not in_code:
                in_code, code_lang, code_buf = True, line[3:].strip() or "plain text", []
            else:
                blocks.append({"object":"block","type":"code","code":{
                    "rich_text":[{"type":"text","text":{"content":'\n'.join(code_buf)[:1900]}}],
                    "language": code_lang if code_lang in supported_langs else "plain text"
                }})
                in_code = False
            i += 1
            continue
        if in_code:
            code_buf.append(line)
        elif line.startswith('### '):
            blocks.append({"object":"block","type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":line[4:].strip()}}]}})
        elif line.startswith('## '):
            blocks.append({"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":line[3:].strip()}}]}})
        elif line.startswith('# '):
            blocks.append({"object":"block","type":"heading_1","heading_1":{"rich_text":[{"type":"text","text":{"content":line[2:].strip()}}]}})
        elif line.strip() == '---':
            blocks.append({"object":"block","type":"divider","divider":{}})
        elif line.strip():
            blocks.append({"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":line.strip()[:1900]}}]}})
        i += 1

    print(f"📝 Notion 저장: {title} | {notion_tag}")
    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json={
            "parent": {"page_id": NOTION_PAGE_ID},
            "icon": {"emoji": "📝"},
            "properties": {"title": {"title": [{"type":"text","text":{
                "content": f"[{category_key.upper()}] {title}"
            }}]}},
            "children": blocks[:100]
        },
        timeout=30
    )
    if resp.status_code != 200:
        raise Exception(f"Notion 오류: {resp.status_code}\n{resp.text[:200]}")

    notion_url = resp.json().get("url", "")
    print(f"✅ Notion 저장 완료: {notion_url}")
    return notion_url


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        d = json.load(f)
    post_to_tistory(title=d["title"], content_html=d.get("content_html",""), tags=d.get("tags",[]))
