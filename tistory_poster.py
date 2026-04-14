"""
tistory_poster.py - v5
핵심 수정:
- 카카오 간편로그인 계정 선택 화면 → 첫 번째 계정 무조건 클릭
- 매 단계 URL 출력으로 흐름 추적
"""

import asyncio
import os
import json
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

KAKAO_EMAIL     = os.environ["KAKAO_EMAIL"]
KAKAO_PASSWORD  = os.environ["KAKAO_PASSWORD"]
TISTORY_BLOG    = os.environ["TISTORY_BLOG"]
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")


async def notify_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        await session.post(DISCORD_WEBHOOK, json={"content": message})


async def kakao_login(page):
    """카카오 간편로그인 전체 플로우"""

    # Step 1: 티스토리 로그인 페이지
    print("🔑 티스토리 로그인 페이지...")
    await page.goto("https://www.tistory.com/auth/login",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # Step 2: 카카오 버튼 클릭
    print("🟡 카카오 버튼 클릭...")
    await page.locator(".btn_login.link_kakao_id").click()
    await page.wait_for_load_state("domcontentloaded", timeout=15000)
    await page.wait_for_timeout(2000)
    print(f"  📍 URL: {page.url[:80]}")

    # Step 3: 페이지 스냅샷 저장 (로그인 화면 구조 파악)
    with open("kakao_login_page.html", "w", encoding="utf-8") as f:
        f.write(await page.content())
    print("  📄 kakao_login_page.html 저장")

    # Step 4: 화면 유형 판별 후 처리
    url = page.url

    if "login/simple" in url or "select_account" in url:
        # ── 간편로그인 계정 선택 화면 ──────────────────────────
        print("  👤 간편로그인 계정 선택 화면 → 첫 번째 계정 클릭...")
        await page.screenshot(path="kakao_select.png")

        # 계정 선택 버튼들 (다양한 셀렉터 시도)
        clicked = False
        selectors = [
            # 계정 목록 아이템
            ".list_account > li:first-child a",
            ".item_account:first-child",
            "ul.list_account li:first-child",
            # 로그인 버튼 형태
            ".btn_account",
            "[class*='account']:first-child",
            # 일반 링크/버튼
            "a.link_account",
            "button.btn_account",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=3000)
                await el.click()
                print(f"  ✅ 계정 클릭: {sel}")
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            # 마지막 수단: 페이지에서 클릭 가능한 첫 번째 요소
            print("  ⚠️ 셀렉터 전부 실패 → JS로 첫 계정 클릭 시도...")
            await page.evaluate("""
                const links = document.querySelectorAll('a, button');
                for (const el of links) {
                    if (el.offsetParent && el.innerText.trim().length > 0) {
                        el.click();
                        break;
                    }
                }
            """)

        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        print(f"  📍 계정 선택 후 URL: {page.url[:80]}")

    # Step 5: 비밀번호 입력 화면 처리
    url = page.url
    print(f"  🔐 비밀번호 화면 확인... URL: {url[:80]}")

    # 비밀번호 필드 대기
    pw_input = None
    for sel in ["#password--2", "input[name='password']", "input[type='password']"]:
        try:
            el = page.locator(sel).first
            await el.wait_for(state="visible", timeout=5000)
            pw_input = el
            print(f"  ✅ 비밀번호 필드: {sel}")
            break
        except Exception:
            continue

    if pw_input is None:
        # 비밀번호 없이 바로 tistory로 넘어간 경우 (자동 로그인)
        print("  ℹ️ 비밀번호 필드 없음 → 자동 로그인 시도 중...")
        await page.wait_for_timeout(3000)
    else:
        await pw_input.fill(KAKAO_PASSWORD)
        print("  ✅ 비밀번호 입력 완료")

        # 로그인 버튼 클릭
        for sel in [".btn_g.highlight.submit", "button[type='submit']", "button.submit", ".submit"]:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(state="visible", timeout=3000)
                await btn.click()
                print(f"  ✅ 로그인 버튼: {sel}")
                break
            except Exception:
                continue

    # Step 6: tistory.com 리다이렉트 대기
    print("  ⏳ 티스토리 리다이렉트 대기...")
    await page.wait_for_url("**/tistory.com/**", timeout=30000)
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(1000)
    print(f"✅ 로그인 완료! URL: {page.url[:60]}")


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
            await kakao_login(page)

            # ── 글쓰기 ──────────────────────────────────────────
            write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
            print(f"\n📝 글쓰기 이동: {write_url}")
            await page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            with open("editor_snapshot.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            print("  📄 editor_snapshot.html 저장")

            # ── 제목 ──────────────────────────────────────────
            print(f"📌 제목: {title}")
            for sel in ["#post-title-inp", "input.tf_subject", "input[placeholder*='제목']"]:
                try:
                    inp = page.locator(sel).first
                    await inp.wait_for(state="visible", timeout=5000)
                    await inp.fill(title)
                    print(f"  ✅ 제목: {sel}")
                    break
                except Exception:
                    continue

            # ── HTML 모드 ──────────────────────────────────────
            print("🔄 HTML 모드...")
            for sel in ["button:has-text('HTML')", ".btn_html", "[data-mode='html']"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    print(f"  ✅ HTML 모드: {sel}")
                    break
                except Exception:
                    continue

            # ── 본문 입력 ──────────────────────────────────────
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
                        print(f"  ✅ CodeMirror (iframe): {frame.url[:50]}")
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

            print(f"  {'✅' if content_injected else '⚠️'} 본문 입력 {'완료' if content_injected else '실패'}")
            await page.wait_for_timeout(1000)

            # ── 태그 ──────────────────────────────────────────
            if tags:
                for sel in ["#tag-label", "input.tf_tag", "input[placeholder*='태그']"]:
                    try:
                        tag_inp = page.locator(sel).first
                        await tag_inp.wait_for(state="visible", timeout=5000)
                        for tag in tags[:10]:
                            await tag_inp.fill(tag)
                            await tag_inp.press("Enter")
                            await page.wait_for_timeout(300)
                        print(f"  ✅ 태그 완료")
                        break
                    except Exception:
                        continue

            # ── 발행 ──────────────────────────────────────────
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
            await page.screenshot(path="error_screenshot.png")
            with open("error_page.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
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
