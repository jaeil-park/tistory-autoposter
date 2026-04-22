"""
generate_post.py - v5
- Gemini 1.5 Flash (IT 기술 포스팅) + Naver HyperCLOVA (상품 리뷰, 한국어 특화) 병행
- 이미지: Pexels (우선) + Unsplash (fallback)
- Pexels 영상 검색 지원 (티스토리 영상 embed용)
"""

import os
import re
import json
import sys
import requests
from datetime import datetime

# ── AI API 설정 ───────────────────────────────────────────
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL        = "gemini-2.0-flash"
GEMINI_API_URL      = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

NAVER_CLIENT_ID     = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

# ── 이미지/영상 API 설정 ──────────────────────────────────
PEXELS_API_KEY      = os.getenv("PEXELS_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")

# ── 환경변수 ──────────────────────────────────────────────
TOPIC            = os.getenv("POST_TOPIC", "")
COUPANG_URL      = os.getenv("COUPANG_URL", "")
POST_TYPE        = os.getenv("POST_TYPE", "review")
PRODUCT_NAME     = os.getenv("PRODUCT_NAME", "")
PRODUCT_PRICE    = os.getenv("PRODUCT_PRICE", "")
PRODUCT_FEATURES = os.getenv("PRODUCT_FEATURES", "")

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

반드시 아래 형식의 순수 JSON만 출력 (마크다운 코드블록 없이):
{
  "category_key": "카테고리 키",
  "thumbnail_title": "썸네일 제목 (35자 내외)",
  "image_keyword": "대표 이미지 영어 키워드 2~3단어",
  "video_keyword": "관련 영상 영어 키워드 2~3단어",
  "title": "포스트 제목",
  "content_md": "마크다운 본문",
  "tags": ["태그1", "태그2"],
  "post_type": "tutorial|troubleshooting|devlog|concept|snippet|review|viral",
  "meta_description": "메타 설명 (80자 내외)"
}
"""

PRODUCT_SYSTEM_PROMPT = """
당신은 쿠팡파트너스 상품 블로그 마케팅 전문가입니다.
실제 상품명, 가격, 특징을 바탕으로 구체적이고 자연스러운 한국어 후기를 작성합니다.

글 유형:
- review: 실사용자 후기 (구체적 장단점, 별점, 총평)
- viral: 바이럴 마케팅 (감성 스토리)
- sales: 판매 최적화 (혜택 강조, CTA)

중요 규칙:
1. 실제 상품명을 제목과 본문에 반드시 명시
2. 실제 가격 정보 포함
3. 쿠팡 구매 링크 본문에 2~3회 자연스럽게 삽입
4. 구체적 사용 경험 묘사 (추상적 표현 금지)
5. 본문 맨 마지막에 반드시 추가:
   > 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.

반드시 아래 형식의 순수 JSON만 출력 (마크다운 코드블록 없이):
{
  "category_key": "product",
  "thumbnail_title": "썸네일 제목 (상품명 포함, 35자 내외)",
  "image_keyword": "상품 관련 영어 키워드 2~3단어",
  "video_keyword": "상품 관련 영상 영어 키워드 2~3단어",
  "title": "포스트 제목 (실제 상품명 포함)",
  "content_md": "마크다운 본문 전체",
  "tags": ["태그1", "태그2"],
  "post_type": "review|viral|sales",
  "meta_description": "메타 설명 (실제 상품명 포함, 80자 내외)"
}
"""


# ══════════════════════════════════════════════════════
# AI API 호출
# ══════════════════════════════════════════════════════

def call_gemini(system_prompt: str, user_message: str) -> dict:
    """Google Gemini API - 429 자동 재시도 + 모델 fallback"""
    import time

    # 모델 우선순위: 빠른 것 → 안정적인 것
    models = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash-latest",
    ]

    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_message}"}], "role": "user"}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        }
    }

    for model in models:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        print(f"  🤖 모델 시도: {model}")

        for attempt in range(3):
            try:
                resp = requests.post(api_url, headers=headers, json=payload, timeout=60)

                # 429 → 대기 후 재시도
                if resp.status_code == 429:
                    wait = (attempt + 1) * 10  # 10초, 20초, 30초
                    print(f"  ⏳ Rate limit → {wait}초 대기 후 재시도...")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                result = json.loads(raw.strip())
                print(f"  ✅ Gemini 완료: {model} (attempt {attempt+1})")
                return result

            except requests.exceptions.HTTPError as e:
                if resp.status_code == 404:
                    print(f"  ⚠️ 모델 없음: {model} → 다음 모델 시도")
                    break  # 다음 모델로
                print(f"  ⚠️ HTTP 오류 (attempt {attempt+1}): {e}")
                if attempt == 2:
                    break  # 다음 모델로
            except Exception as e:
                print(f"  ⚠️ 오류 (attempt {attempt+1}): {e}")
                if attempt == 2:
                    break

    raise RuntimeError("모든 Gemini 모델 시도 실패")


def call_naver_clova(prompt: str) -> str:
    """Naver HyperCLOVA X - 상품 리뷰 한국어 특화"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("  ⚠️ Naver API 키 없음 → Gemini로 대체")
        return ""

    headers = {
        "X-NCP-CLOVASTUDIO-API-KEY": NAVER_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "maxTokens": 3000,
        "temperature": 0.7,
        "topP": 0.8,
    }
    try:
        resp = requests.post(
            "https://clovastudio.stream.ntruss.com/testapp/v1/chat-completions/HCX-003",
            headers=headers, json=payload, timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("result", {}).get("message", {}).get("content", "")
        if text:
            print("  ✅ Naver HyperCLOVA 응답 완료")
        return text
    except Exception as e:
        print(f"  ⚠️ Naver API 오류: {e} → Gemini로 대체")
        return ""


def call_ai_for_product(product: dict, post_type: str, coupang_url: str) -> dict:
    """상품 포스팅: Naver 우선 시도 → 실패 시 Gemini"""

    user_message = f"""
다음 쿠팡 상품으로 블로그 포스트를 작성해주세요:

상품명: {product.get('title') or '(직접 확인 필요)'}
가격: {product.get('price') or '(확인 필요)'}
상품 설명: {product.get('description', '')[:300]}
구매 링크: {coupang_url}
글 유형: {post_type}

실제 상품명을 제목에 포함하고, 구매 링크를 본문에 2~3회 삽입하세요.
순수 JSON만 출력하세요.
"""

    # 1순위: Naver HyperCLOVA (한국어 상품 리뷰 특화)
    if NAVER_CLIENT_ID:
        naver_prompt = PRODUCT_SYSTEM_PROMPT + "\n\n" + user_message
        naver_result = call_naver_clova(naver_prompt)
        if naver_result:
            try:
                raw = naver_result.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                return json.loads(raw.strip())
            except Exception as e:
                print(f"  ⚠️ Naver 응답 파싱 실패: {e} → Gemini로 대체")

    # 2순위: Gemini
    return call_gemini(PRODUCT_SYSTEM_PROMPT, user_message)


# ══════════════════════════════════════════════════════
# 이미지 / 영상
# ══════════════════════════════════════════════════════

def get_pexels_image(keyword: str) -> str:
    """Pexels 이미지 검색 (무료, 우선순위 1)"""
    if not PEXELS_API_KEY or not keyword:
        return ""
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
            print(f"  🖼️ Pexels 이미지: {url[:60]}")
            return url
    except Exception as e:
        print(f"  ⚠️ Pexels 이미지 실패: {e}")
    return ""


def get_pexels_video(keyword: str) -> dict:
    """Pexels 영상 검색 (무료) - 티스토리 embed용"""
    if not PEXELS_API_KEY or not keyword:
        return {}
    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            params={"query": keyword, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=10
        )
        data = resp.json()
        if data.get("videos"):
            video = data["videos"][0]
            # 최적 해상도 파일 선택 (HD 우선)
            files = sorted(video.get("video_files", []),
                          key=lambda x: x.get("width", 0), reverse=True)
            hd_file = next((f for f in files if f.get("width", 0) <= 1280), files[0] if files else None)
            if hd_file:
                result = {
                    "url":       hd_file.get("link", ""),
                    "thumbnail": video.get("image", ""),
                    "width":     hd_file.get("width", 0),
                    "height":    hd_file.get("height", 0),
                    "duration":  video.get("duration", 0),
                    "pexels_url": video.get("url", ""),
                }
                print(f"  🎬 Pexels 영상: {result['url'][:60]}")
                return result
    except Exception as e:
        print(f"  ⚠️ Pexels 영상 실패: {e}")
    return {}


def get_unsplash_image(keyword: str) -> str:
    """Unsplash 이미지 (fallback)"""
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
            print(f"  🖼️ Unsplash 이미지: {url[:60]}")
            return url
    except Exception as e:
        print(f"  ⚠️ Unsplash 실패: {e}")
    return ""


def get_best_image(keyword: str, fallback_url: str = "") -> str:
    """최적 이미지: 쿠팡상품이미지 → Pexels → Unsplash"""
    if fallback_url:
        return fallback_url
    return get_pexels_image(keyword) or get_unsplash_image(keyword) or ""


# ══════════════════════════════════════════════════════
# HTML 생성
# ══════════════════════════════════════════════════════

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


def build_html(content_md: str, image_url: str, video: dict, alt: str = "") -> str:
    """대표 이미지 + 영상 embed + 본문 HTML 조합"""
    parts = []

    # 대표 이미지 (최상단)
    if image_url:
        parts.append(
            f'<div style="text-align:center;margin-bottom:24px;">'
            f'<img src="{image_url}" alt="{alt}" '
            f'style="width:100%;max-width:800px;border-radius:8px;"></div>'
        )

    # 본문
    parts.append(markdown_to_html(content_md))

    # Pexels 영상 embed (본문 하단)
    if video.get("url"):
        parts.append(
            f'\n<div style="text-align:center;margin:24px 0;">'
            f'<video controls style="width:100%;max-width:800px;border-radius:8px;" '
            f'poster="{video.get("thumbnail","")}">'
            f'<source src="{video["url"]}" type="video/mp4">'
            f'</video>'
            f'<p style="font-size:12px;color:#888;">영상 출처: '
            f'<a href="{video.get("pexels_url","https://pexels.com")}" target="_blank">Pexels</a></p>'
            f'</div>'
        )

    return "\n".join(parts)


# ══════════════════════════════════════════════════════
# 쿠팡 상품 파싱
# ══════════════════════════════════════════════════════

def fetch_product_info(url: str) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    try:
        resp = requests.Session().get(url, headers=headers, timeout=15, allow_redirects=True)
        html = resp.text
        print(f"  🔗 최종 URL: {resp.url[:80]}")

        og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html)
        og_image = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        og_desc  = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html)

        title = re.sub(r'\s*[-|]\s*쿠팡.*$', '', (og_title.group(1) if og_title else "")).strip()

        price = ""
        for pat in [r'"finalPrice"\s*:\s*(\d+)', r'(\d{1,3}(?:,\d{3})+)\s*원']:
            m = re.search(pat, html)
            if m:
                p = m.group(1).replace(',', '')
                if len(p) >= 3:
                    price = f"{int(p):,}원"
                    break

        result = {
            "title":       title[:200],
            "price":       price,
            "image_url":   og_image.group(1) if og_image else "",
            "description": og_desc.group(1) if og_desc else "",
        }
        print(f"  📦 상품명: {result['title'][:60] or '파싱 실패'}")
        print(f"  💰 가격: {result['price'] or '파싱 실패'}")
        return result
    except Exception as e:
        print(f"  ⚠️ 상품 파싱 실패: {e}")
        return {"title": "", "price": "", "image_url": "", "description": ""}


# ══════════════════════════════════════════════════════
# 메인 함수
# ══════════════════════════════════════════════════════

def generate_product_post(coupang_url: str, post_type: str = "review") -> dict:
    print(f"🛍️ 상품 포스팅 시작 [{post_type}]: {coupang_url[:60]}")

    product = fetch_product_info(coupang_url)
    if PRODUCT_NAME and not product["title"]:
        product["title"] = PRODUCT_NAME
    if PRODUCT_PRICE and not product["price"]:
        product["price"] = PRODUCT_PRICE
    if PRODUCT_FEATURES:
        product["description"] = (product["description"] + "\n특징: " + PRODUCT_FEATURES).strip()

    # AI 호출 (Naver 우선 → Gemini fallback)
    post_data = call_ai_for_product(product, post_type, coupang_url)

    post_data["category_key"]        = "product"
    post_data["notion_tag"]          = CATEGORY_MAP["product"]["notion_tag"]
    post_data["tistory_category_id"] = CATEGORY_MAP["product"]["tistory_id"]

    # 쿠팡 파트너스 고지 강제
    content_md = post_data.get("content_md", "")
    if "쿠팡 파트너스 활동의 일환" not in content_md:
        content_md += "\n\n---\n> 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
        post_data["content_md"] = content_md

    # 이미지 + 영상
    image_url = get_best_image(post_data.get("image_keyword", "product"), product.get("image_url", ""))
    video     = get_pexels_video(post_data.get("video_keyword", ""))

    post_data["representative_image_url"] = image_url
    post_data["video"]                    = video
    post_data["content_html"]             = build_html(content_md, image_url, video, post_data.get("thumbnail_title", ""))

    print(f"✅ 상품 포스팅 완료: {post_data.get('title','')[:50]}")
    return post_data


def generate_post(topic: str) -> dict:
    print(f"🤖 Gemini로 IT 포스팅 생성: '{topic}'")

    user_message = f"""
주제: {topic}
category_key, image_keyword, video_keyword, post_type 자동 결정.
content_html 제외. 순수 JSON만 출력.
"""
    post_data = call_gemini(BLOG_SYSTEM_PROMPT, user_message)

    key = post_data.get("category_key", "general")
    if key not in CATEGORY_MAP:
        key = "general"
    post_data["category_key"]        = key
    post_data["notion_tag"]          = CATEGORY_MAP[key]["notion_tag"]
    post_data["tistory_category_id"] = CATEGORY_MAP[key]["tistory_id"]

    # 이미지 + 영상
    image_url = get_best_image(post_data.get("image_keyword", "technology laptop"))
    video     = get_pexels_video(post_data.get("video_keyword", ""))

    post_data["representative_image_url"] = image_url
    post_data["video"]                    = video
    post_data["content_html"]             = build_html(
        post_data.get("content_md", ""), image_url, video, post_data.get("thumbnail_title", "")
    )

    print(f"✅ IT 포스팅 완료: {post_data.get('title','')[:50]}")
    print(f"   📂 {post_data['notion_tag']}  🖼️ {'있음' if image_url else '없음'}  🎬 {'있음' if video else '없음'}")
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
    print(f"📌 제목: {post_data.get('title','')}")
    print(f"🖼️  썸네일: {post_data.get('thumbnail_title','')}")
    print(f"📂 카테고리: {post_data.get('notion_tag','')}")
    print(f"🏷️  태그: {', '.join(post_data.get('tags',[]))}")
    print(f"🖼️  이미지: {post_data.get('representative_image_url','없음')[:60]}")
    print(f"🎬 영상: {'있음 - ' + post_data['video']['url'][:50] if post_data.get('video',{}).get('url') else '없음'}")
    print("="*50)
