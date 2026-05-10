#!/usr/bin/env python3
"""
Auto Planner — 설정된 간격으로 trend_sniper.py를 반복 실행하는 스케줄러.

- 설정 파일: auto_planner.json
    - INTERVAL_HOURS: 실행 간격 (시간)
    - TOTAL_RUN_HOURS: 총 가동 시간 (0이면 무한 루프 = 자율 모드)

- trend_sniper.py, trend_sniper.json, youtube_account.json 과 같은 폴더에 있어야 합니다.
"""

import os
import json
import time
import datetime
import subprocess
import sys

# ---- 콘솔 인코딩 방어 (Windows CMD cp949) ----
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "auto_planner.json")
SNIPER_PATH = os.path.join(HERE, "trend_sniper.py")


def load_config():
    """auto_planner.json 로드."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"설정 파일을 읽을 수 없어요: {CONFIG_PATH}\n{e}")
        sys.exit(1)


def main():
    cfg = load_config()

    # v2.89.71: 디폴트 6시간 / TOTAL_RUN_HOURS=0 => 무한 루프
    interval_h = float(cfg.get("INTERVAL_HOURS", 6))
    total_h = float(cfg.get("TOTAL_RUN_HOURS", 0))

    # 안내 메시지
    if total_h <= 0:
        print(f"\n[오토 플래너] 24시간 자율 모드 — {interval_h}시간마다 무한 반복")
        print("사용자가 중단(Ctrl+C)할 때까지 계속 실행됩니다.")
    else:
        print(f"\n[오토 플래너] {total_h}시간 동안 {interval_h}시간마다 트렌드 분석 (제한 모드)")
        print(f"종료까지 {total_h}시간 동안 채팅창을 점유합니다. Ctrl+C로 중단 가능합니다.")
    print()

    # trend_sniper.py 존재 확인
    if not os.path.exists(SNIPER_PATH):
        print(f"trend_sniper.py를 찾을 수 없어요: {SNIPER_PATH}")
        sys.exit(1)

    # ---- 첫 회차 검증: trend_sniper.py를 한 번 돌려 보고 바로 실패 여부 확인 ----
    print("trend_sniper.py 첫 회차 검증 중 (~30초)...")

    env = os.environ.copy()
    # 자식 파이썬 프로세스의 I/O 인코딩을 UTF-8로 강제
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        test_proc = subprocess.run(
            [sys.executable, SNIPER_PATH],
            capture_output=True,   # stdout/stderr 캡처
            text=True,             # 문자열 모드
            encoding="utf-8",      # UTF-8로 디코딩
            errors="replace",      # 깨지는 문자는 대체 문자로
            timeout=300,           # 5분 이내
            env=env,
        )
    except Exception as e:
        print(f"trend_sniper.py 검증 실행 자체가 실패했습니다: {e}")
        sys.exit(1)

    if test_proc.returncode != 0:
        print(f"trend_sniper.py 검증 실패 (exit {test_proc.returncode})")
        print("   먼저 trend_sniper.py 단독으로 ▶ 실행해서 설정·키워드·LLM 연결을 확인한 뒤 재시도하세요.")
        if test_proc.stderr and test_proc.stderr.strip():
            print("   에러 일부:")
            for line in test_proc.stderr.splitlines()[-5:]:
                print(f"   {line}")
        sys.exit(1)

    print("검증 완료. 본 루프 시작.\n")

    # ---- 메인 루프 ----
    start = time.time()
    loop = 0

    while True:
        # total_h > 0 이면 제한 모드: 누적 가동 시간이 목표를 넘으면 종료
        if total_h > 0 and (time.time() - start > total_h * 3600):
            print("\n목표 가동 시간을 채웠어요. 종료합니다.")
            break

        loop += 1
        now = datetime.datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        elapsed_h = (time.time() - start) / 3600

        print(f"\n[{ts}] {loop}회차 트렌드 스나이핑 실행 (가동 {elapsed_h:.1f}시간 경과)")

        try:
            # 여기서는 출력 캡처 없이 바로 터미널로 내보냄
            subprocess.run(
                [sys.executable, SNIPER_PATH],
                check=False,
                env=env,  # 위에서 만든 UTF-8 환경 재사용
            )
        except Exception as e:
            print(f"trend_sniper.py 실행 실패: {e}")

        next_at = now + datetime.timedelta(hours=interval_h)
        print(f"다음 실행 예정 시각: {next_at.strftime('%Y-%m-%d %H:%M')} (약 {interval_h}시간 후)")

        # 다음 회차까지 대기
        time.sleep(interval_h * 3600)


if __name__ == "__main__":
    main()