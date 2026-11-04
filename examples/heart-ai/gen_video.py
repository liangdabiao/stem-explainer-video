"""gen_video.py — 心脏样片「apiz 生视频路线」第 2 步：h3 首帧驱动生成视频

底图（无文字）→ minimax/h3 首帧驱动 → 有机的搏动/血流/瓣膜运动。

★ 为什么底图不带文字：
  AI 视频模型会把图上的文字扭成乱码。文字层全部交给 Remotion 叠加。

★ 为什么用 768P 而不是 480p：
  底图是 2K (1136x2048)。480p 拉到 720 宽会明显糊，
  而这次要检查的正是「AI 视频的画面质量」，糊了看不清。

幂等：指纹命中已付费任务 → 直接复用文件，绝不重复扣费。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib_apiz import check_ready, balance, generate_animation  # noqa: E402
from lib_ledger import Ledger, fingerprint, resume_from_task  # noqa: E402

WORK = HERE
DURATION = 12
RESOLUTION = "768P"
RATIO = "9:16"
MODEL = "minimax/h3"

FIRST_FRAME = "https://cdn-hk.51sux.com/storage/stem-explainer/heart-ai/20261104/977b2400c3f04d96917889d33954f01c.png"

# ── 动画提示词 ──
# 原则：只描述「什么在动」，并强约束「什么必须保持不动」。
# AI 视频模型最容易犯的错是自作主张地转镜头、拉变形、加文字。
PROMPT = """Medical animation of the beating human heart shown in this frontal cross-section view.

Motion: the heart beats continuously in a steady rhythm, roughly one full beat per second. The thick muscular heart wall squeezes inward and relaxes outward in a smooth pumping motion. The two lower ventricles contract firmly and release, visibly shrinking and re-expanding their inner cavities. The four chamber cavities rhythmically fill and empty. Blood visibly streams through the open chamber cavities and through the large tubes, flowing inward through the blue tubes on the left side of the image and outward through the red tubes on the right side of the image. The small pale valve flaps between the chambers swing open and closed in sync with each beat. The overall silhouette breathes with the heartbeat.

Keep fixed: the camera stays completely locked, no pan, no zoom, no rotation, no tilt. The anatomy, the chamber shapes, the color scheme and the pure white background stay exactly as they are in the first frame. Only the tissue deforms and the blood moves.

No text, no letters, no numbers, no labels, no watermark, no scene change, no morphing, no extra objects."""


def main() -> int:
    check_ready()
    pts0, yuan0 = balance()
    print(f"余额: {pts0:.0f} 积分 ({yuan0:.2f} 元)")

    out_dir = WORK / "assets" / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / "heart_main.mp4"

    lg = Ledger(WORK)
    fp = fingerprint(
        MODEL, PROMPT,
        first_frame=FIRST_FRAME, duration=DURATION,
        resolution=RESOLUTION, ratio=RATIO, kind="video",
    )

    # ── 幂等检查 ──
    rec = lg.find(fp)
    if rec and rec.get("status") == "done" and out_mp4.exists() and out_mp4.stat().st_size > 0:
        print(f"✓ 已有同指纹成片，直接复用（不扣费）: {out_mp4}")
        return 0

    # ── 断点续跑：上次已付费但文件没落地 → 取回，不重跑 ──
    if rec and rec.get("task_id"):
        print("检测到已提交的同指纹任务，尝试取回已付费成片 ...")
        got = resume_from_task(rec["task_id"], out_mp4)
        if got:
            lg.complete(fp, rec["task_id"], got, rec.get("price") or 0)
            print(f"✓ 已取回: {got}")
            return 0

    print(f"→ 生成视频 {DURATION}s @{RESOLUTION} @{RATIO} ...")
    lg.submit(fp, "video", "heart_main", price=DURATION * 18 + 7)

    path, info = generate_animation(
        PROMPT, out_mp4,
        first_frame_url=FIRST_FRAME,
        duration=DURATION,
        resolution=RESOLUTION,
        ratio=RATIO,
        model=MODEL,
    )
    lg.complete(fp, info.get("task_id", ""), path, info.get("price", 0))
    print(f"✓ 视频完成: {path}")
    print(f"  扣费 {info.get('price')} 积分  task={info.get('task_id')}")

    pts1, yuan1 = balance()
    print(f"\n本步花费: {pts0 - pts1:.0f} 积分  剩余: {pts1:.0f} 积分 ({yuan1:.2f} 元)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
