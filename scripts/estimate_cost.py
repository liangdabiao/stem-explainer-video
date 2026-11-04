"""estimate_cost.py — 花钱前的成本预估

★ 这个脚本存在的理由：
科普片的成本几乎全部来自 AI 视频（79 积分/段），
而大多数镜头**不需要** AI 视频。先估算再执行，避免误跑。

★ 会计必须准：
  - beats 链的每一段都要单独计费（这是最容易算错的地方）
  - 视频时长不同价格不同：h3 按秒计价，不是按段计价
  - 图片模型单价随模型/尺寸档位变化

用法：
    python scripts/estimate_cost.py plan.json
    python scripts/estimate_cost.py plan.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_schema import load_and_validate

# ── 实测单价 ──
# h3 按秒计价：480p=12 积分/秒，768P=18，1080p=28，2K=30
# 每次请求额外收 Context 7 积分；图片前 5 张免费
VIDEO_PER_SEC = {"480p": 12, "768P": 18, "1080p": 28, "2K": 30}
CONTEXT_COST = 7
COST_IMAGE = 6            # 积分/张（2K/medium 实测）
COST_TTS_PER_CHAR = 0.05  # 积分/字（edge-tts 免费，此项为 0 的占位）


def count_video_segments(shot: dict) -> list[int]:
    """返回这一拍会生成几段 AI 视频，以及各段时长。"""
    motion = shot.get("motion") or {}
    if motion.get("type") != "ai":
        return []
    anim = shot.get("animation") or {}
    beats = anim.get("beats") or []
    if beats:
        out = []
        for b in beats:
            d = b.get("duration")
            if d is None:
                d = shot.get("duration_sec", 6)
            out.append(int(round(float(d))))
        return out
    d = anim.get("duration") or shot.get("duration_sec", 6)
    return [int(round(float(d)))]


def main() -> int:
    ap = argparse.ArgumentParser(description="科普视频成本预估")
    ap.add_argument("plan")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    plan = load_and_validate(Path(args.plan).resolve())
    meta = plan["meta"]
    shots = plan["shots"]

    res = meta.get("resolution", "480p")
    per_sec = VIDEO_PER_SEC.get(res, 12)

    n_img = len(shots)
    ai_shots, still_shots = [], []
    seg_durations: list[int] = []
    seg_detail: list[str] = []

    for s in shots:
        t = (s.get("motion") or {}).get("type", "still")
        if t == "ai":
            ai_shots.append(s)
            for d in count_video_segments(s):
                seg_durations.append(d)
                seg_detail.append(f"{s['id']}:{d}s")
        else:
            still_shots.append(s)

    n_seg = len(seg_durations)
    total_video_sec = sum(seg_durations)
    chars = sum(len(s["narration"]) for s in shots)

    img_cost = n_img * COST_IMAGE
    # 每段 = 时长 × 每秒单价 + Context 7
    vid_cost = total_video_sec * per_sec + n_seg * CONTEXT_COST
    tts_cost = 0.0 if meta.get("tts_engine", "edge") == "edge" else round(chars * COST_TTS_PER_CHAR, 1)
    total = img_cost + vid_cost + tts_cost

    # 反事实：假如每拍都用 AI 视频（每拍按本集平均时长）
    avg_sec = (total_video_sec / n_seg) if n_seg else float(
        sum(float(s.get("duration_sec", 6)) for s in shots) / max(1, len(shots))
    )
    naive = img_cost + (len(shots) * int(round(avg_sec)) * per_sec + len(shots) * CONTEXT_COST) + tts_cost
    saved = naive - total

    result = {
        "shots_total": len(shots),
        "shots_ai": len(ai_shots),
        "shots_still": len(still_shots),
        "video_segments": n_seg,
        "video_total_sec": total_video_sec,
        "resolution": res,
        "cost_image": img_cost,
        "cost_video": vid_cost,
        "cost_tts": tts_cost,
        "total": round(total, 1),
        "total_yuan": round(total / 100, 2),
        "naive_all_ai_yuan": round(naive / 100, 2),
        "saved_yuan": round(saved / 100, 2),
        "saved_pct": round(saved / naive * 100, 1) if naive else 0,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("=== 成本预估 ===")
    print(f"总拍数: {len(shots)}")
    print(f"  AI 视频层: {len(ai_shots)} 拍 → 展开 {n_seg} 段，共 {total_video_sec} 秒")
    print(f"  静态+代码动效: {len(still_shots)} 拍 → 0 积分")
    if seg_detail:
        print(f"  分段: {', '.join(seg_detail)}")
    print()
    print(f"底图 {n_img} 张          : {img_cost} 积分")
    print(f"视频 {n_seg} 段 {total_video_sec}s @{res} : {vid_cost} 积分")
    if tts_cost:
        print(f"配音 {chars} 字          : {tts_cost} 积分")
    else:
        print(f"配音 {chars} 字          : 0 积分（edge-tts 本地免费）")
    print(f"{'─' * 34}")
    print(f"合计: {result['total']} 积分 ≈ {result['total_yuan']} 元")
    print()
    if n_seg < len(shots):
        print(f"对比「每拍都用 AI 视频」: {result['naive_all_ai_yuan']} 元")
        print(f"  → 节省 {result['saved_yuan']} 元（{result['saved_pct']}%）")
    else:
        print("⚠️ 每一拍都用 AI 视频。")
        print("   请检查：只有「运动本身就是知识点」的拍才需要 AI 视频。")
        print("   结构图/剖面图/流程图 → 改成 motion.type='still'，成本降为 0。")
    print()
    print("★ 下一步花钱前请确认：")
    print(f"  1. AI 段数 {n_seg} 段是否都必要？（每一段都必须在 motion.ai_reason 里说清理由）")
    print(f"  2. 底图 {n_img} 张是否都要重生成？（已存在的会被跳过）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
