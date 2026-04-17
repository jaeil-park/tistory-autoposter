"""run.py - 메인 실행 스크립트"""

import os
import sys
from generate_post  import generate_post, generate_product_post, save_output
from tistory_poster import post_to_tistory

COUPANG_URL = os.getenv("COUPANG_URL", "")
POST_TOPIC  = os.getenv("POST_TOPIC", "")
POST_TYPE   = os.getenv("POST_TYPE", "review")
CATEGORY_ID = os.getenv("TISTORY_CATEGORY_ID", "0")


def main():
    coupang_url = COUPANG_URL or (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("http") else "")
    topic       = POST_TOPIC  or (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("http") else "")

    if not coupang_url and not topic:
        print("❌ POST_TOPIC 또는 COUPANG_URL을 설정해주세요.")
        sys.exit(1)

    mode = f"쿠팡 {POST_TYPE} 포스팅: {coupang_url[:50]}" if coupang_url else f"블로그 포스팅: {topic}"
    print(f"\n🚀 {mode}\n{'='*50}")

    print("\n[1/2] 📝 포스트 생성 중...")
    if coupang_url:
        post_data = generate_product_post(coupang_url, POST_TYPE)
    else:
        post_data = generate_post(topic)
    save_output(post_data)

    print("\n[2/2] 📤 Notion 저장 + 발행...")
    post_url = post_to_tistory(
        title        = post_data["title"],
        content_html = post_data["content_html"],
        tags         = post_data.get("tags", []),
        category_id  = CATEGORY_ID
    )

    print(f"\n{'='*50}\n🎉 완료! → {post_url}\n{'='*50}")


if __name__ == "__main__":
    main()
