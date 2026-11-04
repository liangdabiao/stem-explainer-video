"""gen_narration.py — 第 3 层：生成旁白配音

流程：plan.json → apiz speak → assets/narration/sNN.mp3 → 读出真实时长

★ 为什么要读真实时长：
旁白的实际长度由 TTS 决定，和 plan 里写的 duration_sec 只是估算。
如果直接拿 duration_sec 去渲染视频，很容易出现「话没说完画面就切走」。
所以这里用 ffprobe 量出每段音频的真实时长，写进 timeline.json，
让 Remotion 按**音频实际长度**排每一拍。

用法：
    python scripts/gen_narration.py plan.json [--force] [--speed 1.1]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lib_apiz as apiz
from plan_schema import load_and_validate


def probe_duration(path: Path) -> float:
    """用 ffprobe 量音频时长（秒）。"""
    if not shutil.which("ffprobe"):
        raise RuntimeError("找不到 ffprobe，请先安装 ffmpeg 并加入 PATH")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {out.stderr.strip()}")
    try:
        return float(out.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"无法解析音频时长: {out.stdout!r}") from e


def main() -> int:
    ap = argparse.ArgumentParser(description="生成科普视频旁白配音")
    ap.add_argument("plan")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--speed", type=float, default=None, help="覆盖语速（0.5~2.0）")
    ap.add_argument("--voice", default=None, help="覆盖音色")
    ap.add_argument("--engine", default=None,
                    choices=["edge", "apiz", "auto"],
                    help="配音引擎（默认 edge，即 edge-tts；免费无限量）")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else plan_path.parent
    plan = load_and_validate(plan_path)
    meta = plan["meta"]

    out_dir = workdir / "assets" / "narration"
    out_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = out_dir / "timeline.json"

    only = set(args.only.split(",")) if args.only else None
    targets = [s for s in plan["shots"] if only is None or s["id"] in only]
    if not targets:
        print("[SKIP] 没有需要配音的拍")
        return 0

    voice = args.voice or meta["voice"]
    model = meta["tts_model"]
    speed = args.speed if args.speed is not None else meta["tts_speed"]
    engine = args.engine or meta.get("tts_engine", "edge")

    apiz.check_ready()
    pts, yuan = apiz.balance()
    print(f"[余额] {pts:.2f} 积分 ({yuan:.2f} 元)")
    print(f"[设置] engine={engine} voice={voice} model={model} speed={speed}")
    if engine == "edge" and not apiz.edge_tts_available():
        print("[WARN] 未安装 edge-tts。请执行 pip install edge-tts，"
              "或改用 --engine apiz（消耗积分）。")

    timeline: dict[str, dict] = {}
    if timeline_path.exists():
        try:
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            timeline = {}

    done, skipped, failed = 0, 0, []
    for shot in targets:
        sid = shot["id"]
        mp3 = out_dir / f"{sid}.mp3"
        text = str(shot["narration"]).strip()

        if mp3.exists() and not args.force:
            print(f"[跳过] {sid} 配音已存在: {mp3.name}")
            skipped += 1
        else:
            print(f"[配音] {sid}  {text[:40]}...")
            try:
                apiz.synth_voice(
                    text, mp3, engine=engine, voice=voice, model=model, speed=speed
                )
            except apiz.ApizError as e:
                print(f"  [FAIL] {sid}: {e}")
                failed.append(sid)
                continue
            print(f"  [OK] {mp3.name}")
            done += 1

        try:
            dur = probe_duration(mp3)
        except RuntimeError as e:
            print(f"  [FAIL] {sid} 量时长失败: {e}")
            failed.append(sid)
            continue

        timeline[sid] = {
            # ★ 路径必须相对 Remotion 的 public/ 目录
            #   本地文件在 assets/narration/，渲染时同步到 public/audio/narration/
            "audio": f"audio/narration/{sid}.mp3",
            "duration_sec": round(dur, 3),
            "planned_sec": shot.get("duration_sec"),
            "text": text,
        }
        flag = "" if abs(dur - float(shot.get("duration_sec", dur))) < 1.5 else "  ← 偏差>1.5s"
        print(f"  [时长] {sid}: {dur:.2f}s (计划 {shot.get('duration_sec')}s){flag}")

    timeline_path.write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[汇总] 生成 {done} 段，跳过 {skipped} 段，失败 {len(failed)} 段")
    print(f"[产出] {timeline_path}")
    if failed:
        print(f"[失败] {', '.join(failed)}")
        return 1
    print(f"[下一步] python scripts/build_storyboard.py {plan_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
