"""
tistory_poster.py - v9
티스토리 관리자 글쓰기 폼 직접 POST 방식
실제 form action URL 사용
"""

import os
import re
import json
import requests

TISTORY_BLOG       = os.environ["TISTORY_BLOG"]
TISTORY_SESSION_ID = os.environ["TISTORY_SESSION_ID"]
DISCORD_WEBHOOK    = os.getenv("DISCORD_WEBHOOK", "")


def notify_discord(message: str):
    if not DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=5)
        except Exception:
            pass


def post_to_tistory(title: str, content_html: str, tags: list, category_id: str = "0") -> str:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    })

    # TSSESSION 쿠키 설정
    session.cookies.set("TSSESSION", TISTORY_SESSION_ID, domain=".tistory.com")

    # ── Step 1: 글쓰기 페이지 로드해서 form action + CSRF 토큰 파싱 ──
    print("🔑 글쓰기 페이지 로드...")
    manage_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
    resp = session.get(manage_url, timeout=20, allow_redirects=True)
    print(f"  STATUS: {resp.status_code} | URL: {resp.url[:70]}")

    if resp.status_code != 200 or "auth/login" in resp.url:
        raise Exception(
            f"❌ 세션 만료\n"
            f"   URL: {resp.url}\n"
            f"   TSSESSION을 새로 복사해서 Secret을 업데이트하세요."
        )

    html = resp.text

    # form action URL 파싱
    form_action = re.search(r'<form[^>]+action=["\']([^"\']+)["\'][^>]*id=["\']entry-form', html)
    if not form_action:
        form_action = re.search(r'id=["\']entry-form["\'][^>]+action=["\']([^"\']+)["\']', html)
    if not form_action:
        form_action = re.search(r'action=["\']([^"\']*manage/post[^"\']*)["\']', html)

    action_url = form_action.group(1) if form_action else f"https://{TISTORY_BLOG}.tistory.com/manage/post/write"
    if action_url.startswith("/"):
        action_url = f"https://{TISTORY_BLOG}.tistory.com{action_url}"
    print(f"  Form action: {action_url}")

    # CSRF 토큰 파싱
    csrf = ""
    for pattern in [
        r'name=["\']_csrf["\'][^>]+value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\'][^>]+name=["\']_csrf["\']',
        r'"csrf"\s*:\s*"([^"]+)"',
        r'_csrf["\s:=]+["\']([a-zA-Z0-9\-]{20,})["\']',
    ]:
        m = re.search(pattern, html)
        if m:
            csrf = m.group(1)
            break
    print(f"  CSRF: {csrf[:20] if csrf else '없음'}")

    # 숨겨진 input 값들 파싱 (form 전체 필드 수집)
    hidden_inputs = {}
    for m in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', html):
        tag = m.group(0)
        name_m = re.search(r'name=["\']([^"\']+)["\']', tag)
        val_m  = re.search(r'value=["\']([^"\']*)["\']', tag)
        if name_m:
            hidden_inputs[name_m.group(1)] = val_m.group(1) if val_m else ""

    print(f"  숨겨진 필드: {list(hidden_inputs.keys())}")

    # ── Step 2: 포스트 발행 POST ────────────────────────────────────
    print("🚀 포스트 발행 중...")

    payload = {**hidden_inputs}  # 숨겨진 필드 전부 포함
    payload.update({
        "title":         title,
        "content":       content_html,
        "tag":           ",".join(tags[:10]),
        "categoryId":    category_id,
        "visibility":    "20",       # 공개
        "acceptComment": "1",
        "published":     "",
        "password":      "",
        "slogan":        "",
    })
    if csrf:
        payload["_csrf"] = csrf

    session.headers.update({
        "Referer":       manage_url,
        "Origin":        f"https://{TISTORY_BLOG}.tistory.com",
        "Content-Type":  "application/x-www-form-urlencoded",
    })

    resp2 = session.post(action_url, data=payload, timeout=30, allow_redirects=True)
    print(f"  STATUS: {resp2.status_code} | URL: {resp2.url[:70]}")

    # 성공 여부 확인: 숫자로 끝나는 URL이면 발행 완료
    post_url = resp2.url
    if re.search(rf"https://{TISTORY_BLOG}\.tistory\.com/\d+", post_url):
        print(f"🎉 발행 완료: {post_url}")
        notify_discord(
            f"✅ **티스토리 자동 포스팅 완료!**\n"
            f"📌 제목: {title}\n"
            f"🔗 URL: {post_url}"
        )
        return post_url

    # 리다이렉트된 URL에서 포스트 ID 추출 시도
    post_id = re.search(r'/(\d+)(?:\?|$|#)', post_url)
    if post_id:
        final_url = f"https://{TISTORY_BLOG}.tistory.com/{post_id.group(1)}"
        print(f"🎉 발행 완료 (ID 추출): {final_url}")
        notify_discord(
            f"✅ **티스토리 자동 포스팅 완료!**\n"
            f"📌 제목: {title}\n"
            f"🔗 URL: {final_url}"
        )
        return final_url

    # 응답 본문에서 포스트 ID 추출
    id_in_body = re.search(
        rf'https://{TISTORY_BLOG}\.tistory\.com/(\d+)', resp2.text
    )
    if id_in_body:
        final_url = f"https://{TISTORY_BLOG}.tistory.com/{id_in_body.group(1)}"
        print(f"🎉 발행 완료 (본문 추출): {final_url}")
        notify_discord(
            f"✅ **티스토리 자동 포스팅 완료!**\n"
            f"📌 제목: {title}\n"
            f"🔗 URL: {final_url}"
        )
        return final_url

    # 실패 — 디버깅 정보 출력
    print(f"\n❌ 발행 실패")
    print(f"  응답 URL: {resp2.url}")
    print(f"  응답 앞부분:\n{resp2.text[:500]}")
    raise Exception(f"포스팅 실패: STATUS={resp2.status_code}, URL={resp2.url}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python tistory_poster.py <post_json_file>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        post_data = json.load(f)
    post_to_tistory(
        title=post_data["title"],
        content_html=post_data["content_html"],
        tags=post_data.get("tags", []),
        category_id=post_data.get("category_id", "0")
    )
