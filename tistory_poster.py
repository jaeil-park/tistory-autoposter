"""
tistory_poster.py - v11 (Notion API 저장)
티스토리 직접 발행 대신 Notion에 포스트 저장
Notion에서 확인 후 티스토리에 복붙
"""

import os
import json
import requests

TISTORY_BLOG    = os.environ.get("TISTORY_BLOG", "")
NOTION_TOKEN    = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID  = os.environ["NOTION_PAGE_ID"]   # 허브 페이지 ID
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")


def notify_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=5)
    except Exception:
        pass


def post_to_notion(title: str, content_md: str, tags: list, thumbnail_title: str = "") -> str:
    """Notion에 블로그 포스트 저장"""

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    # 마크다운을 Notion 블록으로 변환 (간단 버전)
    blocks = []

    # 썸네일 제목
    if thumbnail_title:
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": f"🖼️ 썸네일 제목: {thumbnail_title}"}}],
                "icon": {"emoji": "🖼️"},
                "color": "blue_background"
            }
        })

    # 태그
    if tags:
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": f"🏷️ 태그: {' '.join(['#' + t for t in tags[:10]])}"}}],
                "icon": {"emoji": "🏷️"},
                "color": "green_background"
            }
        })

    # 구분선
    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # 본문을 줄 단위로 Notion 블록으로 변환
    lines = content_md.split('\n')
    i = 0
    code_buffer = []
    in_code = False
    code_lang = ""

    while i < len(lines):
        line = lines[i]

        # 코드블록 처리
        if line.startswith('```'):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip() or "plain text"
                code_buffer = []
            else:
                # 코드블록 종료
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": '\n'.join(code_buffer)[:1900]}}],
                        "language": code_lang if code_lang in [
                            "python", "javascript", "typescript", "bash", "shell",
                            "json", "yaml", "sql", "html", "css", "java", "go",
                            "rust", "kotlin", "swift", "c", "cpp", "plain text"
                        ] else "plain text"
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

        # 헤딩
        if line.startswith('### '):
            blocks.append({"object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]}})
        elif line.startswith('## '):
            blocks.append({"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]}})
        elif line.startswith('# '):
            blocks.append({"object": "block", "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]}})
        # 구분선
        elif line.strip() == '---':
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        # 빈 줄
        elif not line.strip():
            pass
        # 일반 텍스트 (볼드 처리)
        else:
            text = line.strip()
            if len(text) > 1900:
                text = text[:1900] + "..."
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}
            })

        i += 1

    # Notion API: 페이지 생성
    print(f"📝 Notion에 페이지 생성 중: {title}")

    payload = {
        "parent": {"page_id": NOTION_PAGE_ID},
        "icon": {"emoji": "📝"},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": blocks[:100]  # Notion API 한 번에 최대 100블록
    }

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload,
        timeout=30
    )

    if resp.status_code != 200:
        raise Exception(f"Notion API 오류: {resp.status_code}\n{resp.text[:300]}")

    page_data = resp.json()
    notion_url = page_data.get("url", "")
    print(f"✅ Notion 저장 완료: {notion_url}")

    notify_discord(
        f"✅ **티스토리 포스트 Notion 저장 완료!**\n"
        f"📌 제목: {title}\n"
        f"📝 Notion: {notion_url}\n"
        f"→ 확인 후 티스토리에 복붙하세요!"
    )

    return notion_url


def post_to_tistory(title: str, content_html: str, tags: list, category_id: str = "0") -> str:
    """Notion에 저장 (티스토리 대체)"""

    # post_output.json에서 마크다운 읽기
    content_md = content_html  # fallback
    thumbnail_title = ""

    try:
        with open("post_output.json", "r", encoding="utf-8") as f:
            post_data = json.load(f)
            content_md = post_data.get("content_md", content_html)
            thumbnail_title = post_data.get("thumbnail_title", "")
    except Exception:
        pass

    return post_to_notion(title, content_md, tags, thumbnail_title)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python tistory_poster.py <post_json_file>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        post_data = json.load(f)
    post_to_tistory(
        title=post_data["title"],
        content_html=post_data.get("content_html", ""),
        tags=post_data.get("tags", []),
    )
