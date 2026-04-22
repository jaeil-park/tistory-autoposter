"""
generate_post.py - v4 (Google Gemini API - 무료)
- Anthropic Claude API → Google Gemini 1.5 Flash (무료)
- Unsplash source.unsplash.com 제거 → Unsplash API 또는 Pexels API
"""

import os
import re
import json
import sys
import requests
from datetime import datetime

# ── Gemini API (무료) ─────────────────────────────────────
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL        = "gemini-1.5-flash"
GEMINI_API_URL      = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
PEXELS_API_KEY      = os.getenv("PEXELS_API_KEY", "")
TOPIC               = os.getenv("POST_TOPIC", "")
COUPANG_URL         = os.getenv("COUPANG_URL", "")
POST_TYPE           = os.getenv("POST_TYPE", "review")
PRODUCT_NAME        = os.getenv("PRODUCT_NAME", "")
PRODUCT_PRICE       = os.getenv("PRODUCT_PRICE", "")
PRODUCT_FEATURES    = os.getenv("PRODUCT_FEATURES", "")

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

반드시 아래 형식의 순수 JSON만 출력하세요. 마크다운 코드블록(```) 없이:
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
- viral: 바이럴 마케팅 (감성 스토리)
- sales: 판매 최적화 (혜택 강조, CTA)

중요 규칙:
1. 실제 상품명을 제목과 본문에 반드시 명시
2. 실제 가격 정보 포함
3. 쿠팡 구매 링크를 본문에 2~3회 자연스럽게 삽입
4. 구체적인 사용 경험 묘사 (추상적 표현 금지)
5. 본문 맨 마지막에 반드시:
   > 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.

반드시 아래 형식의 순수 JSON만 출력하세요. 마크다운 코드블록(```) 없이:
{
  "category_key": "product",
  "thumbnail_title": "썸네일 제목 (상품명 포함, 35자 내외)",
  "image_keyword": "상품 관련 영어 키워드 2~3단어",
  "title": "포스트 제목 (실제 상품명 포함)",
  "content_md": "마크다운 본문 전체",
  "tags": ["태그1", "태그2"],
  "post_type": "review|viral|sales",
  "meta_description": "메타 설명 (실제 상품명 포함, 80자 내외)"
}
"""


def call_gemini(system_prompt: str, user_message: str) -> dict:
    """Google Gemini API 호출 (무료)"""
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY,
    }

    # Gemini는 system/user를 contents로 통합
    payload = {
        "contents": [
            {
                "parts": [{"text": f"{system_prompt}\n\n{user_message}"}],
                "role": "user"
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",  # JSON 모드 강제
        }
    }

    for attempt in range(3):
        try:
            resp = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            # 응답 추출
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # 혹시 코드블록으로 감싸진 경우 제거
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            result = json.loads(raw)
            print(f"  ✅ Gemini API 호출 성공 (attempt {attempt+1})")
            return result

        except Exception as e:
            print(f"  ⚠️ Gemini 오류 (attempt {attempt+1}): {e}")
            if attempt == 2:
                raise RuntimeError(f"Gemini API 호출 실패: {e}")

    raise RuntimeError("Gemini API 모든 시도 실패")


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
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=15, allow_redirects=True)
        html = resp.text
        print(f"  🔗 최종 URL: {resp.url[:80]}")

        og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html)
        og_image = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        og_desc  = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html)

        title = (og_title.group(1) if og_title else "")
        title = re.sub(r'\s*[-|]\s*쿠팡.*$', '', title).strip()

        price = ""
        for pat in [r'"finalPrice"\s*:\s*(\d+)', r'(\d{1,3}(?:,\d{3})+)\s*원']:
            m = re.search(pat, html, re.DOTALL)
            if m:
                price_num = m.group(1).replace(',', '')
                if len(price_num) >= 3:
                    price = f"{int(price_num):,}원"
                    break

        result = {
            "url": url, "final_url": resp.url,
            "title": title[:200], "price": price or "",
            "image_url": og_image.group(1) if og_image else "",
            "description": og_desc.group(1) if og_desc else "",
        }
        print(f"  📦 상품명: {result['title'][:60] or '파싱 실패'}")
        print(f"  💰 가격: {result['price'] or '파싱 실패'}")
        return result
    except Exception as e:
        print(f"  ⚠️ 상품 파싱 실패: {e}")
        return {"url": url, "final_url": url, "title": "", "price": "", "image_url": "", "description": ""}


def get_image(keyword: str, fallback_url: str = "") -> str:
    """이미지 URL 가져오기: 쿠팡 이미지 → Pexels → Unsplash"""
    if fallback_url:
        return fallback_url

    # Pexels API (무료, 월 25,000회)
    if PEXELS_API_KEY and keyword:
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": keyword, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": PEXELS_API_KEY},
                timeout=10
            )
            data = resp.json()
            if data.get("photos"):
                url = data["photos"][0]["src"]["large"]
                print(f"  🖼️ Pexels: {url[:60]}")
                return url
        except Exception as e:
            print(f"  ⚠️ Pexels 실패: {e}")

    # Unsplash API
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
                print(f"  🖼️ Unsplash: {url[:60]}")
                return url
        except Exception as e:
            print(f"  ⚠️ Unsplash 실패: {e}")

    print("  ⚠️ 이미지 없음 (API 키 미설정)")
    return ""


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
    img_tag = ""
    if image_url:
        img_tag = (
            f'<div style="text-align:center;margin-bottom:24px;">'
            f'<img src="{image_url}" alt="{alt}" '
            f'style="width:100%;max-width:800px;border-radius:8px;"></div>\n'
        )
    return img_tag + markdown_to_html(content_md)


def generate_product_post(coupang_url: str, post_type: str = "review") -> dict:
    print(f"🛍️ 쿠팡 상품 분석: {coupang_url[:60]}")
    product = fetch_product_info(coupang_url)

    # 수동 입력으로 보완
    if PRODUCT_NAME and not product.get("title"):
        product["title"] = PRODUCT_NAME
    if PRODUCT_PRICE and not product.get("price"):
        product["price"] = PRODUCT_PRICE
    if PRODUCT_FEATURES:
        product["description"] = (product.get("description","") + "\n특징: " + PRODUCT_FEATURES).strip()

    user_message = f"""
다음 쿠팡 상품으로 블로그 포스트를 작성해주세요:

상품명: {product['title'] or '(파싱 실패 - 링크에서 확인)'}
가격: {product['price'] or '(확인 필요)'}
상품 설명: {product['description'][:300]}
구매 링크: {coupang_url}
글 유형: {post_type}

실제 상품명을 제목에 포함하고, 구매 링크({coupang_url})를 본문에 2~3회 삽입하세요.
순수 JSON만 출력하세요.
"""
    post_data = call_gemini(PRODUCT_SYSTEM_PROMPT, user_message)
    post_data["category_key"]        = "product"
    post_data["notion_tag"]          = CATEGORY_MAP["product"]["notion_tag"]
    post_data["tistory_category_id"] = CATEGORY_MAP["product"]["tistory_id"]

    # 쿠팡 파트너스 고지 강제 삽입
    content_md = post_data.get("content_md", "")
    if "쿠팡 파트너스 활동의 일환" not in content_md:
        content_md += "\n\n---\n> 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
        post_data["content_md"] = content_md

    image_url = get_image(post_data.get("image_keyword","product shopping"), product.get("image_url",""))
    post_data["representative_image_url"] = image_url
    post_data["content_html"] = build_html_with_image(content_md, image_url, post_data.get("thumbnail_title",""))

    print(f"✅ 상품 포스팅 완료: {post_data['title'][:50]}")
    return post_data


def generate_post(topic: str) -> dict:
    print(f"🤖 Gemini로 포스트 생성: '{topic}'")

    user_message = f"""
다음 주제로 티스토리 블로그 포스트를 작성해주세요:
주제: {topic}

category_key, image_keyword, post_type 자동 결정.
content_html 제외. 순수 JSON만 출력.
"""
    post_data = call_gemini(BLOG_SYSTEM_PROMPT, user_message)

    key = post_data.get("category_key", "general")
    if key not in CATEGORY_MAP:
        key = "general"
    post_data["category_key"]        = key
    post_data["notion_tag"]          = CATEGORY_MAP[key]["notion_tag"]
    post_data["tistory_category_id"] = CATEGORY_MAP[key]["tistory_id"]

    image_url = get_image(post_data.get("image_keyword", "technology laptop"))
    post_data["representative_image_url"] = image_url
    post_data["content_html"] = build_html_with_image(
        post_data.get("content_md",""), image_url, post_data.get("thumbnail_title","")
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
