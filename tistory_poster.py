"""
tistory_poster.py
Playwright 기반 티스토리 자동 포스팅
- 카카오 간편로그인 (계정 선택 화면) 대응
- CodeMirror HTML 에디터 입력
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

            # ── STEP 2: 카카오 로그인 버튼 클릭 ─────────────────────
            print("🟡 카카오 로그인 버튼 클릭...")
            for sel in [".btn_login.link_kakao_id", "a[href*='kakao']", "button:has-text('카카오')"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    print(f"  ✅ 클릭 성공: {sel}")
                    break
                except Exception:
                    continue

            # ── STEP 3: 카카오 페이지 안정화 대기 ───────────────────
            # wait_for_url 대신 networkidle로 대기 (이미 kakao.com에 있을 수 있음)
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            current_url = page.url
            print(f"  📍 현재 URL: {current_url[:80]}...")

            # ── STEP 4: 계정 선택 화면 처리 ─────────────────────────
            # "로그인할 카카오계정 선택" 팝업이 뜨는 경우
            # → 저장된 계정 클릭 또는 "새로운 계정으로 로그인" 클릭
            try:
                # 저장된 계정 목록에서 이메일 매칭 클릭
                account_btn = page.locator(f"a:has-text('{KAKAO_EMAIL}'), button:has-text('{KAKAO_EMAIL}')")
                await account_btn.wait_for(state="visible", timeout=4000)
                await account_btn.click()
                print(f"  ✅ 저장된 계정 선택: {KAKAO_EMAIL}")
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
            except Exception:
                # 계정 선택 화면이 없거나 이메일 매칭 실패 → 일반 로그인 폼으로 진행
                print("  ℹ️ 저장된 계정 선택 화면 없음 → 직접 로그인 시도")

            # ── STEP 5: 로그인 폼 처리 (계정 선택 후에도 비번 요구할 수 있음) ──
            current_url = page.url
            print(f"  📍 로그인 후 URL: {current_url[:80]}...")

            if "tistory.com" not in current_url:
                # 아직 카카오 로그인 폼이 남아있는 경우
                print("  📧 이메일/비밀번호 직접 입력...")

                # 이메일 입력 (필드가 없으면 skip)
                for sel in ["#loginId--1", "input[name='loginId']", "input[type='email']"]:
                    try:
                        inp = page.locator(sel).first
                        await inp.wait_for(state="visible", timeout=3000)
                        val = await inp.input_value()
                        if not val:  # 비어있을 때만 입력
                            await inp.fill(KAKAO_EMAIL)
                        print(f"  ✅ 이메일 입력: {sel}")
                        break
                    except Exception:
                        continue

                # 비밀번호 입력
                for sel in ["#password--2", "input[name='password']", "input[type='password']"]:
                    try:
                        inp = page.locator(sel).first
                        await inp.wait_for(state="visible", timeout=3000)
                        await inp.fill(KAKAO_PASSWORD)
                        print(f"  ✅ 비밀번호 입력: {sel}")
                        break
                    except Exception:
                        continue

                # 로그인 버튼
                for sel in [".btn_g.highlight.submit", "button[type='submit']", "button.submit"]:
                    try:
                        btn = page.locator(sel).first
                        await btn.wait_for(state="visible", timeout=3000)
                        await btn.click()
                        print(f"  ✅ 로그인 버튼 클릭: {sel}")
                        break
                    except Exception:
                        continue

                await page.wait_for_url("**/tistory.com/**", timeout=20000)

            print("✅ 티스토리 로그인 성공!")

            # ── STEP 6: 글쓰기 페이지 ───────────────────────────────
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
                    print(f"  ✅ 제목 입력: {sel}")
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
                    print(f"  ✅ HTML 모드 전환: {sel}")
                    break
                except Exception:
                    continue

            # ── STEP 9: 본문 입력 ────────────────────────────────────
            print("📄 본문 입력...")
            injected = await page.evaluate(f"""
                (function() {{
                    const cm = document.querySelector('.CodeMirror');
                    if (cm && cm.CodeMirror) {{
                        cm.CodeMirror.setValue({json.dumps(content_html)});
                        return 'codemirror';
                    }}
                    const ta = document.querySelector('#content, textarea.editor');
                    if (ta) {{
                        ta.value = {json.dumps(content_html)};
                        ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                        return 'textarea';
                    }}
                    return 'not_found';
                }})();
            """)
            print(f"  ✅ 본문 입력 방식: {injected}")
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
                        print(f"  ✅ 태그 입력 완료")
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
                    print(f"  ✅ 발행 버튼 클릭: {sel}")
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
                    print(f"  ✅ 최종 발행 확인: {sel}")
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
            # 디버깅용 HTML 저장
            html = await page.content()
            with open("error_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  📸 스크린샷 저장: error_screenshot.png")
            print(f"  📄 페이지 HTML 저장: error_page.html")
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
