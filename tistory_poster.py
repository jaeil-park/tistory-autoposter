"""
tistory_poster.py - v4
핵심 수정:
- 카카오 로그인 완료를 tistory.com URL로 엄격하게 확인
- 계정 선택 → 비밀번호 입력 → tistory 리다이렉트 완전 대기
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
    """카카오 로그인 전체 플로우 처리"""

    # 1. 티스토리 로그인 페이지
    print("🔑 티스토리 로그인 페이지 이동...")
    await page.goto("https://www.tistory.com/auth/login",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # 2. 카카오 로그인 버튼 클릭
    print("🟡 카카오 로그인 버튼 클릭...")
    for sel in [".btn_login.link_kakao_id", "a[href*='kakao']", "button:has-text('카카오')"]:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()
            print(f"  ✅ 클릭: {sel}")
            break
        except Exception:
            continue

    # 3. 카카오 페이지 로드 대기
    await page.wait_for_load_state("domcontentloaded", timeout=15000)
    await page.wait_for_timeout(2000)
    print(f"  📍 현재: {page.url[:70]}")

    # 4. "계정 선택" 화면 처리 (간편로그인 저장 계정)
    # URL에 accounts.kakao.com/login/simple 이 포함되면 계정 선택 화면
    if "login/simple" in page.url or "select_account" in page.url or "prompt=select" in page.url:
        print("  👤 계정 선택 화면 감지 → 저장된 계정 클릭 시도...")
        try:
            # 저장된 계정 버튼 (이메일 텍스트 포함 또는 첫 번째 계정)
            account = page.locator(f"a:has-text('{KAKAO_EMAIL}')").first
            await account.wait_for(state="visible", timeout=5000)
            await account.click()
            print(f"  ✅ 계정 선택: {KAKAO_EMAIL}")
        except Exception:
            # 이메일 매칭 실패 시 첫 번째 계정 클릭
            try:
                first_account = page.locator(".btn_account, .link_account, [class*='account']").first
                await first_account.wait_for(state="visible", timeout=3000)
                await first_account.click()
                print("  ✅ 첫 번째 계정 클릭")
            except Exception:
                print("  ⚠️ 계정 선택 실패 → 비밀번호 직접 입력 시도")

        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await page.wait_for_timeout(1500)
        print(f"  📍 계정 선택 후: {page.url[:70]}")

    # 5. 비밀번호 입력 화면 처리
    print("  🔐 비밀번호 입력 시도...")
    pw_filled = False
    for sel in ["#password--2", "input[name='password']", "input[type='password']"]:
        try:
            inp = page.locator(sel).first
            await inp.wait_for(state="visible", timeout=5000)
            await inp.fill(KAKAO_PASSWORD)
            print(f"  ✅ 비밀번호 입력: {sel}")
            pw_filled = True
            break
        except Exception:
            continue

    if not pw_filled:
        # 이메일도 다시 입력 필요한 경우
        print("  ⚠️ 비밀번호 필드 없음 → 이메일부터 입력 시도...")
        for sel in ["#loginId--1", "input[name='loginId']", "input[type='email']"]:
            try:
                inp = page.locator(sel).first
                await inp.wait_for(state="visible", timeout=3000)
                val = await inp.input_value()
                if not val:
                    await inp.fill(KAKAO_EMAIL)
                print(f"  ✅ 이메일 입력: {sel}")
                break
            except Exception:
                continue

        for sel in ["#password--2", "input[name='password']", "input[type='password']"]:
            try:
                inp = page.locator(sel).first
                await inp.wait_for(state="visible", timeout=5000)
                await inp.fill(KAKAO_PASSWORD)
                print(f"  ✅ 비밀번호 입력: {sel}")
                pw_filled = True
                break
            except Exception:
                continue

    # 6. 로그인 버튼 클릭
    print("  🖱️ 로그인 버튼 클릭...")
    for sel in [".btn_g.highlight.submit", "button[type='submit']", ".submit", "button.submit"]:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=3000)
            await btn.click()
            print(f"  ✅ 로그인 버튼: {sel}")
            break
        except Exception:
            continue

    # 7. tistory.com으로 리다이렉트 될 때까지 대기 (핵심!)
    print("  ⏳ 티스토리 리다이렉트 대기 중...")
    await page.wait_for_url("**/tistory.com/**", timeout=30000)
    await page.wait_for_load_state("domcontentloaded", timeout=10000)
    print(f"✅ 로그인 완료! URL: {page.url[:60]}")


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
            # ── 로그인 ──────────────────────────────────────────────
            await kakao_login(page)

            # ── 글쓰기 ──────────────────────────────────────────────
            write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
            print(f"\n📝 글쓰기 이동: {write_url}")
            await page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # 에디터 구조 스냅샷 저장
            with open("editor_snapshot.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            print("  📄 editor_snapshot.html 저장 완료")

            # ── 제목 입력 ────────────────────────────────────────────
            print(f"📌 제목: {title}")
            for sel in ["#post-title-inp", "input.tf_subject", "input[placeholder*='제목']", "[data-role='title']"]:
                try:
                    inp = page.locator(sel).first
                    await inp.wait_for(state="visible", timeout=5000)
                    await inp.fill(title)
                    print(f"  ✅ 제목 입력: {sel}")
                    break
                except Exception:
                    continue

            # ── HTML 모드 전환 ────────────────────────────────────────
            print("🔄 HTML 모드 전환...")
            for sel in ["button:has-text('HTML')", ".btn_html", "[data-mode='html']", "button[title='HTML']"]:
                try:
                    btn = page.locator(sel).first
                    await btn.wait_for(state="visible", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    print(f"  ✅ HTML 모드: {sel}")
                    break
                except Exception:
                    continue

            # ── 본문 입력 ─────────────────────────────────────────────
            print("📄 본문 입력...")
            content_injected = False

            # 전략 A: iframe 내 CodeMirror
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
                        print(f"  ✅ 본문 입력 (iframe CodeMirror): {frame.url[:50]}")
                        content_injected = True
                        break
                except Exception:
                    continue

            # 전략 B: 메인 CodeMirror
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
                except Exception:
                    pass

            # 전략 C: textarea
            if not content_injected:
                for sel in ["textarea#content", "textarea.editor-content", "textarea"]:
                    try:
                        ta = page.locator(sel).first
                        await ta.wait_for(state="visible", timeout=3000)
                        await ta.fill(content_html)
                        print(f"  ✅ 본문 입력 (textarea): {sel}")
                        content_injected = True
                        break
                    except Exception:
                        continue

            if not content_injected:
                print("  ⚠️ 본문 입력 실패 - editor_snapshot.html 확인 필요")

            await page.wait_for_timeout(1000)

            # ── 태그 입력 ─────────────────────────────────────────────
            if tags:
                print(f"🏷️ 태그: {tags[:10]}")
                for sel in ["#tag-label", "input.tf_tag", "input[placeholder*='태그']"]:
                    try:
                        tag_inp = page.locator(sel).first
                        await tag_inp.wait_for(state="visible", timeout=5000)
                        for tag in tags[:10]:
                            await tag_inp.fill(tag)
                            await tag_inp.press("Enter")
                            await page.wait_for_timeout(300)
                        print("  ✅ 태그 입력 완료")
                        break
                    except Exception:
                        continue

            # ── 발행 ──────────────────────────────────────────────────
            print("🚀 발행...")
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
                print("  ✅ 공개 설정")
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

            # 발행 완료 확인
            try:
                await page.wait_for_url(f"**/{TISTORY_BLOG}.tistory.com/**", timeout=20000)
            except PlaywrightTimeout:
                pass

            post_url = page.url
            await page.screenshot(path="success_screenshot.png")
            print(f"\n🎉 발행 완료: {post_url}")

            await notify_discord(
                f"✅ **티스토리 자동 포스팅 완료!**\n"
                f"📌 제목: {title}\n"
                f"🔗 URL: {post_url}"
            )
            return post_url

        except Exception as e:
            print(f"\n❌ 포스팅 실패: {e}")
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
