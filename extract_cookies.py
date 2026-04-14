"""
extract_cookies.py
GitHub Actions에서 실행 — 카카오 로그인 후 쿠키를 cookies.json으로 저장
추가인증이 떠도 비밀번호 입력까지만 하고 쿠키를 최대한 추출
"""

import asyncio
import json
import os
from playwright.async_api import async_playwright

KAKAO_EMAIL    = os.environ["KAKAO_EMAIL"]
KAKAO_PASSWORD = os.environ["KAKAO_PASSWORD"]
TISTORY_BLOG   = os.environ["TISTORY_BLOG"]


async def extract():
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

        # Step 1: 티스토리 로그인
        print("🔑 티스토리 로그인...")
        await page.goto("https://www.tistory.com/auth/login",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Step 2: 카카오 버튼
        await page.click(".btn_login.link_kakao_id")
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        print(f"  📍 {page.url[:70]}")

        # Step 3: 이메일 입력
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

        # Step 4: 비밀번호 입력
        for sel in ["#password--2", "input[name='password']", "input[type='password']"]:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=5000)
                await el.fill(KAKAO_PASSWORD)
                print(f"  ✅ 비밀번호: {sel}")
                break
            except Exception:
                continue

        # Step 5: 로그인 버튼
        for sel in [".btn_g.highlight.submit", "button[type='submit']", ".submit"]:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(state="visible", timeout=3000)
                await btn.click()
                print(f"  ✅ 로그인 버튼: {sel}")
                break
            except Exception:
                continue

        # Step 6: 결과 대기 (추가인증이 와도 30초 대기)
        print("  ⏳ 최대 30초 대기...")
        try:
            await page.wait_for_url("**/tistory.com/**", timeout=30000)
            print(f"  ✅ 티스토리 도달: {page.url[:60]}")
        except Exception:
            print(f"  ⚠️ 타임아웃 — 현재 URL: {page.url[:80]}")
            print("     추가인증이 필요한 상태일 수 있습니다.")

        # Step 7: 쿠키 수집 (어느 단계든 저장)
        cookies = await context.cookies([
            "https://www.tistory.com",
            "https://accounts.kakao.com",
            "https://kauth.kakao.com",
        ])

        with open("cookies.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 쿠키 {len(cookies)}개 저장 → cookies.json")
        print("\n📋 다음 단계:")
        print("   1. Actions 아티팩트에서 tistory-cookies 다운로드")
        print("   2. cookies.json 파일 열어서 전체 내용 복사")
        print("   3. GitHub Secrets → TISTORY_COOKIES 에 붙여넣기")

        # 쿠키 미리보기
        tistory_cookies = [c for c in cookies if "tistory" in c.get("domain", "")]
        kakao_cookies   = [c for c in cookies if "kakao" in c.get("domain", "")]
        print(f"\n   티스토리 쿠키: {len(tistory_cookies)}개")
        print(f"   카카오 쿠키:   {len(kakao_cookies)}개")

        await page.screenshot(path="cookie_extraction.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(extract())
