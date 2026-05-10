#!/usr/bin/env python3
"""
Channel Full Analysis — comprehensive overview of your YouTube channel.

Input  : youtube_account.json 에서 YOUTUBE_API_KEY + MY_CHANNEL_ID/HANDLE
Output : 채널 통계·패턴·추천이 담긴 마크다운 리포트
"""

import os
import json
import sys
import time
import datetime
import statistics
import re
import warnings
from collections import Counter

# ---- 콘솔 인코딩 방어 (Windows CMD cp949 대비) ----
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 원하면 FutureWarning 숨기기 (google.api_core 경고 등)
warnings.filterwarnings("ignore", category=FutureWarning)

HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNT = os.path.join(HERE, "youtube_account.json")
REPORT  = os.path.join(HERE, "channel_full_analysis_report.md")


def _load(p: str):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_channel_id(youtube, handle: str, channel_id: str):
    """핸들이 있으면 검색해서 채널 ID를 찾고, 없으면 기존 ID 사용."""
    if channel_id:
        return channel_id
    if not handle:
        return None

    h = handle.lstrip("@")
    try:
        r = youtube.search().list(
            part="snippet",
            q=h,
            type="channel",
            maxResults=1
        ).execute()
        items = r.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]
    except Exception as e:
        print(f"채널 ID 조회 실패: {e}")
    return None


def _parse_iso_duration(d: str) -> int:
    """ISO 8601 duration (PT4M30S) → seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + int(s or 0)


def _fmt_duration(sec: int) -> str:
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec//60}m {sec%60}s"
    return f"{sec//3600}h {(sec%3600)//60}m"


def _resolve_telegram(account: dict):
    """my_videos_check.py와 동일한 방식으로 텔레그램 설정 찾기."""
    import json as _json

    token = (account.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat  = (account.get("TELEGRAM_CHAT_ID") or "").strip()
    if token and chat:
        return token, chat

    brain_root = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
    sec_json = os.path.join(brain_root, "_agents", "secretary", "tools", "telegram_setup.json")

    if (not token or not chat) and os.path.exists(sec_json):
        try:
            with open(sec_json, "r", encoding="utf-8") as f:
                cfg = _json.load(f)
            if not token:
                token = (cfg.get("TELEGRAM_BOT_TOKEN") or "").strip()
            if not chat:
                chat  = (cfg.get("TELEGRAM_CHAT_ID") or "").strip()
        except Exception:
            pass

    return token, chat


def _push_telegram(account: dict, text: str):
    """텔레그램으로 요약 보고 전송 (옵션)."""
    token, chat = _resolve_telegram(account)
    if not token or not chat:
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        print("텔레그램으로 보고 전송 완료")
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")


def main():
    # ---- 0. 기본 설정 파일 확인 ----
    if not os.path.exists(ACCOUNT):
        print("youtube_account.json이 없어요. 외부 연결 패널에서 YouTube API 키와 채널 ID를 먼저 입력해주세요.")
        sys.exit(1)

    acct = _load(ACCOUNT)
    api_key = (acct.get("YOUTUBE_API_KEY") or "").strip()
    handle  = (acct.get("MY_CHANNEL_HANDLE") or "").strip()
    chan_id = (acct.get("MY_CHANNEL_ID") or "").strip()

    if not api_key:
        print("YOUTUBE_API_KEY가 비어있어요. 외부 연결 패널 → YouTube Data API 카드에 API 키를 입력해주세요.")
        sys.exit(1)
    if not (handle or chan_id):
        print("MY_CHANNEL_HANDLE 또는 MY_CHANNEL_ID가 필요합니다. 외부 연결 패널에서 채널 ID/핸들을 입력해주세요.")
        sys.exit(1)

    # ---- 1. YouTube 클라이언트 준비 ----
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("google-api-python-client가 설치되어 있지 않습니다.")
        print("터미널에서 다음 명령을 실행해주세요:")
        print("  pip3 install google-api-python-client requests")
        sys.exit(1)

    youtube = build("youtube", "v3", developerKey=api_key)

    # 채널 ID 결정
    cid = _resolve_channel_id(youtube, handle, chan_id)
    if not cid:
        print("채널 ID를 찾지 못했어요. youtube_account.json의 MY_CHANNEL_HANDLE / MY_CHANNEL_ID를 다시 확인해주세요.")
        sys.exit(1)

    print(f"[채널 완전 분석] 채널 {handle or cid} 분석 중...\n")

    # ---- 2. 채널 메타 정보 ----
    ch = youtube.channels().list(
        part="snippet,statistics,brandingSettings,contentDetails",
        id=cid
    ).execute()

    if not ch.get("items"):
        print("채널 데이터를 가져오지 못했습니다. API 키 또는 할당량을 확인해주세요.")
        sys.exit(1)

    c = ch["items"][0]
    sn = c.get("snippet", {})
    st = c.get("statistics", {})

    title = sn.get("title", "(이름 없음)")
    subs = int(st.get("subscriberCount", 0))
    total_views = int(st.get("viewCount", 0))
    video_count = int(st.get("videoCount", 0))
    pub_at = sn.get("publishedAt", "")[:10]

    print("─── 1. 채널 개요 ───")
    print(f"  채널: {title}")
    print(f"  핸들: {sn.get('customUrl', handle or '(없음)')}")
    print(f"  구독자: {subs:,}명")
    print(f"  총 조회수: {total_views:,}회")
    print(f"  업로드 영상: {video_count}개")
    print(f"  채널 개설일: {pub_at}")
    avg_per_video = total_views // max(1, video_count)
    print(f"  영상당 평균 조회수: {avg_per_video:,}회\n")

    # ---- 3. 최근 30일 영상 수집 (uploads playlist 우선) ----
    uploads = c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

    # contentDetails가 없었던 경우를 대비한 폴백
    if not uploads:
        cd = youtube.channels().list(part="contentDetails", id=cid).execute()
        if cd.get("items"):
            uploads = cd["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    recent_video_ids = []

    if uploads:
        next_token = None
        while len(recent_video_ids) < 50:
            args = {
                "part": "snippet,contentDetails",
                "playlistId": uploads,
                "maxResults": 50,
            }
            if next_token:
                args["pageToken"] = next_token

            pi = youtube.playlistItems().list(**args).execute()
            items = pi.get("items", [])

            for item in items:
                pub = item["snippet"]["publishedAt"]
                pub_dt = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pub_dt < cutoff:
                    break
                recent_video_ids.append(item["contentDetails"]["videoId"])

            next_token = pi.get("nextPageToken")
            if not next_token:
                break
            # 마지막 아이템이 컷오프보다 이전이면 종료
            if items and datetime.datetime.fromisoformat(items[-1]["snippet"]["publishedAt"].replace("Z", "+00:00")) < cutoff:
                break

    if not recent_video_ids:
        print("최근 30일 동안 업로드한 영상이 없습니다. 영상을 업로드한 뒤 다시 분석해주세요.")
        sys.exit(0)

    # ---- 4. 영상별 상세 통계 ----
    all_vids = []
    for i in range(0, len(recent_video_ids), 50):
        chunk = recent_video_ids[i : i + 50]
        st_resp = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(chunk),
        ).execute()

        for v in st_resp.get("items", []):
            stats = v.get("statistics", {})
            sn_v = v.get("snippet", {})
            cd_v = v.get("contentDetails", {})

            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            duration_sec = _parse_iso_duration(cd_v.get("duration", ""))
            pub = sn_v.get("publishedAt", "")
            pub_dt = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))

            all_vids.append(
                {
                    "id": v["id"],
                    "title": sn_v.get("title", ""),
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "duration_sec": duration_sec,
                    "pub_dt": pub_dt,
                    "engagement_rate": (likes + comments) / views if views > 0 else 0,
                }
            )

    all_vids.sort(key=lambda x: x["views"], reverse=True)
    views_list = [v["views"] for v in all_vids]
    median_views = statistics.median(views_list) if views_list else 0
    mean_views = statistics.mean(views_list) if views_list else 0

    print("─── 2. 최근 30일 업로드 패턴 ───")
    print(f"  업로드 횟수: {len(all_vids)}개 (월 기준)")
    weekday_counts = Counter(v["pub_dt"].strftime("%A") for v in all_vids)
    weekday_kr = {"Monday": "월", "Tuesday": "화", "Wednesday": "수",
                  "Thursday": "목", "Friday": "금", "Saturday": "토", "Sunday": "일"}
    top_day = weekday_counts.most_common(1)
    if top_day:
        print(f"  주로 업로드한 요일: {weekday_kr.get(top_day[0][0], top_day[0][0])}요일 ({top_day[0][1]}회)")

    avg_duration = sum(v["duration_sec"] for v in all_vids) / len(all_vids)
    print(f"  평균 영상 길이: {_fmt_duration(int(avg_duration))}\n")

    print("─── 3. 성과 통계 ───")
    print(f"  조회수 중간값: {int(median_views):,}회")
    print(f"  평균 조회수:   {int(mean_views):,}회")
    avg_eng = (
        sum(v["engagement_rate"] for v in all_vids) / len(all_vids) * 100
        if all_vids else 0
    )
    print(f"  평균 참여율 (좋아요+댓글)/조회: {avg_eng:.2f}%\n")

    # ---- 5. 떡상 / 부진 분류 ----
    hot = [v for v in all_vids if v["views"] >= median_views * 1.5]
    cold = [v for v in all_vids if v["views"] < median_views * 0.5]

    print("─── 4. 떡상 영상 (중간값 × 1.5 이상) ───")
    if not hot:
        print("  (없음 — 모든 영상이 평균 근처)")
    else:
        for v in hot[:5]:
            print(
                f"  {v['views']:>8,}회 · 참여 {v['engagement_rate']*100:.2f}% · "
                f"{_fmt_duration(v['duration_sec'])} · {v['title'][:50]}"
            )
    print()

    print("─── 5. 부진 영상 (중간값 × 0.5 미만) ───")
    if not cold:
        print("  (없음 — 모든 영상이 평균 근처)")
    else:
        for v in cold[:5]:
            print(
                f"  {v['views']:>8,}회 · 참여 {v['engagement_rate']*100:.2f}% · "
                f"{_fmt_duration(v['duration_sec'])} · {v['title'][:50]}"
            )
    print()

    # ---- 6. 패턴 비교 ----
    print("─── 6. 떡상 vs 부진 — 패턴 비교 ───")
    if hot and cold:
        hot_avg_dur = sum(v["duration_sec"] for v in hot) / len(hot)
        cold_avg_dur = sum(v["duration_sec"] for v in cold) / len(cold)
        hot_avg_title = sum(len(v["title"]) for v in hot) / len(hot)
        cold_avg_title = sum(len(v["title"]) for v in cold) / len(cold)

        print(f"  떡상 영상 평균 길이: {_fmt_duration(int(hot_avg_dur))}")
        print(f"  부진 영상 평균 길이: {_fmt_duration(int(cold_avg_dur))}")
        if abs(hot_avg_dur - cold_avg_dur) > 60:
            longer = "떡상" if hot_avg_dur > cold_avg_dur else "부진"
            print(
                f"  → {longer} 영상이 평균 {abs(int(hot_avg_dur - cold_avg_dur))}초 더 깁니다."
            )

        print(f"  떡상 영상 평균 제목 길이: {hot_avg_title:.0f}자")
        print(f"  부진 영상 평균 제목 길이: {cold_avg_title:.0f}자")
    else:
        print("  (떡상 또는 부진 데이터가 부족합니다 — 영상이 더 쌓이면 다시 분석해주세요.)")
    print()

    # ---- 7. 데이터 기반 추천 ----
    print("─── 7. 다음 액션 추천 (데이터 기반) ───")
    actions = []

    if hot:
        actions.append(
            f"떡상한 {len(hot)}개 영상의 제목·후크 패턴을 다음 영상에 적용 — "
            f"가장 잘 된 후크 예시: \"{hot[0]['title'][:50]}\""
        )
    if cold:
        actions.append(
            f"부진한 {len(cold)}개 영상은 썸네일 A/B 테스트 또는 제목 리네이밍 후보로 검토"
        )
    if avg_eng < 2.0:
        actions.append(
            f"평균 참여율 {avg_eng:.2f}% — 영상 말미에 명확한 CTA(좋아요·구독·댓글 유도)를 "
            "추가하면 보통 3% 이상까지 개선됩니다."
        )
    elif avg_eng > 5.0:
        actions.append(
            f"참여율 {avg_eng:.2f}% — 매우 건강한 수준입니다. 상품·멤버십·뉴스레터 등 "
            "수익화/팬 베이스 확장 수단을 실험해 볼 시점입니다."
        )
    if len(all_vids) < 4:
        actions.append("월 4개 미만 업로드 — 알고리즘 노출을 위해 최소 주 1회 업로드를 권장합니다.")
    elif len(all_vids) > 12:
        actions.append(
            "월 12개 이상 업로드 — 양은 충분하니, 영상별 후킹과 썸네일 퀄리티에 더 집중해보세요."
        )
    if not actions:
        actions.append(
            "채널 상태는 전반적으로 안정적입니다 — 시청자 댓글과 커뮤니티 탭에서 다음 콘텐츠 아이디어를 수집해 보세요."
        )

    for a in actions:
        print(f"  • {a}")
    print()

    # ---- 8. 마크다운 보고서 저장 ----
    now_str = time.strftime("%Y-%m-%d %H:%M")
    summary_lines = [
        f"# 채널 완전 분석 — {now_str}",
        f"채널: **{title}** · 구독자 **{subs:,}명** · 영상 **{video_count}개**",
        "",
        "## 최근 30일 통계",
        f"- 업로드: {len(all_vids)}개",
        f"- 조회수 중간값: **{int(median_views):,}회**",
        f"- 평균 참여율: **{avg_eng:.2f}%**",
        f"- 평균 영상 길이: **{_fmt_duration(int(avg_duration))}**",
        "",
        f"## 떡상 영상 ({len(hot)}개)",
    ]

    for v in hot[:5]:
        summary_lines.append(f"- {v['views']:,}회 · {v['title']}")

    summary_lines.append("")
    summary_lines.append(f"## 부진 영상 ({len(cold)}개)")
    for v in cold[:5]:
        summary_lines.append(f"- {v['views']:,}회 · {v['title']}")

    summary_lines.append("")
    summary_lines.append("## 다음 액션 (자동 추천)")
    for a in actions:
        summary_lines.append(f"- {a}")

    summary = "\n".join(summary_lines)

    with open(REPORT, "a", encoding="utf-8") as f:
        f.write("\n\n" + summary + "\n\n---\n")

    print(f"보고서 저장 완료: {REPORT}")
    _push_telegram(acct, summary)


if __name__ == "__main__":
    main()
