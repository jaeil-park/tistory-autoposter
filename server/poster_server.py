"""
poster_server.py
집 서버에서 실행되는 FastAPI 서버
GitHub Actions에서 Webhook 수신 → Playwright로 티스토리 자동 발행
집 IP = 카카오 신뢰 환경 → 2FA 없음!
"""

import os
import json
import asyncio
import hashlib
import hmac
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

app = FastAPI(title="Tistory Auto-Poster Server")

# ── 환경변수 ───────────────────────────────────────────────
KAKAO_EMAIL      = os.environ["KAKAO_EMAIL"]
KAKAO_PASSWORD   = os.environ["KAKAO_PASSWORD"]
TISTORY_BLOG     = os.environ["TISTORY_BLOG"]
WEBHOOK_SECRET   = os.environ["WEBHOOK_SECRET"]   # GitHub Actions와 공유하는 시크릿
DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK", "")


def verify_signature(payload: bytes, signature: str) -> bool:
    """Webhook 요청 인증 — GitHub Actions와 동일한 시크릿 사용"""
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


async def notify_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        await session.post(DISCORD_WEBHOOK, json={"content": message})


async def post_to_tistory(title: str, content_html: str, tags: list) -> str:
    """Playwright로 티스토리 자동 발행 (집 IP에서 실행)"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await context.new_page()

        try:
            # ── 로그인 ────────────────────────────────────────
            print(f"[{datetime.now()}] 🔑 로그인 시작: {title[:30]}")
            await page.goto("https://www.tistory.com/auth/login",
                            wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # 카카오 버튼
            await page.click(".btn_login.link_kakao_id")
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            print(f"  📍 카카오 URL: {page.url[:60]}")

            # 계정 선택 화면 처리
            if "login/simple" in page.url or "select_account" in page.url:
                try:
                    el = page.locator(f"a:has-text('{KAKAO_EMAIL}')").first
                    await el.wait_for(state="visible", timeout=4000)
                    await el.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

            # 이메일 입력 (필요 시)
            if "tistory.com" not in page.url:
                for sel in ["#loginId--1", "input[name='loginId']", "input[type='email']"]:
                    try:
                        el = page.locator(sel).first
                        await el.wait_for(state="visible", timeout=3000)
                        val = await el.input_value()
                        if not val:
                            await el.fill(KAKAO_EMAIL)
                        break
                    except Exception:
                        continue

                # 비밀번호
                for sel in ["#password--2", "input[name='password']", "input[type='password']"]:
                    try:
                        el = page.locator(sel).first
                        await el.wait_for(state="visible", timeout=5000)
                        await el.fill(KAKAO_PASSWORD)
                        break
                    except Exception:
                        continue

                # 로그인 버튼
                for sel in [".btn_g.highlight.submit", "button[type='submit']", ".submit"]:
                    try:
                        btn = page.locator(sel).first
                        await btn.wait_for(state="visible", timeout=3000)
                        await btn.click()
                        break
                    except Exception:
                        continue

                await page.wait_for_url("**/tistory.com/**", timeout=30000)

            print(f"  ✅ 로그인 완료")

            # ── 글쓰기 ────────────────────────────────────────
            write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
            await page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # 제목
            for sel in ["#post-title-inp", "input.tf_subject", "input[placeholder*='제목']"]:
                try:
                    inp = page.locator(sel).first
                    await inp.wait_for(state="visible", timeout=5000)
                    await inp.fill(title)
                    break
                except Exception:
                    continue

            # HTML 모드
            for sel in ["button:has-text('HTML')", ".btn_html", "[data-mode='html']"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
                except Exception:
                    continue

            # 본문
            for frame in page.frames:
                try:
                    result = await frame.evaluate(f"""
                        (function() {{
                            const cm = document.querySelector('.CodeMirror');
                            if (cm && cm.CodeMirror) {{
                                cm.CodeMirror.setValue({json.dumps(content_html)});
                                return 'ok';
                            }}
                            return null;
                        }})();
                    """)
                    if result:
                        break
                except Exception:
                    continue

            # 태그
            if tags:
                for sel in ["#tag-label", "input.tf_tag", "input[placeholder*='태그']"]:
                    try:
                        tag_inp = page.locator(sel).first
                        await tag_inp.wait_for(state="visible", timeout=5000)
                        for tag in tags[:10]:
                            await tag_inp.fill(tag)
                            await tag_inp.press("Enter")
                            await page.wait_for_timeout(300)
                        break
                    except Exception:
                        continue

            # 발행
            for sel in ["#publish-layer-btn", "button.btn_publish", "button:has-text('발행')"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
                except Exception:
                    continue

            try:
                await page.locator("input[value='20']").check(timeout=3000)
            except Exception:
                pass

            for sel in ["#publish-btn", "button.btn_ok", "button:has-text('완료')", "button:has-text('발행하기')"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    break
                except Exception:
                    continue

            try:
                await page.wait_for_url(f"**/{TISTORY_BLOG}.tistory.com/**", timeout=20000)
            except PlaywrightTimeout:
                pass

            post_url = page.url
            print(f"  🎉 발행 완료: {post_url}")
            return post_url

        finally:
            await context.close()
            await browser.close()


async def handle_post_job(data: dict):
    """백그라운드 작업: 포스팅 실행"""
    title       = data.get("title", "")
    content_html = data.get("content_html", "")
    tags        = data.get("tags", "").split(",") if data.get("tags") else []
    notion_url  = data.get("notion_url", "")
    notion_tag  = data.get("notion_tag", "")

    try:
        post_url = await post_to_tistory(title, content_html, tags)

        await notify_discord(
            f"✅ **티스토리 자동 발행 완료!**\n"
            f"📌 제목: {title}\n"
            f"📂 카테고리: {notion_tag}\n"
            f"🔗 티스토리: {post_url}\n"
            f"📝 Notion: {notion_url}"
        )
    except Exception as e:
        print(f"  ❌ 발행 실패: {e}")
        await notify_discord(
            f"❌ **티스토리 발행 실패**\n"
            f"📌 제목: {title}\n"
            f"오류: {str(e)[:200]}\n"
            f"📝 Notion에서 수동 복붙: {notion_url}"
        )


@app.get("/health")
async def health():
    return {"status": "ok", "server": "tistory-auto-poster"}


@app.post("/webhook/post")
async def webhook_post(request: Request, background_tasks: BackgroundTasks):
    """GitHub Actions에서 호출하는 Webhook 엔드포인트"""
    # 서명 검증
    signature = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()

    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = json.loads(body)
    print(f"\n[{datetime.now()}] 📥 Webhook 수신: {data.get('title', '')[:50]}")

    # 백그라운드로 포스팅 실행 (즉시 200 응답)
    background_tasks.add_task(handle_post_job, data)

    return JSONResponse({"status": "accepted", "message": "포스팅 작업 시작됨"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
