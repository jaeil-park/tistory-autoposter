"""
tistory_poster.py - v10
티스토리 내부 JSON API 직접 호출
네트워크 탭 분석 기반: /apis/post/write 엔드포인트
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
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=5)
    except Exception:
        pass


def get_csrf_token(session: requests.Session) -> str:
    """관리자 페이지에서 CSRF 토큰 추출"""
    resp = session.get(
        f"https://{TISTORY_BLOG}.tistory.com/manage",
        timeout=15
    )
    # meta 태그에서 추출
    m = re.search(r'<meta[^>]+name=["\']_csrf["\'][^>]+content=["\']([^"\']+)["\']', resp.text)
    if m:
        return m.group(1)
    # JS 변수에서 추출
    m = re.search(r'["\']?_csrf["\']?\s*[:=]\s*["\']([a-zA-Z0-9\-]{20,})["\']', resp.text)
    if m:
        return m.group(1)
    return ""


def post_to_tistory(title: str, content_html: str, tags: list, category_id: str = "0") -> str:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    })
    session.cookies.set("TSSESSION", TISTORY_SESSION_ID, domain=".tistory.com")

    # ── Step 1: 세션 유효성 확인 ─────────────────────────────
    print("🔑 세션 확인...")
    resp = session.get(
        f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/",
        timeout=15, allow_redirects=True
    )
    print(f"  STATUS: {resp.status_code} | URL: {resp.url[:70]}")

    if "auth/login" in resp.url or resp.status_code == 401:
        raise Exception("❌ TSSESSION 만료 — Secret을 새로 업데이트하세요.")

    # ── Step 2: CSRF 토큰 획득 ───────────────────────────────
    csrf = get_csrf_token(session)
    print(f"  CSRF: {csrf[:20] if csrf else '없음'}")

    # ── Step 3: API 방식 1 — JSON API ────────────────────────
    print("🚀 방식 1: JSON API...")
    session.headers.update({
        "Content-Type": "application/json;charset=UTF-8",
        "Accept":       "application/json, text/plain, */*",
        "Referer":      f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/",
        "Origin":       f"https://{TISTORY_BLOG}.tistory.com",
        "X-Requested-With": "XMLHttpRequest",
    })
    if csrf:
        session.headers["X-CSRF-TOKEN"] = csrf

    payload = {
        "title":          title,
        "content":        content_html,
        "visibility":     20,
        "categoryId":     int(category_id),
        "tag":            ",".join(tags[:10]),
        "acceptComment":  1,
        "published":      None,
        "slogan":         "",
        "password":       "",
        "postType":       "NORMAL",
    }

    for endpoint in [
        f"https://{TISTORY_BLOG}.tistory.com/manage/api/post",
        f"https://{TISTORY_BLOG}.tistory.com/manage/api/post/write",
        f"https://{TISTORY_BLOG}.tistory.com/manage/posts/api",
    ]:
        try:
            r = session.post(endpoint, json=payload, timeout=20)
            print(f"  {endpoint.split('/manage/')[1]}: {r.status_code}")
            if r.status_code in [200, 201]:
                try:
                    data = r.json()
                    post_id = (data.get("postId") or data.get("id") or
                               data.get("data", {}).get("postId") or
                               data.get("result", {}).get("postId"))
                    if post_id:
                        url = f"https://{TISTORY_BLOG}.tistory.com/{post_id}"
                        print(f"🎉 발행 완료 (JSON API): {url}")
                        notify_discord(f"✅ **티스토리 포스팅 완료!**\n📌 {title}\n🔗 {url}")
                        return url
                except Exception:
                    pass
        except Exception as e:
            print(f"  오류: {e}")

    # ── Step 4: 방식 2 — multipart/form-data ─────────────────
    print("🚀 방식 2: multipart form...")
    session.headers.pop("Content-Type", None)
    session.headers.pop("X-CSRF-TOKEN", None)
    session.headers["Accept"] = "application/json, text/plain, */*"

    form_data = {
        "title":         (None, title),
        "content":       (None, content_html),
        "visibility":    (None, "20"),
        "categoryId":    (None, category_id),
        "tag":           (None, ",".join(tags[:10])),
        "acceptComment": (None, "1"),
        "postType":      (None, "NORMAL"),
    }
    if csrf:
        form_data["_csrf"] = (None, csrf)

    for endpoint in [
        f"https://{TISTORY_BLOG}.tistory.com/manage/api/post",
        f"https://{TISTORY_BLOG}.tistory.com/manage/post/write",
    ]:
        try:
            r = session.post(endpoint, files=form_data, timeout=20)
            print(f"  {endpoint.split('/manage/')[1]}: {r.status_code} | {r.url[:60]}")
            if r.status_code in [200, 201, 302]:
                # URL에서 포스트 ID 추출
                post_id_m = re.search(rf"/{TISTORY_BLOG}\.tistory\.com/(\d+)", r.url)
                if not post_id_m:
                    post_id_m = re.search(r'/(\d+)(?:\?|$)', r.url)
                if post_id_m:
                    url = f"https://{TISTORY_BLOG}.tistory.com/{post_id_m.group(1)}"
                    print(f"🎉 발행 완료 (form): {url}")
                    notify_discord(f"✅ **티스토리 포스팅 완료!**\n📌 {title}\n🔗 {url}")
                    return url
                # 응답 본문에서 ID 추출
                id_m = re.search(r'"(?:postId|id)"\s*:\s*(\d+)', r.text)
                if id_m:
                    url = f"https://{TISTORY_BLOG}.tistory.com/{id_m.group(1)}"
                    print(f"🎉 발행 완료 (본문): {url}")
                    notify_discord(f"✅ **티스토리 포스팅 완료!**\n📌 {title}\n🔗 {url}")
                    return url
        except Exception as e:
            print(f"  오류: {e}")

    # ── Step 5: 디버깅 정보 수집 ─────────────────────────────
    print("\n🔍 네트워크 엔드포인트 탐색...")
    debug_resp = session.get(
        f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/",
        timeout=15
    )
    # JS 번들에서 API 엔드포인트 힌트 추출
    api_hints = re.findall(r'["\']/(manage/[^"\']+/(?:write|post|save|create)[^"\']*)["\']', debug_resp.text)
    print(f"  발견된 API 힌트: {api_hints[:10]}")

    raise Exception(
        "모든 API 방식 실패.\n"
        "브라우저 개발자도구 → Network 탭 → 글 저장 시 호출되는 API URL을 확인해주세요."
    )


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
