"""
save_cookies.py
로컬에서 한 번 실행해서 카카오 로그인 쿠키를 저장
저장된 cookies.json을 GitHub Secrets에 등록
"""

import asyncio
import json
import os
from playwright.async_api import async_playwright

KAKAO_EMAIL    = os.getenv("KAKAO_EMAIL", "")
KAKAO_PASSWORD = os.getenv("KAKAO_PASSWORD", "")
TISTORY_BLOG   = os.getenv("TISTORY_BLOG", "")


async def save_login_cookies():
    async with async_playwright() as p:
        # headless=False 로 실제 브라우저 창 띄움 (수동 인증 가능)
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await context.new_page()

        print("🔑 티스토리 로그인 페이지 이동...")
        await page.goto("https://www.tistory.com/auth/login")
        await page.wait_for_timeout(2000)

        # 카카오 버튼 클릭
        await page.click(".btn_login.link_kakao_id")
        await page.wait_for_timeout(2000)

        print("\n⚠️  브라우저에서 직접 카카오 로그인을 완료해주세요.")
        print("   (카카오 인증 포함) 완료 후 티스토리 메인이 뜨면 Enter 를 누르세요.")
        input("   ✅ 로그인 완료 후 Enter: ")

        # 현재 URL 확인
        print(f"   현재 URL: {page.url}")

        # 쿠키 저장
        cookies = await context.cookies()
        with open("cookies.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 쿠키 저장 완료: cookies.json ({len(cookies)}개)")
        print("\n📋 다음 단계:")
        print("   1. cookies.json 내용을 복사")
        print("   2. GitHub Repository → Settings → Secrets → New secret")
        print("   3. Name: TISTORY_COOKIES  Value: (cookies.json 전체 내용 붙여넣기)")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(save_login_cookies())
