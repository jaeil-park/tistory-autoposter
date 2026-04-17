"""
generate_post.py - v2
- 일반 주제 포스팅
- 쿠팡파트너스 링크 → 상품 분석 → 판매/리뷰/바이럴 글 자동 생성
- 대표 이미지 URL 생성 (Unsplash API 활용)
"""

import os
import re
import json
import sys
import requests
import anthropic
from datetime import datetime

ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")  # 선택사항
TOPIC              = os.getenv("POST_TOPIC", "")
COUPANG_URL        = os.getenv("COUPANG_URL", "")   # 쿠팡파트너스 링크

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CATEGORY_MAP = {
    "python":    {"notion_tag": "🐍 Python/개발",   "tistory_id": "0"},
    "langchain": {"notion_tag": "🤖 AI/LangChain",  "tistory_id": "0"},
    "discord":   {"notion_tag": "💬 Discord봇",     "tistory_id": "0"},
    "infra":     {"notion_tag": "🖥️ IT인프라",      "tistory_id": "0"},
    "quant":     {"notion_tag": "📈 퀀트/자동화",   "tistory_id": "0"},
    "linux":     {"notion_tag": "🐧 Linux/Server",  "tistory_id": "0"},
    "docker":    {"notion_tag": "🐳 Docker/DevOps", "tistory_id": "0"},
    "fastapi":   {"notion_tag": "⚡ FastAPI/백엔드","tistory_id": "0"},
    "vue":       {"notion_tag": "🎨 Frontend",      "tistory_id": "0"},
    "product":   {"notion_tag": "🛍️ 상품리뷰",     "tistory_id": "0"},
    "general":   {"notion_tag": "📝 일반",          "tistory_id": "0"},
}

BLOG_SYSTEM_PROMPT = """
당신은 베테랑 IT 엔지니어 재일(jaeil.park)의 티스토리 블로그 포스트 작성 전문가입니다.

## 카테고리 키 목록
python, langchain, discord, infra, quant, linux, docker, fastapi, vue, product, general

## 출력 형식 (순수 JSON, 마크다운 코드블록 없이)
{
  "category_key": "카테고리 키",
  "thumbnail_title": "썸네일 제목 (35자 내외)",
  "image_keyword": "대표 이미지 검색 키워드 (영어 2~3단어, 예: python code laptop)",
  "title": "포스트 제목",
  "content_md": "마크다운 본문 전체",
  "tags": ["태그1", "태그2"],
  "post_type": "tutorial|troubleshooting|devlog|concept|snippet|review|viral",
  "meta_description": "메타 설명 (80자 내외)"
}
"""

PRODUCT_SYSTEM_PROMPT = """
당신은 쿠팡파트너스 상품을 분석해서 블로그 마케팅 글을 작성하는 전문가입니다.

## 글 유형 (post_type에 따라)
- review: 실사용 후기 형태 (장단점, 별점, 총평)
- viral: 바이럴 마케팅 (감성 스토리 + 상품 자연스럽게 녹이기)
- sales: 판매 최적화 (혜택 강조, CTA, 가격 비교)

## 출력 형식 (순수 JSON)
{
  "category_key": "product",
  "thumbnail_title": "썸네일 제목",
  "image_keyword": "영어 상품 키워드 2~3단어",
  "title": "포스트 제목 (SEO 최적화)",
  "content_md": "마크다운 본문 (쿠팡 링크 포함)",
  "tags": ["태그1", "태그2"],
  "post_type": "review|viral|sales",
  "meta_description": "메타 설명"
}

## 중요 규칙
- 본문 내 자연스럽게 쿠팡 구매 링크 2~3회 삽입
- 클릭을 유도하는 CTA 문구 포함
- 광고 느낌 최소화, 실제 사용자 후기처럼 작성
- 본문 **맨 마지막**에 반드시 아래 문구를 추가:
  > 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
"""


def fetch_product_info(url: str) -> dict:
    """쿠팡 상품 페이지에서 기본 정보 파싱"""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        html = resp.text

        # 상품명 파싱
        title_match = re.search(r'<title>([^<]+)</title>', html)
        title = title_match.group(1).strip() if title_match else ""

        # OG 태그에서 상품 정보
        og_title = re.search(r'og:title["\s]+content=["\']([^"\']+)["\']', html)
        og_image = re.search(r'og:image["\s]+content=["\']([^"\']+)["\']', html)
        og_desc  = re.search(r'og:description["\s]+content=["\']([^"\']+)["\']', html)

        # 가격 파싱
        price_match = re.search(r'class="[^"]*price[^"]*"[^>]*>.*?(\d{1,3}(?:,\d{3})+)원', html, re.DOTALL)

        product_info = {
            "url":         url,
            "title":       (og_title.group(1) if og_title else title)[:200],
            "image_url":   og_image.group(1) if og_image else "",
            "description": og_desc.group(1) if og_desc else "",
            "price":       price_match.group(1) + "원" if price_match else "가격 미확인",
        }
        print(f"  📦 상품명: {product_info['title'][:50]}")
        print(f"  💰 가격: {product_info['price']}")
        return product_info

    except Exception as e:
        print(f"  ⚠️ 상품 파싱 실패: {e}")
        return {"url": url, "title": "", "image_url": "", "description": "", "price": ""}


def get_representative_image(keyword: str, fallback_url: str = "") -> str:
    """
    대표 이미지 URL 가져오기
    1순위: 쿠팡 상품 이미지 (상품 포스팅 시)
    2순위: Unsplash API
    3순위: 기본 IT 이미지
    """
    if fallback_url:
        return fallback_url

    if UNSPLASH_ACCESS_KEY and keyword:
        try:
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": keyword, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
                timeout=10
            )
            data = resp.json()
            if data.get("results"):
                url = data["results"][0]["urls"]["regular"]
                print(f"  🖼️ Unsplash 이미지: {url[:60]}")
                return url
        except Exception as e:
            print(f"  ⚠️ Unsplash 실패: {e}")

    # Unsplash 무료 소스 (API 키 없이)
    keyword_encoded = keyword.replace(" ", ",")
    url = f"https://source.unsplash.com/1200x630/?{keyword_encoded}"
    print(f"  🖼️ Unsplash 기본: {url}")
    return url


def _call_api(system: str, user_message: str, max_tokens: int = 8000) -> str:
    for tokens in [max_tokens, 6000, 4000]:
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}]
            )
            if response.stop_reason == "max_tokens":
                continue
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return raw.strip()
        except Exception as e:
            print(f"  ⚠️ API 오류 (tokens={tokens}): {e}")
            continue
    raise RuntimeError("모든 API 시도 실패")


def markdown_to_html(md: str) -> str:
    try:
        import markdown as md_lib
        return md_lib.markdown(md, extensions=["fenced_code", "tables", "toc"])
    except ImportError:
        html = md
        html = re.sub(r"```(\w+)\n(.*?)```", r"<pre><code class='language-\1'>\2</code></pre>", html, flags=re.DOTALL)
        for i in range(6, 0, -1):
            html = re.sub(rf"^{'#'*i} (.+)$", rf"<h{i}>\1</h{i}>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = html.replace("\n\n", "</p><p>")
        return f"<p>{html}</p>"


def generate_product_post(coupang_url: str, post_type: str = "review") -> dict:
    """쿠팡파트너스 링크로 상품 포스팅 생성"""
    print(f"🛍️ 쿠팡 상품 분석 중: {coupang_url[:60]}")

    product_info = fetch_product_info(coupang_url)

    user_message = f"""
다음 쿠팡 상품으로 블로그 포스트를 작성해주세요:

**상품명**: {product_info['title']}
**가격**: {product_info['price']}
**상품설명**: {product_info['description'][:300]}
**구매링크**: {coupang_url}
**글 유형**: {post_type} (review=리뷰, viral=바이럴, sales=판매최적화)

상품 이미지가 있으면 본문 상단에 마크다운 이미지로 삽입하세요.
구매 링크를 자연스럽게 2~3회 본문에 녹여주세요.
순수 JSON만 출력하세요.
"""
    raw = _call_api(PRODUCT_SYSTEM_PROMPT, user_message)
    post_data = json.loads(raw)

    # 카테고리 처리
    post_data["category_key"] = "product"
    post_data["notion_tag"] = CATEGORY_MAP["product"]["notion_tag"]
    post_data["tistory_category_id"] = CATEGORY_MAP["product"]["tistory_id"]

    # 쿠팡파트너스 필수 고지 문구 강제 삽입 (맨 마지막)
    COUPANG_DISCLAIMER = (
        "\n\n---\n"
        "> 이 포스팅은 쿠팡 파트너스 활동의 일환으로, "
        "이에 따른 일정액의 수수료를 제공받습니다."
    )
    content_md = post_data.get("content_md", "")
    if "쿠팡 파트너스 활동의 일환" not in content_md:
        post_data["content_md"] = content_md + COUPANG_DISCLAIMER

    # 대표 이미지 (상품 이미지 우선)
    image_url = get_representative_image(
        post_data.get("image_keyword", "product shopping"),
        fallback_url=product_info.get("image_url", "")
    )
    post_data["representative_image_url"] = image_url

    # HTML 변환 (이미지 최상단 삽입)
    content_md = post_data.get("content_md", "")
    if image_url and not content_md.startswith("!["):
        content_md = f"![대표이미지]({image_url})\n\n" + content_md
        post_data["content_md"] = content_md

    post_data["content_html"] = f'<img src="{image_url}" alt="대표이미지" style="width:100%;max-width:800px;margin-bottom:20px;">\n' + markdown_to_html(content_md)

    print(f"✅ 상품 포스팅 완료: {post_data['title'][:50]}")
    return post_data


def generate_post(topic: str) -> dict:
    """일반 주제 포스팅 생성"""
    print(f"🤖 Claude API로 포스트 생성 중: '{topic}'")

    user_message = f"""
다음 주제로 티스토리 블로그 포스트를 작성해주세요:

**주제**: {topic}

주제를 분석하여 category_key, image_keyword, post_type을 선택하고
실무에 바로 적용 가능한 포스트를 작성하세요.
순수 JSON만 출력하세요. content_html 제외.
"""
    raw = _call_api(BLOG_SYSTEM_PROMPT, user_message)
    post_data = json.loads(raw)

    # 카테고리 처리
    category_key = post_data.get("category_key", "general")
    if category_key not in CATEGORY_MAP:
        category_key = "general"
    cat = CATEGORY_MAP[category_key]
    post_data["category_key"]        = category_key
    post_data["notion_tag"]          = cat["notion_tag"]
    post_data["tistory_category_id"] = cat["tistory_id"]

    # 대표 이미지
    image_keyword = post_data.get("image_keyword", "technology code laptop")
    image_url = get_representative_image(image_keyword)
    post_data["representative_image_url"] = image_url

    # HTML 변환 (이미지 최상단 삽입)
    content_md = post_data.get("content_md", "")
    if image_url:
        content_md_with_img = f"![대표이미지]({image_url})\n\n" + content_md
    else:
        content_md_with_img = content_md

    post_data["content_html"] = (
        f'<img src="{image_url}" alt="{post_data.get("thumbnail_title","")}" '
        f'style="width:100%;max-width:800px;margin-bottom:20px;">\n'
        + markdown_to_html(content_md)
    ) if image_url else markdown_to_html(content_md)

    print(f"✅ 포스팅 완료: {post_data['title'][:50]}")
    print(f"   📂 카테고리: {post_data['notion_tag']}")
    print(f"   🖼️ 대표이미지: {image_url[:60]}")
    return post_data


def save_output(post_data: dict, output_path: str = "post_output.json"):
    post_data["generated_at"] = datetime.now().isoformat()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(post_data, f, ensure_ascii=False, indent=2)
    print(f"💾 저장 완료: {output_path}")


if __name__ == "__main__":
    # 쿠팡 URL 우선, 없으면 일반 주제
    coupang_url = COUPANG_URL or (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("http") else "")
    topic       = TOPIC or (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("http") else "")
    post_type   = os.getenv("POST_TYPE", "review")  # review, viral, sales

    if not coupang_url and not topic:
        print("❌ POST_TOPIC 또는 COUPANG_URL 환경변수를 설정해주세요.")
        sys.exit(1)

    if coupang_url:
        post_data = generate_product_post(coupang_url, post_type)
    else:
        post_data = generate_post(topic)

    save_output(post_data)

    print("\n" + "="*50)
    print(f"📌 제목: {post_data['title']}")
    print(f"🖼️  썸네일: {post_data.get('thumbnail_title','')}")
    print(f"📂 카테고리: {post_data.get('notion_tag','')}")
    print(f"🏷️  태그: {', '.join(post_data.get('tags',[]))}")
    print(f"🖼️  대표이미지: {post_data.get('representative_image_url','없음')[:60]}")
    print("="*50)
