"""fit_duration.py — 让每拍的画面时长对齐旁白时长

★ 为什么需要这个：
AI 视频的时长受 h3 限制（4~15 秒，且只能整数秒），
而旁白长度由内容决定（TTS 实测出来）。
两者很容易打架 —— 典型症状是「话没说完画面就切走」。

两种补齐策略：
  loop   把视频循环播放到够长（运动是周期性的：流动、旋转、振动 → 首选）
  freeze 冻结在最后一帧（画面是静态的 → 用 still 层根本不需要这一步）

对 still 层（静态底图）完全不需要处理 —— 画面本身就是静态的，
时序完全由 Remotion 控制，天然与旁白对齐。

用法：
    python scripts/fit_duration.py plan.json
    python scripts/fit_duration.py plan.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_schema import load_and_validate

# 循环后允许的最大时长（防止无限循环）
MAX_LOOP_SEC = 30.0


def probe_duration(path: Path) -> float:
    if not shutil.which("ffprobe"):
        raise RuntimeError("找不到 ffprobe，请先安装 ffmpeg")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {out.stderr.strip()}")
    return float(out.stdout.strip())


def loop_video(src: Path, dst: Path, target_sec: float) -> None:
    """把视频循环到指定时长。

    用 -stream_loop -1 输入循环，再 -t 截断。视频流用 copy（不重编码，省时间），
    音频流重编码（循环拼接处音频会断，必须重新编码保证连续）。
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-stream_loop", "-1", "-i", str(src),
        "-t", f"{target_sec:.3f}",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 循环失败: {r.stderr.strip()[:300]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="让画面时长对齐旁白时长")
    ap.add_argument("plan")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else plan_path.parent
    plan = load_and_validate(plan_path)

    timeline_path = workdir / "assets" / "narration" / "timeline.json"
    if not timeline_path.exists():
        print(f"[FAIL] 找不到 {timeline_path}\n请先跑 gen_narration.py")
        return 1
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    vids = workdir / "assets" / "videos"
    fitted_dir = vids / "fitted"
    fitted_dir.mkdir(parents=True, exist_ok=True)

    adjusted, skipped, failed = 0, 0, []
    for shot in plan["shots"]:
        sid = shot["id"]
        motion_type = (shot.get("motion") or {}).get("type", "still")

        tl = timeline.get(sid)
        if not tl:
            skipped += 1
            continue
        need = float(tl["duration_sec"]) + 0.4  # 与 build_storyboard 的 TAIL_PAD 一致

        if motion_type != "ai":
            # 静态层画面本身就是静态的，时序由 Remotion 控制，天然对齐
            print(f"[跳过] {sid}  motion.type={motion_type}（静态画面，天然对齐）")
            skipped += 1
            continue

        mp4 = vids / f"{sid}.mp4"
        if not mp4.exists():
            print(f"[FAIL] {sid} 缺少视频 {mp4.name}")
            failed.append(sid)
            continue

        have = probe_duration(mp4)
        if have >= need - 0.05:
            print(f"[OK]   {sid}  视频 {have:.2f}s ≥ 旁白 {need:.2f}s，无需处理")
            skipped += 1
            continue

        if need > MAX_LOOP_SEC:
            print(f"[FAIL] {sid} 需要 {need:.2f}s，超过上限 {MAX_LOOP_SEC}s。"
                  "请缩短旁白或拆成两拍。")
            failed.append(sid)
            continue

        print(f"[调整] {sid}  视频 {have:.2f}s < 旁白 {need:.2f}s → 循环补齐")
        if args.dry_run:
            continue
        out = fitted_dir / f"{sid}.mp4"
        try:
            loop_video(mp4, out, need)
        except RuntimeError as e:
            print(f"  [FAIL] {e}")
            failed.append(sid)
            continue
        got = probe_duration(out)
        print(f"  [OK] {out.name}  {got:.2f}s")
        adjusted += 1

    print(f"\n[汇总] 调整 {adjusted} 拍，跳过 {skipped} 拍，失败 {len(failed)} 拍")
    if failed:
        return 1
    if adjusted and not args.dry_run:
        print("[下一步] build_storyboard.py 会自动优先使用 assets/videos/fitted/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
