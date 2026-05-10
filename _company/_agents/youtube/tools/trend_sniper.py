#!/usr/bin/env python3
"""
Trend Sniper — 유튜브 키워드 트렌드 분석기

- TARGET_KEYWORDS: trend_sniper.json
- 공통 설정 (YOUTUBE_API_KEY, OLLAMA_URL, MODEL): youtube_account.json 또는 trend_sniper.json
- 둘 다에 있으면 trend_sniper.json 값이 우선

필수 설치:
    pip install google-api-python-client requests
"""

import os
import json
import time
import random
import datetime
import sys

# ---- 콘솔 인코딩 방어: Windows CMD cp949에서 죽지 않게 ----
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "trend_sniper.json")
ACCOUNT_PATH = os.path.join(HERE, "youtube_account.json")
REPORT_PATH = os.path.join(HERE, "trend_sniper_report.md")


def load_config():
    """trend_sniper.json 불러오기."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"설정 파일을 읽을 수 없어요: {CONFIG_PATH}\n{e}")
        sys.exit(1)


def load_account():
    """youtube_account.json 불러오기 (없으면 빈 dict)."""
    try:
        if os.path.exists(ACCOUNT_PATH):
            with open(ACCOUNT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _shared(cfg, acct, key, default=""):
    """
    Per-tool 설정이 우선, 없으면 공통 설정, 그래도 없으면 기본값.
    """
    v = cfg.get(key)
    if v not in (None, "", []):
        return v
    v = acct.get(key)
    if v not in (None, "", []):
        return v
    return default


def main():
    cfg = load_config()
    acct = load_account()

    # ---- 기본 설정 로딩 ----
    api_key = (_shared(cfg, acct, "YOUTUBE_API_KEY") or "").strip()
    if not api_key:
        print("YOUTUBE_API_KEY가 비어있어요. youtube_account.json 또는 trend_sniper.json에 입력하세요.")
        print("  발급 경로: Google Cloud Console → YouTube Data API v3 → 사용자 인증 정보 → API 키")
        sys.exit(1)

    target_keywords = cfg.get("TARGET_KEYWORDS", [])
    if not target_keywords:
        print("TARGET_KEYWORDS가 비어있어요. 분석할 키워드를 1개 이상 trend_sniper.json에 추가하세요.")
        sys.exit(1)

    ollama_url = (_shared(cfg, acct, "OLLAMA_URL", "http://127.0.0.1:11434") or "http://127.0.0.1:11434").rstrip("/")
    model = _shared(cfg, acct, "MODEL", "") or ""

    # 한 번에 분석할 키워드 수 (최대 2개)
    pick = min(2, len(target_keywords))
    chosen = random.sample(target_keywords, pick)

    # ---- 라이브러리 확인 ----
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("google-api-python-client가 설치되지 않았어요.")
        print("  설치: pip install google-api-python-client requests")
        sys.exit(1)

    try:
        import requests
    except ImportError:
        print("requests가 설치되지 않았어요.")
        print("  설치: pip install requests")
        sys.exit(1)

    # ---- 유튜브 조회 ----
    print(f"\n[트렌드 스나이퍼] 키워드 {chosen} 스캔 시작...")
    youtube = build("youtube", "v3", developerKey=api_key)

    # 최근 30일
    last_month = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).isoformat("T") + "Z"

    sniper_data = []

    for q in chosen:
        print(f"[{q}] 상위 영상 검색 중...")
        try:
            req = youtube.search().list(
                part="snippet",
                q=q,
                maxResults=5,
                order="viewCount",
                publishedAfter=last_month,
                type="video",
            )
            res = req.execute()
            for item in res.get("items", []):
                title = item["snippet"]["title"]
                channel = item["snippet"]["channelTitle"]
                sniper_data.append(f"[{q}] 채널: {channel} | 제목: {title}")
        except Exception as e:
            print(f"[{q}] 검색 오류: {e}")

    if not sniper_data:
        print("수집된 데이터가 없습니다. API 키 한도, 네트워크, 키워드를 확인하세요.")
        sys.exit(1)

    data_text = "\n".join(sniper_data)

    # ---- LLM 프롬프트 구성 ----
    prompt = f"""당신은 유튜브 알고리즘 마스터마인드입니다. 아래는 최근 30일 조회수가 잘 나온 영상들입니다.

[키워드] {', '.join(chosen)}

[데이터]
{data_text}

아래 3개 섹션으로 마크다운 보고서를 작성하세요.

1. 트렌드 해킹 분석
   - 어떤 패턴이 조회수를 끌고 있는지
   - 썸네일/제목/오프닝/구성의 공통점과 차이점

2. 빈집 털기 전략
   - 경쟁이 덜한 틈새 주제
   - 기존 영상과 다르게 가져가야 할 포인트

3. 파괴적 영상 기획안
   - 채널에서 바로 찍을 수 있는 영상 기획 2~3개
   - 각 기획마다:
     - 썸네일 카피 2~3개
     - 제목 후보 3개
     - 후킹 오프닝(첫 5초) 구체 설명
"""

    # ---- 엔진 종류 감지 (LM Studio vs Ollama) ----
    is_lm_studio = ("1234" in ollama_url) or ("/v1" in ollama_url)
    print(f"[LLM 분석 중... 엔진: {'LM Studio' if is_lm_studio else 'Ollama'}]")

    # ---- 모델 자동 선택 ----
    import requests  # 위에서 임포트 확인됨

    if not model:
        try:
            if is_lm_studio:
                # LM Studio (OpenAI 호환)
                base = ollama_url.rstrip("/")
                if not base.endswith("/v1"):
                    base = base + "/v1"
                r = requests.get(f"{base}/models", timeout=5)
                r.raise_for_status()
                models = [m["id"] for m in r.json().get("data", [])]
            else:
                # Ollama
                r = requests.get(f"{ollama_url}/api/tags", timeout=5)
                r.raise_for_status()
                models = [m["name"] for m in r.json().get("models", [])]

            if not models:
                print(f"로컬 LLM에 설치된 모델이 없습니다. {'LM Studio' if is_lm_studio else 'Ollama'}에서 모델을 먼저 준비하세요.")
                sys.exit(1)

            model = models[0]
            print(f"자동 선택 모델: {model}")
        except Exception as e:
            print(f"로컬 LLM 연결 실패 ({ollama_url}): {e}")
            print(f"엔진이 실행 중인지 확인하세요: {'LM Studio (포트 1234)' if is_lm_studio else 'Ollama (포트 11434)'}")
            sys.exit(1)

    # ---- LLM 호출 ----
    try:
        if is_lm_studio:
            base = ollama_url.rstrip("/")
            if not base.endswith("/v1"):
                base = base + "/v1"
            r = requests.post(
                f"{base}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "max_tokens": 2048,
                },
                timeout=180,
            )
            r.raise_for_status()
            report = (
                r.json()
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
        else:
            r = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=180,
            )
            r.raise_for_status()
            report = r.json().get("response", "").strip()
    except Exception as e:
        print(f"LLM 호출 실패: {e}")
        sys.exit(1)

    # ---- 결과 출력 ----
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)

    # ---- 보고서 저장 ----
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(REPORT_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n\n# 트렌드 스나이핑 보고서 — {now}\n")
            f.write(f"## 키워드: {', '.join(chosen)}\n\n")
            f.write(report)
            f.write("\n\n---\n")
        print(f"\n보고서 저장 완료: {REPORT_PATH}")
    except Exception as e:
        print(f"보고서 저장 실패: {e}")


if __name__ == "__main__":
    main()