"""
tistory_poster.py
Playwright 기반 티스토리 자동 포스팅 스크립트
카카오 계정으로 로그인 → HTML 모드로 포스트 작성 → 발행
"""

import asyncio
import os
import json
import time
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ── 환경변수 ──────────────────────────────────────────
KAKAO_EMAIL    = os.environ["KAKAO_EMAIL"]
KAKAO_PASSWORD = os.environ["KAKAO_PASSWORD"]
TISTORY_BLOG   = os.environ["TISTORY_BLOG"]      # e.g. "jaeil"  → jaeil.tistory.com
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")


async def notify_discord(message: str):
    """Discord Webhook으로 결과 알림 전송"""
    if not DISCORD_WEBHOOK:
        return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        await session.post(DISCORD_WEBHOOK, json={"content": message})


async def post_to_tistory(title: str, content_html: str, tags: list[str], category_id: str = "0"):
    """
    티스토리에 포스트를 발행하는 핵심 함수
    - title        : 포스트 제목
    - content_html : HTML 형식의 본문
    - tags         : 태그 리스트 (최대 10개)
    - category_id  : 카테고리 ID (기본값 "0" = 미분류)
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]   # GitHub Actions 환경 필수
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            # ── STEP 1: 티스토리 로그인 페이지 ─────────────────────
            print("🔑 티스토리 로그인 시작...")
            await page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")

            # 카카오 로그인 버튼 클릭
            await page.click(".btn_login.link_kakao_id")
            await page.wait_for_url("**/kakao.com/**", timeout=10000)

            # ── STEP 2: 카카오 계정 입력 ────────────────────────────
            print("📧 카카오 계정 입력 중...")
            await page.fill("#loginId--1", KAKAO_EMAIL)
            await page.fill("#password--2", KAKAO_PASSWORD)
            await page.click(".btn_g.highlight.submit")

            # 로그인 완료 대기 (티스토리로 리다이렉트)
            await page.wait_for_url("**/tistory.com/**", timeout=15000)
            print("✅ 로그인 성공!")

            # ── STEP 3: 글쓰기 페이지 이동 ──────────────────────────
            write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
            print(f"📝 글쓰기 페이지 이동: {write_url}")
            await page.goto(write_url, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # ── STEP 4: 제목 입력 ───────────────────────────────────
            print(f"📌 제목 입력: {title}")
            title_input = page.locator("#post-title-inp")
            await title_input.wait_for(state="visible", timeout=10000)
            await title_input.fill(title)

            # ── STEP 5: HTML 모드 전환 ───────────────────────────────
            print("🔄 HTML 편집 모드 전환 중...")
            # "기본 모드" → "HTML" 탭 클릭
            try:
                html_tab = page.locator("button:has-text('HTML')")
                await html_tab.wait_for(state="visible", timeout=5000)
                await html_tab.click()
                await page.wait_for_timeout(1000)
            except PlaywrightTimeout:
                # 에디터 타입이 다를 경우 대비
                await page.evaluate("document.querySelector('.CodeMirror') && switchMode('html')")

            # ── STEP 6: 본문 HTML 입력 ──────────────────────────────
            print("📄 본문 입력 중...")
            # CodeMirror 에디터에 직접 입력
            await page.evaluate(f"""
                (function() {{
                    const editor = document.querySelector('.CodeMirror').CodeMirror;
                    if (editor) {{
                        editor.setValue({json.dumps(content_html)});
                    }}
                }})();
            """)
            await page.wait_for_timeout(1000)

            # ── STEP 7: 카테고리 설정 ───────────────────────────────
            if category_id != "0":
                print(f"📂 카테고리 설정: {category_id}")
                try:
                    await page.select_option("#category-id", value=category_id)
                except Exception:
                    print("⚠️ 카테고리 설정 실패 (미분류로 발행)")

            # ── STEP 8: 태그 입력 ───────────────────────────────────
            if tags:
                print(f"🏷️ 태그 입력: {', '.join(tags[:10])}")
                tag_input = page.locator("#tag-label")
                await tag_input.wait_for(state="visible", timeout=5000)
                for tag in tags[:10]:   # 티스토리 최대 10개
                    await tag_input.fill(tag)
                    await tag_input.press("Enter")
                    await page.wait_for_timeout(300)

            # ── STEP 9: 발행 ────────────────────────────────────────
            print("🚀 발행 버튼 클릭...")
            publish_btn = page.locator("#publish-layer-btn")
            await publish_btn.wait_for(state="visible", timeout=5000)
            await publish_btn.click()
            await page.wait_for_timeout(1000)

            # 발행 확인 팝업에서 "공개" 선택 후 발행
            try:
                public_radio = page.locator("input[value='20']")   # 20 = 공개
                await public_radio.check(timeout=3000)
            except PlaywrightTimeout:
                pass

            confirm_btn = page.locator("#publish-btn")
            await confirm_btn.wait_for(state="visible", timeout=5000)
            await confirm_btn.click()

            # ── STEP 10: 발행 완료 확인 ─────────────────────────────
            await page.wait_for_url(f"**/{TISTORY_BLOG}.tistory.com/**", timeout=15000)
            post_url = page.url
            print(f"🎉 발행 완료: {post_url}")

            # Discord 알림
            await notify_discord(
                f"✅ **티스토리 자동 포스팅 완료!**\n"
                f"📌 제목: {title}\n"
                f"🔗 URL: {post_url}"
            )
            return post_url

        except Exception as e:
            error_msg = f"❌ 포스팅 실패: {str(e)}"
            print(error_msg)
            # 실패 시 스크린샷 저장 (디버깅용)
            await page.screenshot(path="error_screenshot.png")
            await notify_discord(f"❌ **티스토리 포스팅 실패**\n오류: {str(e)}")
            raise
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    # 단독 실행 테스트용
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tistory_poster.py <post_json_file>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        post_data = json.load(f)

    asyncio.run(post_to_tistory(
        title=post_data["title"],
        content_html=post_data["content_html"],
        tags=post_data.get("tags", []),
        category_id=post_data.get("category_id", "0")
    ))
