"""
tistory_poster.py
Playwright 기반 티스토리 자동 포스팅 스크립트
카카오 계정으로 로그인 → HTML 모드로 포스트 작성 → 발행
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
                "--disable-blink-features=AutomationControlled",  # 봇 감지 우회
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

        # navigator.webdriver 숨기기 (카카오 봇 감지 우회)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        try:
            # ── STEP 1: 티스토리 로그인 페이지 ──────────────────────
            print("🔑 티스토리 로그인 시작...")
            await page.goto(
                "https://www.tistory.com/auth/login",
                wait_until="domcontentloaded",
                timeout=30000
            )
            await page.wait_for_timeout(2000)

            # ── STEP 2: 카카오 로그인 버튼 클릭 ────────────────────
            # 여러 셀렉터를 순서대로 시도
            kakao_btn_selectors = [
                ".btn_login.link_kakao_id",
                "a.btn_login[href*='kakao']",
                "a[href*='kakao']",
                "button:has-text('카카오')",
                ".kakao_login",
            ]
            clicked = False
            for sel in kakao_btn_selectors:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=3000)
                    await btn.click()
                    clicked = True
                    print(f"✅ 카카오 버튼 클릭 성공: {sel}")
                    break
                except Exception:
                    continue

            if not clicked:
                # 스크린샷 찍고 페이지 HTML 덤프
                await page.screenshot(path="error_screenshot.png")
                html = await page.content()
                print("❌ 카카오 버튼을 찾지 못했습니다. 페이지 HTML(앞 2000자):")
                print(html[:2000])
                raise Exception("카카오 로그인 버튼을 찾지 못했습니다.")

            # 카카오 로그인 페이지 로드 대기
            await page.wait_for_url("**/kakao.com/**", timeout=20000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)
            print(f"📍 현재 URL: {page.url}")

            # ── STEP 3: 카카오 이메일 입력 ──────────────────────────
            print("📧 카카오 계정 입력 중...")
            email_selectors = ["#loginId--1", "input[name='loginId']", "input[type='email']", "#id_email_2"]
            for sel in email_selectors:
                try:
                    inp = page.locator(sel).first
                    await inp.wait_for(state="visible", timeout=3000)
                    await inp.fill(KAKAO_EMAIL)
                    print(f"✅ 이메일 입력 성공: {sel}")
                    break
                except Exception:
                    continue

            # ── STEP 4: 카카오 비밀번호 입력 ────────────────────────
            pw_selectors = ["#password--2", "input[name='password']", "input[type='password']"]
            for sel in pw_selectors:
                try:
                    inp = page.locator(sel).first
                    await inp.wait_for(state="visible", timeout=3000)
                    await inp.fill(KAKAO_PASSWORD)
                    print(f"✅ 비밀번호 입력 성공: {sel}")
                    break
                except Exception:
                    continue

            # ── STEP 5: 로그인 버튼 클릭 ────────────────────────────
            login_btn_selectors = [
                ".btn_g.highlight.submit",
                "button[type='submit']",
                "button.submit",
                "input[type='submit']",
            ]
            for sel in login_btn_selectors:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=3000)
                    await btn.click()
                    print(f"✅ 로그인 버튼 클릭: {sel}")
                    break
                except Exception:
                    continue

            # 티스토리로 리다이렉트 대기
            await page.wait_for_url("**/tistory.com/**", timeout=20000)
            print("✅ 로그인 성공!")

            # ── STEP 6: 글쓰기 페이지 이동 ──────────────────────────
            write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
            print(f"📝 글쓰기 이동: {write_url}")
            await page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # ── STEP 7: 제목 입력 ────────────────────────────────────
            print(f"📌 제목 입력: {title}")
            for sel in ["#post-title-inp", "input.tf_subject", "input[placeholder*='제목']"]:
                try:
                    inp = page.locator(sel).first
                    await inp.wait_for(state="visible", timeout=5000)
                    await inp.fill(title)
                    print(f"✅ 제목 입력 성공: {sel}")
                    break
                except Exception:
                    continue

            # ── STEP 8: HTML 모드 전환 ────────────────────────────────
            print("🔄 HTML 모드 전환...")
            for sel in ["button:has-text('HTML')", ".btn_html", "[data-mode='html']"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    print(f"✅ HTML 모드 전환: {sel}")
                    break
                except Exception:
                    continue

            # ── STEP 9: 본문 입력 (CodeMirror) ───────────────────────
            print("📄 본문 입력 중...")
            injected = await page.evaluate(f"""
                (function() {{
                    // CodeMirror 에디터
                    const cm = document.querySelector('.CodeMirror');
                    if (cm && cm.CodeMirror) {{
                        cm.CodeMirror.setValue({json.dumps(content_html)});
                        return 'codemirror';
                    }}
                    // textarea fallback
                    const ta = document.querySelector('#content, textarea.editor');
                    if (ta) {{
                        ta.value = {json.dumps(content_html)};
                        ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                        return 'textarea';
                    }}
                    return 'not_found';
                }})();
            """)
            print(f"✅ 본문 입력 방식: {injected}")
            await page.wait_for_timeout(1000)

            # ── STEP 10: 태그 입력 ───────────────────────────────────
            if tags:
                print(f"🏷️ 태그 입력: {tags[:10]}")
                for sel in ["#tag-label", "input.tf_tag", "input[placeholder*='태그']"]:
                    try:
                        tag_inp = page.locator(sel).first
                        await tag_inp.wait_for(state="visible", timeout=5000)
                        for tag in tags[:10]:
                            await tag_inp.fill(tag)
                            await tag_inp.press("Enter")
                            await page.wait_for_timeout(300)
                        print(f"✅ 태그 입력 성공: {sel}")
                        break
                    except Exception:
                        continue

            # ── STEP 11: 발행 ─────────────────────────────────────────
            print("🚀 발행 중...")
            for sel in ["#publish-layer-btn", "button.btn_publish", "button:has-text('발행')"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    print(f"✅ 발행 버튼 클릭: {sel}")
                    break
                except Exception:
                    continue

            # 공개 설정
            try:
                await page.locator("input[value='20']").check(timeout=3000)
            except Exception:
                pass

            # 최종 발행 확인
            for sel in ["#publish-btn", "button.btn_ok", "button:has-text('완료')"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    print(f"✅ 최종 발행 확인: {sel}")
                    break
                except Exception:
                    continue

            await page.wait_for_url(f"**/{TISTORY_BLOG}.tistory.com/**", timeout=20000)
            post_url = page.url
            print(f"🎉 발행 완료: {post_url}")

            await notify_discord(
                f"✅ **티스토리 자동 포스팅 완료!**\n"
                f"📌 제목: {title}\n"
                f"🔗 URL: {post_url}"
            )
            return post_url

        except Exception as e:
            print(f"❌ 포스팅 실패: {e}")
            await page.screenshot(path="error_screenshot.png")
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
