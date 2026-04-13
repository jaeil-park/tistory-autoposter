"""
run.py
generate_post.py + tistory_poster.py를 연결하는 메인 실행 스크립트
GitHub Actions에서 이 파일을 직접 실행
"""

import asyncio
import os
import sys
import json
from generate_post  import generate_post, save_output
from tistory_poster import post_to_tistory

CATEGORY_ID = os.getenv("TISTORY_CATEGORY_ID", "0")


async def main():
    topic = os.getenv("POST_TOPIC") or (sys.argv[1] if len(sys.argv) > 1 else None)

    if not topic:
        print("❌ POST_TOPIC 환경변수 또는 인수를 설정해주세요.")
        sys.exit(1)

    print(f"\n🚀 티스토리 자동 포스팅 시작: '{topic}'\n{'='*50}")

    # 1단계: Claude API로 포스트 생성
    print("\n[1/2] 📝 포스트 생성 중...")
    post_data = generate_post(topic)
    save_output(post_data)

    # 2단계: Playwright로 티스토리 발행
    print("\n[2/2] 🌐 티스토리 발행 중...")
    post_url = await post_to_tistory(
        title       = post_data["title"],
        content_html= post_data["content_html"],
        tags        = post_data.get("tags", []),
        category_id = CATEGORY_ID
    )

    print(f"\n{'='*50}")
    print(f"🎉 전체 완료!")
    print(f"🔗 포스트 URL: {post_url}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    asyncio.run(main())
