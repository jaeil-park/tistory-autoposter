"""
tistory_poster.py - v7 (쿠키 세션 재사용)
TISTORY_COOKIES Secret에서 쿠키 로드 → 카카오 추가인증 완전 우회
"""

import asyncio
import os
import json
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

KAKAO_EMAIL      = os.environ["KAKAO_EMAIL"]
KAKAO_PASSWORD   = os.environ["KAKAO_PASSWORD"]
TISTORY_BLOG     = os.environ["TISTORY_BLOG"]
DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK", "")
TISTORY_COOKIES  = os.getenv("TISTORY_COOKIES", "")   # JSON 문자열


async def notify_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        await session.post(DISCORD_WEBHOOK, json={"content": message})


async def save_debug(page, name: str):
    await page.screenshot(path=f"{name}.png")
    with open(f"{name}.html", "w", encoding="utf-8") as f:
        f.write(await page.content())
    print(f"  📸 {name}.png / {name}.html 저장")


async def login_with_cookies(context, page) -> bool:
    """저장된 쿠키로 로그인 시도"""
    if not TISTORY_COOKIES:
        return False

    try:
        cookies = json.loads(TISTORY_COOKIES)
        await context.add_cookies(cookies)
        print(f"  🍪 쿠키 {len(cookies)}개 로드")

        # 쿠키로 직접 글쓰기 페이지 접근
        write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
        await page.goto(write_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        # 로그인 페이지로 리다이렉트 됐으면 쿠키 만료
        if "auth/login" in page.url or "accounts.kakao" in page.url:
            print("  ⚠️ 쿠키 만료 → 일반 로그인으로 fallback")
            return False

        print(f"  ✅ 쿠키 로그인 성공: {page.url[:60]}")
        return True
    except Exception as e:
        print(f"  ⚠️ 쿠키 로그인 실패: {e}")
        return False


async def login_with_password(page):
    """이메일/비밀번호 직접 로그인 (쿠키 만료 시 fallback)"""
    print("🔑 직접 로그인 시도...")
    await page.goto("https://www.tistory.com/auth/login",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    await save_debug(page, "step1_tistory")

    # 카카오 버튼
    await page.click(".btn_login.link_kakao_id")
    await page.wait_for_load_state("domcontentloaded", timeout=15000)
    await page.wait_for_timeout(2000)
    print(f"  📍 {page.url[:80]}")
    await save_debug(page, "step2_kakao")

    # 이메일 입력
    for sel in ["#loginId--1", "input[name='loginId']", "input[type='email']"]:
        try:
            el = page.locator(sel).first
            await el.wait_for(state="visible", timeout=3000)
            val = await el.input_value()
            if not val:
                await el.fill(KAKAO_EMAIL)
            print(f"  ✅ 이메일: {sel}")
            break
        except Exception:
            continue

    # 비밀번호 입력
    for sel in ["#password--2", "input[name='password']", "input[type='password']"]:
        try:
            el = page.locator(sel).first
            await el.wait_for(state="visible", timeout=5000)
            await el.fill(KAKAO_PASSWORD)
            print(f"  ✅ 비밀번호: {sel}")
            break
        except Exception:
            continue

    # 로그인 버튼
    for sel in [".btn_g.highlight.submit", "button[type='submit']", ".submit"]:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=3000)
            await btn.click()
            print(f"  ✅ 로그인 버튼: {sel}")
            break
        except Exception:
            continue

    await save_debug(page, "step3_after_submit")
    print(f"  📍 제출 후: {page.url[:80]}")

    # tistory 리다이렉트 대기
    await page.wait_for_url("**/tistory.com/**", timeout=30000)
    print(f"✅ 로그인 완료: {page.url[:60]}")


async def post_to_tistory(title: str, content_html: str, tags: list, category_id: str = "0"):
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
            # ── 로그인: 쿠키 우선, 실패 시 직접 로그인 ──────────────
            cookie_ok = await login_with_cookies(context, page)

            if cookie_ok:
                # 쿠키 로그인 성공 → 이미 글쓰기 페이지에 있음
                write_url = page.url
            else:
                # 직접 로그인 후 글쓰기 이동
                await login_with_password(page)
                write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
                await page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

            print(f"\n📝 글쓰기 페이지: {page.url[:60]}")
            await save_debug(page, "editor")

            # ── 제목 ─────────────────────────────────────────────────
            print(f"📌 제목: {title}")
            for sel in ["#post-title-inp", "input.tf_subject", "input[placeholder*='제목']"]:
                try:
                    inp = page.locator(sel).first
                    await inp.wait_for(state="visible", timeout=5000)
                    await inp.fill(title)
                    print(f"  ✅ {sel}")
                    break
                except Exception:
                    continue

            # ── HTML 모드 ─────────────────────────────────────────────
            print("🔄 HTML 모드...")
            for sel in ["button:has-text('HTML')", ".btn_html", "[data-mode='html']"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    print(f"  ✅ {sel}")
                    break
                except Exception:
                    continue

            # ── 본문 ─────────────────────────────────────────────────
            print("📄 본문 입력...")
            content_injected = False

            for frame in page.frames:
                try:
                    result = await frame.evaluate(f"""
                        (function() {{
                            const cm = document.querySelector('.CodeMirror');
                            if (cm && cm.CodeMirror) {{
                                cm.CodeMirror.setValue({json.dumps(content_html)});
                                return 'codemirror';
                            }}
                            return null;
                        }})();
                    """)
                    if result:
                        print(f"  ✅ CodeMirror (iframe): {frame.url[:40]}")
                        content_injected = True
                        break
                except Exception:
                    continue

            if not content_injected:
                try:
                    result = await page.evaluate(f"""
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
                        print("  ✅ CodeMirror (메인)")
                        content_injected = True
                except Exception:
                    pass

            if not content_injected:
                for sel in ["textarea#content", "textarea"]:
                    try:
                        ta = page.locator(sel).first
                        await ta.wait_for(state="visible", timeout=3000)
                        await ta.fill(content_html)
                        print(f"  ✅ textarea: {sel}")
                        content_injected = True
                        break
                    except Exception:
                        continue

            print(f"  {'✅' if content_injected else '⚠️'} 본문 {'완료' if content_injected else '실패'}")
            await page.wait_for_timeout(1000)

            # ── 태그 ─────────────────────────────────────────────────
            if tags:
                for sel in ["#tag-label", "input.tf_tag", "input[placeholder*='태그']"]:
                    try:
                        tag_inp = page.locator(sel).first
                        await tag_inp.wait_for(state="visible", timeout=5000)
                        for tag in tags[:10]:
                            await tag_inp.fill(tag)
                            await tag_inp.press("Enter")
                            await page.wait_for_timeout(300)
                        print("  ✅ 태그 완료")
                        break
                    except Exception:
                        continue

            # ── 발행 ─────────────────────────────────────────────────
            print("🚀 발행...")
            for sel in ["#publish-layer-btn", "button.btn_publish", "button:has-text('발행')"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    print(f"  ✅ 발행 버튼: {sel}")
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
                    print(f"  ✅ 최종 발행: {sel}")
                    break
                except Exception:
                    continue

            try:
                await page.wait_for_url(f"**/{TISTORY_BLOG}.tistory.com/**", timeout=20000)
            except PlaywrightTimeout:
                pass

            post_url = page.url
            await page.screenshot(path="success_screenshot.png")
            print(f"\n🎉 완료: {post_url}")

            await notify_discord(
                f"✅ **티스토리 자동 포스팅 완료!**\n"
                f"📌 제목: {title}\n"
                f"🔗 URL: {post_url}"
            )
            return post_url

        except Exception as e:
            print(f"\n❌ 실패: {e}")
            await save_debug(page, "error_final")
            await notify_discord(f"❌ **티스토리 포스팅 실패**\n오류: {str(e)}")
            raise
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
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
