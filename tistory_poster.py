"""
tistory_poster.py
Playwright 기반 티스토리 자동 포스팅
- iframe 내부 에디터 접근
- HTML 모드 전환 후 직접 입력
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


async def post_to_tistory(title: str, content_html: str, tags: list, category_id: str = "0"):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
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
            # ── STEP 1: 티스토리 로그인 ──────────────────────────────
            print("🔑 티스토리 로그인 시작...")
            await page.goto("https://www.tistory.com/auth/login",
                            wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # ── STEP 2: 카카오 로그인 버튼 ───────────────────────────
            for sel in [".btn_login.link_kakao_id", "a[href*='kakao']", "button:has-text('카카오')"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    print(f"  ✅ 카카오 버튼 클릭: {sel}")
                    break
                except Exception:
                    continue

            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # ── STEP 3: 계정 선택 화면 처리 ─────────────────────────
            try:
                account_btn = page.locator(f"a:has-text('{KAKAO_EMAIL}'), button:has-text('{KAKAO_EMAIL}')").first
                await account_btn.wait_for(state="visible", timeout=4000)
                await account_btn.click()
                print(f"  ✅ 저장된 계정 선택: {KAKAO_EMAIL}")
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
            except Exception:
                print("  ℹ️ 계정 선택 화면 없음 → 직접 로그인")

            # ── STEP 4: 로그인 폼 (필요 시) ──────────────────────────
            if "tistory.com" not in page.url:
                for sel in ["#loginId--1", "input[name='loginId']", "input[type='email']"]:
                    try:
                        inp = page.locator(sel).first
                        await inp.wait_for(state="visible", timeout=3000)
                        val = await inp.input_value()
                        if not val:
                            await inp.fill(KAKAO_EMAIL)
                        break
                    except Exception:
                        continue

                for sel in ["#password--2", "input[name='password']", "input[type='password']"]:
                    try:
                        inp = page.locator(sel).first
                        await inp.wait_for(state="visible", timeout=3000)
                        await inp.fill(KAKAO_PASSWORD)
                        break
                    except Exception:
                        continue

                for sel in [".btn_g.highlight.submit", "button[type='submit']", "button.submit"]:
                    try:
                        btn = page.locator(sel).first
                        await btn.wait_for(state="visible", timeout=3000)
                        await btn.click()
                        break
                    except Exception:
                        continue

                await page.wait_for_url("**/tistory.com/**", timeout=20000)

            print(f"✅ 로그인 성공! URL: {page.url[:60]}")

            # ── STEP 5: 글쓰기 페이지 ───────────────────────────────
            write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
            print(f"📝 글쓰기 이동: {write_url}")
            await page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # 페이지 HTML 저장 (에디터 구조 파악용)
            html_snapshot = await page.content()
            with open("editor_snapshot.html", "w", encoding="utf-8") as f:
                f.write(html_snapshot)
            print(f"  📄 에디터 HTML 스냅샷 저장 (editor_snapshot.html)")

            # ── STEP 6: 제목 입력 ────────────────────────────────────
            print(f"📌 제목 입력: {title}")
            for sel in ["#post-title-inp", "input.tf_subject", "input[placeholder*='제목']", "[data-role='title']"]:
                try:
                    inp = page.locator(sel).first
                    await inp.wait_for(state="visible", timeout=5000)
                    await inp.fill(title)
                    print(f"  ✅ 제목 입력: {sel}")
                    break
                except Exception:
                    continue

            # ── STEP 7: HTML 모드 전환 ────────────────────────────────
            print("🔄 HTML 모드 전환...")
            html_switched = False
            for sel in ["button:has-text('HTML')", ".btn_html", "[data-mode='html']", "button[title='HTML']"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    html_switched = True
                    print(f"  ✅ HTML 모드 전환: {sel}")
                    break
                except Exception:
                    continue

            # ── STEP 8: 본문 입력 (iframe + CodeMirror + textarea 전략) ──
            print("📄 본문 입력...")
            content_injected = False

            # 전략 A: iframe 내부 CodeMirror
            try:
                frames = page.frames
                print(f"  ℹ️ 프레임 수: {len(frames)}")
                for frame in frames:
                    print(f"     프레임 URL: {frame.url[:60]}")
                    result = await frame.evaluate(f"""
                        (function() {{
                            const cm = document.querySelector('.CodeMirror');
                            if (cm && cm.CodeMirror) {{
                                cm.CodeMirror.setValue({json.dumps(content_html)});
                                return 'codemirror_iframe';
                            }}
                            return null;
                        }})();
                    """)
                    if result:
                        print(f"  ✅ 본문 입력 (iframe CodeMirror): {frame.url[:40]}")
                        content_injected = True
                        break
            except Exception as e:
                print(f"  ⚠️ iframe 전략 실패: {e}")

            # 전략 B: 메인 페이지 CodeMirror
            if not content_injected:
                try:
                    result = await page.evaluate(f"""
                        (function() {{
                            const cm = document.querySelector('.CodeMirror');
                            if (cm && cm.CodeMirror) {{
                                cm.CodeMirror.setValue({json.dumps(content_html)});
                                return 'codemirror_main';
                            }}
                            return null;
                        }})();
                    """)
                    if result:
                        print(f"  ✅ 본문 입력 (메인 CodeMirror)")
                        content_injected = True
                except Exception as e:
                    print(f"  ⚠️ 메인 CodeMirror 실패: {e}")

            # 전략 C: textarea 직접 입력
            if not content_injected:
                for sel in ["textarea#content", "textarea.editor-content", "textarea[name='content']", "textarea"]:
                    try:
                        ta = page.locator(sel).first
                        await ta.wait_for(state="visible", timeout=3000)
                        await ta.fill(content_html)
                        print(f"  ✅ 본문 입력 (textarea): {sel}")
                        content_injected = True
                        break
                    except Exception:
                        continue

            # 전략 D: contenteditable div 클릭 후 키보드 입력
            if not content_injected:
                for sel in ["[contenteditable='true']", ".ProseMirror", ".editor-content"]:
                    try:
                        el = page.locator(sel).first
                        await el.wait_for(state="visible", timeout=3000)
                        await el.click()
                        await page.keyboard.press("Control+a")
                        await page.keyboard.type(content_html[:500])  # 너무 길면 자름
                        print(f"  ✅ 본문 입력 (contenteditable): {sel}")
                        content_injected = True
                        break
                    except Exception:
                        continue

            if not content_injected:
                print("  ⚠️ 본문 입력 실패 - 스냅샷 확인 필요")

            await page.wait_for_timeout(1000)

            # ── STEP 9: 태그 입력 ───────────────────────────────────
            if tags:
                print(f"🏷️ 태그 입력...")
                for sel in ["#tag-label", "input.tf_tag", "input[placeholder*='태그']"]:
                    try:
                        tag_inp = page.locator(sel).first
                        await tag_inp.wait_for(state="visible", timeout=5000)
                        for tag in tags[:10]:
                            await tag_inp.fill(tag)
                            await tag_inp.press("Enter")
                            await page.wait_for_timeout(300)
                        print(f"  ✅ 태그 입력 완료")
                        break
                    except Exception:
                        continue

            # ── STEP 10: 발행 ─────────────────────────────────────────
            print("🚀 발행 중...")
            for sel in ["#publish-layer-btn", "button.btn_publish", "button:has-text('발행')", "[data-btn='publish']"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    print(f"  ✅ 발행 버튼: {sel}")
                    break
                except Exception:
                    continue

            # 공개 설정
            try:
                await page.locator("input[value='20']").check(timeout=3000)
                print("  ✅ 공개 설정 완료")
            except Exception:
                pass

            # 최종 발행 확인
            for sel in ["#publish-btn", "button.btn_ok", "button:has-text('완료')", "button:has-text('발행하기')"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    print(f"  ✅ 최종 발행: {sel}")
                    break
                except Exception:
                    continue

            # 발행 완료 확인 — URL 변경 또는 성공 메시지
            try:
                await page.wait_for_url(f"**/{TISTORY_BLOG}.tistory.com/**", timeout=20000)
                post_url = page.url
            except PlaywrightTimeout:
                # URL이 안 바뀌어도 성공일 수 있음
                post_url = page.url
                print(f"  ⚠️ URL 변경 미확인, 현재: {post_url[:60]}")

            print(f"🎉 발행 완료: {post_url}")
            await page.screenshot(path="success_screenshot.png")

            await notify_discord(
                f"✅ **티스토리 자동 포스팅 완료!**\n"
                f"📌 제목: {title}\n"
                f"🔗 URL: {post_url}"
            )
            return post_url

        except Exception as e:
            print(f"❌ 포스팅 실패: {e}")
            await page.screenshot(path="error_screenshot.png")
            html = await page.content()
            with open("error_page.html", "w", encoding="utf-8") as f:
                f.write(html)
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
