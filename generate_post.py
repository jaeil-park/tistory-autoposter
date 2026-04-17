"""
generate_post.py - v3
- 쿠팡 리다이렉트 → 실제 상품 페이지 파싱
- 상품 이미지 직접 추출
- Unsplash source.unsplash.com 제거 → API 직접 사용
- 실제 상품명/가격 기반 구체적 글쓰기
"""

import os
import re
import json
import sys
import requests
import anthropic
from datetime import datetime

ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
TOPIC               = os.getenv("POST_TOPIC", "")
COUPANG_URL         = os.getenv("COUPANG_URL", "")
POST_TYPE           = os.getenv("POST_TYPE", "review")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CATEGORY_MAP = {
    "python":    {"notion_tag": "🐍 Python/개발",    "tistory_id": "0"},
    "langchain": {"notion_tag": "🤖 AI/LangChain",   "tistory_id": "0"},
    "discord":   {"notion_tag": "💬 Discord봇",      "tistory_id": "0"},
    "infra":     {"notion_tag": "🖥️ IT인프라",       "tistory_id": "0"},
    "quant":     {"notion_tag": "📈 퀀트/자동화",    "tistory_id": "0"},
    "linux":     {"notion_tag": "🐧 Linux/Server",   "tistory_id": "0"},
    "docker":    {"notion_tag": "🐳 Docker/DevOps",  "tistory_id": "0"},
    "fastapi":   {"notion_tag": "⚡ FastAPI/백엔드", "tistory_id": "0"},
    "vue":       {"notion_tag": "🎨 Frontend",       "tistory_id": "0"},
    "product":   {"notion_tag": "🛍️ 상품리뷰",      "tistory_id": "0"},
    "general":   {"notion_tag": "📝 일반",           "tistory_id": "0"},
}

BLOG_SYSTEM_PROMPT = """
당신은 베테랑 IT 엔지니어 재일(jaeil.park)의 티스토리 블로그 포스트 작성 전문가입니다.

카테고리 키: python, langchain, discord, infra, quant, linux, docker, fastapi, vue, product, general

출력 형식 (순수 JSON):
{
  "category_key": "카테고리 키",
  "thumbnail_title": "썸네일 제목 (35자 내외)",
  "image_keyword": "대표 이미지 검색 키워드 (영어 2~3단어)",
  "title": "포스트 제목",
  "content_md": "마크다운 본문",
  "tags": ["태그1", "태그2"],
  "post_type": "tutorial|troubleshooting|devlog|concept|snippet|review|viral",
  "meta_description": "메타 설명 (80자 내외)"
}
"""

PRODUCT_SYSTEM_PROMPT = """
당신은 쿠팡파트너스 상품 블로그 마케팅 전문가입니다.
실제 상품명, 가격, 특징을 바탕으로 구체적이고 자연스러운 후기를 작성합니다.

글 유형:
- review: 실사용자 후기 (구체적 장단점, 별점, 총평) - 추상적 표현 금지
- viral: 바이럴 마케팅 (감성 스토리, 상품 자연스럽게 녹이기)
- sales: 판매 최적화 (혜택 강조, CTA, 가격 비교)

중요 규칙:
1. 실제 상품명을 제목과 본문에 반드시 명시
2. 실제 가격 정보 포함
3. 쿠팡 구매 링크를 본문에 2~3회 자연스럽게 삽입
4. 구체적인 사용 경험 묘사 (추상적 표현 금지)
5. 본문 맨 마지막에 반드시:
   > 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.

출력 형식 (순수 JSON):
{
  "category_key": "product",
  "thumbnail_title": "썸네일 제목 (상품명 포함, 35자 내외)",
  "image_keyword": "상품 관련 영어 키워드 2~3단어",
  "title": "포스트 제목 (실제 상품명 포함, SEO 최적화)",
  "content_md": "마크다운 본문 전체",
  "tags": ["태그1", "태그2"],
  "post_type": "review|viral|sales",
  "meta_description": "메타 설명 (실제 상품명 포함, 80자 내외)"
}
"""


def fetch_product_info(url: str) -> dict:
    """쿠팡 단축 URL → 실제 상품 페이지 → 정보 파싱"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    try:
        # 리다이렉트 따라가기
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=15,
                          allow_redirects=True, stream=False)
        final_url = resp.url
        html = resp.text
        print(f"  🔗 최종 URL: {final_url[:80]}")

        # OG 태그 파싱
        og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html)
        og_image = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        og_desc  = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html)

        # 제목 파싱 (여러 방법 시도)
        title = ""
        if og_title:
            title = og_title.group(1).strip()
        if not title:
            t = re.search(r'<title>([^<]+)</title>', html)
            title = t.group(1).strip() if t else ""
        # 쿠팡 제목에서 " - 쿠팡!" 제거
        title = re.sub(r'\s*[-|]\s*쿠팡.*$', '', title).strip()

        # 가격 파싱
        price = ""
        price_patterns = [
            r'"finalPrice"\s*:\s*(\d+)',
            r'class="[^"]*total-price[^"]*"[^>]*>.*?(\d{1,3}(?:,\d{3})+)',
            r'(\d{1,3}(?:,\d{3})+)\s*원',
        ]
        for pat in price_patterns:
            m = re.search(pat, html, re.DOTALL)
            if m:
                price_num = m.group(1).replace(',', '')
                if len(price_num) >= 3:
                    price = f"{int(price_num):,}원"
                    break

        # 상품 이미지 (OG 이미지 우선)
        image_url = og_image.group(1) if og_image else ""
        # 쿠팡 상품 썸네일 직접 추출
        if not image_url:
            img_m = re.search(r'src=["\']([^"\']*thumbnail[^"\']*\.jpg[^"\']*)["\']', html)
            if img_m:
                image_url = img_m.group(1)

        # 상품 설명
        description = og_desc.group(1) if og_desc else ""

        result = {
            "url":         url,
            "final_url":   final_url,
            "title":       title[:200],
            "price":       price or "가격 확인 필요",
            "image_url":   image_url,
            "description": description[:300],
        }
        print(f"  📦 상품명: {result['title'][:60]}")
        print(f"  💰 가격: {result['price']}")
        print(f"  🖼️ 이미지: {'있음' if image_url else '없음'}")
        return result

    except Exception as e:
        print(f"  ⚠️ 상품 파싱 실패: {e}")
        return {"url": url, "final_url": url, "title": "", "price": "", "image_url": "", "description": ""}


def get_unsplash_image(keyword: str) -> str:
    """Unsplash API로 이미지 URL 가져오기"""
    if not UNSPLASH_ACCESS_KEY or not keyword:
        return ""
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
            print(f"  🖼️ Unsplash: {url[:60]}")
            return url
    except Exception as e:
        print(f"  ⚠️ Unsplash 실패: {e}")
    return ""


def _call_api(system: str, user_message: str) -> dict:
    for tokens in [8000, 6000, 4000]:
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
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            print(f"  ⚠️ API 오류 (tokens={tokens}): {e}")
    raise RuntimeError("API 호출 실패")


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
        html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)
        html = html.replace("\n\n", "</p><p>")
        return f"<p>{html}</p>"


def build_html_with_image(content_md: str, image_url: str, alt: str = "") -> str:
    """본문 HTML 생성 (대표 이미지 최상단 삽입)"""
    img_tag = ""
    if image_url:
        img_tag = (
            f'<div style="text-align:center;margin-bottom:24px;">'
            f'<img src="{image_url}" alt="{alt}" '
            f'style="width:100%;max-width:800px;border-radius:8px;"></div>\n'
        )
    return img_tag + markdown_to_html(content_md)


def generate_product_post(coupang_url: str, post_type: str = "review") -> dict:
    """쿠팡파트너스 링크 → 상품 분석 → 포스팅 생성"""
    print(f"🛍️ 쿠팡 상품 분석: {coupang_url[:60]}")

    product = fetch_product_info(coupang_url)

    user_message = f"""
다음 쿠팡 상품으로 블로그 포스트를 작성해주세요:

**상품명**: {product['title'] or '(파싱 실패 - 링크 참고)'}
**가격**: {product['price']}
**상품 설명**: {product['description']}
**구매 링크**: {coupang_url}
**글 유형**: {post_type}

{'상품명을 모르는 경우 링크 클릭을 유도하는 방식으로 작성하세요.' if not product['title'] else '실제 상품명을 제목과 본문에 명시하세요.'}
구매 링크({coupang_url})를 본문에 자연스럽게 2~3회 삽입하세요.
순수 JSON만 출력하세요.
"""
    post_data = _call_api(PRODUCT_SYSTEM_PROMPT, user_message)

    # 카테고리
    post_data["category_key"]        = "product"
    post_data["notion_tag"]          = CATEGORY_MAP["product"]["notion_tag"]
    post_data["tistory_category_id"] = CATEGORY_MAP["product"]["tistory_id"]

    # 쿠팡 필수 고지 문구 강제 삽입
    content_md = post_data.get("content_md", "")
    if "쿠팡 파트너스 활동의 일환" not in content_md:
        content_md += (
            "\n\n---\n"
            "> 이 포스팅은 쿠팡 파트너스 활동의 일환으로, "
            "이에 따른 일정액의 수수료를 제공받습니다."
        )
        post_data["content_md"] = content_md

    # 대표 이미지: 쿠팡 상품 이미지 우선 → Unsplash
    image_url = product.get("image_url", "")
    if not image_url:
        image_url = get_unsplash_image(post_data.get("image_keyword", "product shopping"))
    post_data["representative_image_url"] = image_url

    # HTML 생성
    post_data["content_html"] = build_html_with_image(
        content_md, image_url, post_data.get("thumbnail_title", "")
    )

    print(f"✅ 상품 포스팅 완료: {post_data['title'][:50]}")
    return post_data


def generate_post(topic: str) -> dict:
    """일반 주제 포스팅"""
    print(f"🤖 포스트 생성: '{topic}'")

    user_message = f"""
다음 주제로 티스토리 블로그 포스트를 작성해주세요:
**주제**: {topic}
category_key, image_keyword, post_type 자동 결정.
content_html 제외. 순수 JSON만 출력.
"""
    post_data = _call_api(BLOG_SYSTEM_PROMPT, user_message)

    # 카테고리
    key = post_data.get("category_key", "general")
    if key not in CATEGORY_MAP:
        key = "general"
    post_data["category_key"]        = key
    post_data["notion_tag"]          = CATEGORY_MAP[key]["notion_tag"]
    post_data["tistory_category_id"] = CATEGORY_MAP[key]["tistory_id"]

    # 대표 이미지
    image_url = get_unsplash_image(post_data.get("image_keyword", "technology laptop"))
    post_data["representative_image_url"] = image_url

    # HTML 생성
    post_data["content_html"] = build_html_with_image(
        post_data.get("content_md", ""),
        image_url,
        post_data.get("thumbnail_title", "")
    )

    print(f"✅ 포스팅 완료: {post_data['title'][:50]}")
    print(f"   📂 {post_data['notion_tag']}  🖼️ {image_url[:50] if image_url else '없음'}")
    return post_data


def save_output(post_data: dict, path: str = "post_output.json"):
    post_data["generated_at"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(post_data, f, ensure_ascii=False, indent=2)
    print(f"💾 저장: {path}")


if __name__ == "__main__":
    coupang_url = COUPANG_URL or (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("http") else "")
    topic       = TOPIC or (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("http") else "")

    if not coupang_url and not topic:
        print("❌ POST_TOPIC 또는 COUPANG_URL을 설정해주세요.")
        sys.exit(1)

    post_data = generate_product_post(coupang_url, POST_TYPE) if coupang_url else generate_post(topic)
    save_output(post_data)

    print("\n" + "="*50)
    print(f"📌 제목: {post_data['title']}")
    print(f"🖼️  썸네일: {post_data.get('thumbnail_title','')}")
    print(f"📂 카테고리: {post_data.get('notion_tag','')}")
    print(f"🏷️  태그: {', '.join(post_data.get('tags',[]))}")
    print(f"🖼️  대표이미지: {post_data.get('representative_image_url','없음')[:60]}")
    print("="*50)
