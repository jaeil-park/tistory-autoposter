"""
tistory_poster.py - v6
핵심 수정:
- URL 패턴 기반 화면 정확히 판별
- 일반 로그인: 이메일 + 비밀번호 순서대로 입력
- 간편로그인: 계정 선택 후 비밀번호
- 매 단계 스크린샷 저장으로 정확한 디버깅
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


async def save_debug(page, name: str):
    """디버깅용 스크린샷 + HTML 저장"""
    await page.screenshot(path=f"{name}.png")
    with open(f"{name}.html", "w", encoding="utf-8") as f:
        f.write(await page.content())
    print(f"  📸 저장: {name}.png / {name}.html")


async def fill_input(page, selectors: list, value: str, label: str) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            await el.wait_for(state="visible", timeout=3000)
            await el.clear()
            await el.fill(value)
            print(f"  ✅ {label}: {sel}")
            return True
        except Exception:
            continue
    print(f"  ⚠️ {label} 입력 실패")
    return False


async def click_button(page, selectors: list, label: str) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            await el.wait_for(state="visible", timeout=3000)
            await el.click()
            print(f"  ✅ {label}: {sel}")
            return True
        except Exception:
            continue
    print(f"  ⚠️ {label} 클릭 실패")
    return False


async def kakao_login(page):
    """카카오 로그인 — 일반/간편 로그인 모두 대응"""

    # Step 1: 티스토리 로그인
    print("🔑 티스토리 로그인 페이지...")
    await page.goto("https://www.tistory.com/auth/login",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    await save_debug(page, "step1_tistory_login")

    # Step 2: 카카오 버튼 클릭
    print("🟡 카카오 버튼 클릭...")
    await click_button(page, [
        ".btn_login.link_kakao_id",
        "a[href*='kakao']",
        "button:has-text('카카오')",
    ], "카카오 버튼")

    await page.wait_for_load_state("domcontentloaded", timeout=15000)
    await page.wait_for_timeout(2000)
    url = page.url
    print(f"  📍 URL: {url[:90]}")
    await save_debug(page, "step2_after_kakao_btn")

    # Step 3: 화면 유형 판별
    if "login/simple" in url or "prompt=select_account" in url:
        # ── 간편로그인 계정 선택 화면 ──────────────────
        print("  👤 간편로그인 계정 선택 화면")
        await save_debug(page, "step3_simple_login")

        # 페이지 내 모든 a/button 텍스트 로그
        elements_info = await page.evaluate("""
            () => {
                const els = [...document.querySelectorAll('a, button')];
                return els
                    .filter(e => e.offsetParent)
                    .map(e => ({
                        tag: e.tagName,
                        class: e.className,
                        text: e.innerText.trim().substring(0, 50),
                        href: e.href || ''
                    }))
                    .filter(e => e.text.length > 0)
                    .slice(0, 20);
            }
        """)
        print("  📋 페이지 내 클릭 요소:")
        for el in elements_info:
            print(f"     [{el['tag']}] class={el['class'][:30]} text={el['text']}")

        # 이메일 포함된 요소 클릭 시도
        clicked = False
        email_local = KAKAO_EMAIL.split('@')[0]  # @ 앞부분

        for el in elements_info:
            if KAKAO_EMAIL in el['text'] or email_local in el['text']:
                # 해당 텍스트 가진 요소 클릭
                try:
                    await page.get_by_text(el['text']).first.click()
                    print(f"  ✅ 이메일 매칭 클릭: {el['text'][:40]}")
                    clicked = True
                    break
                except Exception:
                    continue

        if not clicked:
            # 첫 번째 계정 클릭 (다양한 셀렉터)
            for sel in [
                "li:first-child a", "li:first-child button",
                ".list_account li:first-child a",
                ".account_list li:first-child",
                "[class*='item']:first-child",
                "[class*='account']:first-child",
            ]:
                try:
                    el = page.locator(sel).first
                    await el.wait_for(state="visible", timeout=2000)
                    await el.click()
                    print(f"  ✅ 첫 계정 클릭: {sel}")
                    clicked = True
                    break
                except Exception:
                    continue

        if not clicked:
            print("  ⚠️ 계정 선택 실패 → 새 계정으로 로그인 클릭 시도")
            for sel in ["a:has-text('새로운 계정')", "button:has-text('새로운 계정')", "a:has-text('다른 계정')"]:
                try:
                    await page.locator(sel).first.click()
                    print(f"  ✅ 새 계정 로그인: {sel}")
                    break
                except Exception:
                    continue

        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await page.wait_for_timeout(2000)
        url = page.url
        print(f"  📍 계정 선택 후: {url[:90]}")
        await save_debug(page, "step3b_after_account_select")

    # Step 4: 로그인 폼 처리 (이메일 + 비밀번호)
    print("  📝 로그인 폼 입력...")
    await save_debug(page, "step4_login_form")

    # 이메일 필드 (비어있으면 입력)
    email_selectors = ["#loginId--1", "input[name='loginId']", "input[type='email']", "input[name='email']"]
    for sel in email_selectors:
        try:
            el = page.locator(sel).first
            await el.wait_for(state="visible", timeout=3000)
            val = await el.input_value()
            if not val:
                await el.fill(KAKAO_EMAIL)
                print(f"  ✅ 이메일 입력: {sel}")
            else:
                print(f"  ℹ️ 이메일 이미 입력됨: {val[:20]}")
            break
        except Exception:
            continue

    # 비밀번호 입력
    pw_selectors = ["#password--2", "input[name='password']", "input[type='password']"]
    pw_ok = await fill_input(page, pw_selectors, KAKAO_PASSWORD, "비밀번호")

    if not pw_ok:
        print("  ⚠️ 비밀번호 필드 없음 → 자동 로그인 가능성")

    # 로그인 버튼
    await click_button(page, [
        ".btn_g.highlight.submit",
        "button[type='submit']",
        "button.submit",
        ".submit",
        "input[type='submit']",
    ], "로그인 버튼")

    await page.wait_for_timeout(2000)
    await save_debug(page, "step5_after_login_submit")
    print(f"  📍 로그인 제출 후: {page.url[:90]}")

    # Step 5: tistory.com 리다이렉트 대기
    print("  ⏳ 티스토리 리다이렉트 대기...")
    await page.wait_for_url("**/tistory.com/**", timeout=30000)
    await page.wait_for_load_state("domcontentloaded")
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

            # 글쓰기
            write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost/"
            print(f"\n📝 글쓰기: {write_url}")
            await page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await save_debug(page, "step6_editor")

            # 제목
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

            # HTML 모드
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

            # 본문 입력
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
                        print(f"  ✅ CodeMirror (iframe)")
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
                        print("  ✅ 태그 완료")
                        break
                    except Exception:
                        continue

            # 발행
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
