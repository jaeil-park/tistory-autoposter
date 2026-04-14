"""
run.py - 메인 실행 스크립트
generate_post.py + tistory_poster.py 연결
"""

import os
import sys
from generate_post  import generate_post, save_output
from tistory_poster import post_to_tistory

CATEGORY_ID = os.getenv("TISTORY_CATEGORY_ID", "0")


def main():
    topic = os.getenv("POST_TOPIC") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not topic:
        print("❌ POST_TOPIC 환경변수 또는 인수를 설정해주세요.")
        sys.exit(1)

    print(f"\n🚀 티스토리 자동 포스팅 시작: '{topic}'\n{'='*50}")

    print("\n[1/2] 📝 포스트 생성 중...")
    post_data = generate_post(topic)
    save_output(post_data)

    print("\n[2/2] 🌐 티스토리 발행 중...")
    post_url = post_to_tistory(
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
    main()
