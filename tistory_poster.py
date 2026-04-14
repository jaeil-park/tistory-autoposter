"""
tistory_poster.py - v8 (REST API 방식)
Playwright 로그인 완전 제거
티스토리 REST API + SESSION_ID 쿠키로 직접 포스팅
"""

import os
import json
import requests
from datetime import datetime

TISTORY_BLOG       = os.environ["TISTORY_BLOG"]
TISTORY_SESSION_ID = os.environ["TISTORY_SESSION_ID"]   # 브라우저에서 복사
DISCORD_WEBHOOK    = os.getenv("DISCORD_WEBHOOK", "")


def notify_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    requests.post(DISCORD_WEBHOOK, json={"content": message})


def post_to_tistory(title: str, content_html: str, tags: list, category_id: str = "0") -> str:
    """
    티스토리 REST API로 포스트 발행
    SESSION_ID 쿠키를 직접 사용 — 카카오 로그인 불필요
    """

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/",
        "Origin": f"https://{TISTORY_BLOG}.tistory.com",
    })

    # SESSION_ID 쿠키 설정
    session.cookies.set("TSSESSION", TISTORY_SESSION_ID, domain=".tistory.com")
    session.cookies.set("TSSESSION", TISTORY_SESSION_ID, domain=f"{TISTORY_BLOG}.tistory.com")

    # 글쓰기 페이지에서 CSRF 토큰 획득
    print("🔑 CSRF 토큰 획득 중...")
    manage_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
    resp = session.get(manage_url, timeout=15)

    if "auth/login" in resp.url or resp.status_code != 200:
        raise Exception(
            f"❌ 세션 만료 또는 로그인 필요\n"
            f"   STATUS: {resp.status_code}, URL: {resp.url}\n"
            f"   → SESSION_ID를 새로 복사해서 Secret을 업데이트하세요."
        )

    # CSRF 토큰 파싱
    import re
    csrf_match = re.search(r'_csrf["\s]+value=["\s]+([a-zA-Z0-9\-]+)', resp.text)
    if not csrf_match:
        csrf_match = re.search(r'"csrf"\s*:\s*"([a-zA-Z0-9\-]+)"', resp.text)
    if not csrf_match:
        csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text)

    csrf_token = csrf_match.group(1) if csrf_match else ""
    print(f"  {'✅' if csrf_token else '⚠️'} CSRF: {csrf_token[:20] if csrf_token else '없음 (계속 진행)'}")

    # 포스트 발행 API 호출
    print("🚀 포스트 발행 중...")
    post_url = f"https://{TISTORY_BLOG}.tistory.com/manage/post/quick-save"

    payload = {
        "type":           "post",
        "status":         "publish",       # 즉시 발행
        "visibility":     "20",            # 공개
        "title":          title,
        "content":        content_html,
        "tag":            ",".join(tags[:10]),
        "categoryId":     category_id,
        "published":      "",
        "slogan":         "",
        "acceptComment":  "1",
        "password":       "",
    }
    if csrf_token:
        payload["_csrf"] = csrf_token

    resp = session.post(post_url, data=payload, timeout=30)
    print(f"  STATUS: {resp.status_code}")

    if resp.status_code == 200:
        try:
            result = resp.json()
            post_id = result.get("postId") or result.get("id") or ""
            if post_id:
                final_url = f"https://{TISTORY_BLOG}.tistory.com/{post_id}"
                print(f"🎉 발행 완료: {final_url}")
                notify_discord(
                    f"✅ **티스토리 자동 포스팅 완료!**\n"
                    f"📌 제목: {title}\n"
                    f"🔗 URL: {final_url}"
                )
                return final_url
        except Exception:
            pass

    # 대체 방법: write API
    print("  ℹ️ quick-save 실패 → write API 시도...")
    write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/post/write"
    resp2 = session.post(write_url, data=payload, timeout=30)
    print(f"  STATUS: {resp2.status_code}")

    if resp2.status_code in [200, 302]:
        # 발행된 포스트 목록에서 최신 글 URL 찾기
        list_url = f"https://{TISTORY_BLOG}.tistory.com/manage/posts"
        list_resp = session.get(list_url, timeout=15)
        latest = re.search(
            rf'href="https://{TISTORY_BLOG}\.tistory\.com/(\d+)"', list_resp.text
        )
        if latest:
            final_url = f"https://{TISTORY_BLOG}.tistory.com/{latest.group(1)}"
            print(f"🎉 발행 완료: {final_url}")
            notify_discord(
                f"✅ **티스토리 자동 포스팅 완료!**\n"
                f"📌 제목: {title}\n"
                f"🔗 URL: {final_url}"
            )
            return final_url

    raise Exception(f"포스팅 실패: {resp2.status_code}\n{resp2.text[:300]}")


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
