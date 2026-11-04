"""build_storyboard.py — 第 4 层：组装 storyboard.json

流程：plan.json + assets/narration/timeline.json → storyboard.json（Remotion 输入）

这一层是「确定性」的：字幕、术语卡片、时间轴全部由代码算出来，
不经过任何 AI 模型。所以字幕永远不会错字、时序永远不会漂。

★ 关键：每一拍的时长以**音频实际长度**为准（而不是 plan 里写的估算值），
这样不会出现「话没说完画面就切走」。

用法：
    python scripts/build_storyboard.py plan.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_schema import load_and_validate

# 旁白结束后的留白（秒），给观众消化的时间
TAIL_PAD = 0.4


def main() -> int:
    ap = argparse.ArgumentParser(description="组装 Remotion storyboard.json")
    ap.add_argument("plan")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--out", default=None, help="storyboard.json 输出路径")
    ap.add_argument("--strict", action="store_true", help="素材缺失时报错退出")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else plan_path.parent
    plan = load_and_validate(plan_path)
    meta = plan["meta"]

    timeline_path = workdir / "assets" / "narration" / "timeline.json"
    timeline = {}
    if timeline_path.exists():
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    scenes = []
    missing = []
    cost_ai = 0

    for shot in plan["shots"]:
        sid = shot["id"]
        tl = timeline.get(sid)
        motion = shot.get("motion") or {}
        motion_type = motion.get("type", "still")

        # ★ 素材按动效层分配
        videos_rel: list[str] = []
        still_rel = None
        if motion_type == "ai":
            # 多段接力：每一段一个文件
            beats = motion.get("beats") or []
            if beats:
                for i, b in enumerate(beats):
                    bid = b.get("id") or f"{sid}_{i + 1:02d}"
                    # 优先用 fit_duration 补齐过的版本
                    fitted = workdir / "assets" / "videos" / "fitted" / f"{bid}.mp4"
                    if fitted.exists():
                        videos_rel.append(f"assets/videos/fitted/{bid}.mp4")
                    else:
                        videos_rel.append(f"assets/videos/{bid}.mp4")
                video_rel = videos_rel[0] if videos_rel else None
                cost_ai += len(videos_rel)
            else:
                # 单段
                fitted = workdir / "assets" / "videos" / "fitted" / f"{sid}.mp4"
                if fitted.exists():
                    video_rel = f"assets/videos/fitted/{sid}.mp4"
                else:
                    video_rel = f"assets/videos/{sid}.mp4"
                videos_rel = [video_rel]
                cost_ai += 1
        else:
            video_rel = None
            still_rel = f"assets/diagrams/{sid}.png"

        # ★ 路径必须相对 Remotion 的 public/ 目录
        #   本地文件在 assets/narration/，渲染时同步到 public/audio/narration/
        audio_rel = (tl or {}).get("audio")
        if not audio_rel or not audio_rel.startswith("audio/"):
            audio_rel = f"audio/narration/{sid}.mp3"
        audio_local = workdir / "assets" / "narration" / f"{sid}.mp3"

        # 时长优先级：音频实测 > plan 估算
        if tl and tl.get("duration_sec"):
            duration = float(tl["duration_sec"]) + TAIL_PAD
        else:
            duration = float(shot.get("duration_sec", 6))

        # 素材存在性检查
        needed = [r for r in (video_rel, still_rel) if r]
        for rel in needed:
            if not (workdir / rel).exists():
                missing.append(f"{sid}: {rel}")
                break
        if not audio_local.exists():
            missing.append(f"{sid}: assets/narration/{sid}.mp3")

        # 静态层：读底图原始尺寸，交给 Remotion 做 cover 换算
        img_w = img_h = None
        if still_rel:
            still_path = workdir / still_rel
            if still_path.exists():
                try:
                    from PIL import Image
                    with Image.open(still_path) as im:
                        img_w, img_h = im.size
                except Exception:
                    pass

        scene = {
            "id": sid,
            "narration": shot["narration"],
            "narration_audio": audio_rel,
            "motion_video": video_rel,
            "motion_videos": videos_rel if len(videos_rel) > 1 else None,
            "still_image": still_rel,
            "duration_sec": round(duration, 3),
            # 字幕：优先用 shot 里的 caption，否则用旁白
            "caption": shot.get("caption") or shot["narration"],
            "title": shot.get("title"),
            # 术语卡片（四问中的「是什么」）
            "term": shot.get("term"),
            "term_def": shot.get("term_def"),
            # 讲解重点标注（叠加在画面上的确定性文字层）
            "annotations": shot.get("annotations") or [],
            # 动效配置
            "motion": {
                "type": motion_type,
                "zoomTo": motion.get("zoomTo"),
                "highlight": motion.get("highlight"),
                # ★ 代码矢量层（0 积分的精确表达）
                "vectors": motion.get("vectors") or [],
                # ★ AI 多段接力
                "beats": motion.get("beats") or [],
            },
            # 底图原始尺寸（静态层做 cover 换算用）
            "image_width": img_w,
            "image_height": img_h,
            # 知识点清单（用于结尾回顾卡）
            "takeaway": shot.get("takeaway"),
        }
        scenes.append(scene)

    storyboard = {
        "title": meta["title"],
        "lang": meta.get("lang", "zh"),
        "style": "stem",
        "width": int(meta["width"]),
        "height": int(meta["height"]),
        "fps": int(meta["fps"]),
        "ratio": meta["ratio"],
        "resolution": meta["resolution"],
        "theme": meta["theme"],
        "scenes": scenes,
    }

    out_path = Path(args.out) if args.out else (workdir / "storyboard.json")
    out_path.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = sum(s["duration_sec"] for s in scenes)
    n_ai = sum(1 for s in scenes if s["motion"]["type"] == "ai")
    n_still = sum(1 for s in scenes if s["motion"]["type"] != "ai")
    print(f"[OK] {out_path}")
    print(f"[统计] {len(scenes)} 拍，总时长 {total:.1f}s")
    print(f"[动效] AI 视频 {n_ai} 拍（{n_ai * 79} 积分），"
          f"静态+代码动效 {n_still} 拍（0 积分）")
    if missing:
        print(f"[警告] {len(missing)} 拍素材缺失：")
        for m in missing:
            print(f"  - {m}")
        if args.strict:
            return 1
    print(f"[下一步] python scripts/render_episode.py {plan_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
