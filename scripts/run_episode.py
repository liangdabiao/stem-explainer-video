"""run_episode.py — 一键跑完整条流水线

用法：
    python scripts/run_episode.py plan.json              # 完整流程
    python scripts/run_episode.py plan.json --skip-diagrams
    python scripts/run_episode.py plan.json --render-only # 只渲染（素材已就绪）

流程：
    1. gen_diagrams.py    严格底图（apiz 图片模型）
    2. gen_animations.py  首帧驱动动画（minimax/h3）
    3. gen_narration.py   旁白配音（apiz speak）
    4. build_storyboard.py 组装 storyboard.json
    5. render_episode.py  Remotion 渲染成片
    6. verify_media.py    成片质检（含音频波形体检）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def run(step: str, script: str, args: list[str]) -> bool:
    print(f"\n{'=' * 60}\n[{step}] {script}\n{'=' * 60}")
    cmd = [sys.executable, str(HERE / script)] + args
    t0 = time.time()
    proc = subprocess.run(cmd)
    dt = time.time() - t0
    if proc.returncode != 0:
        print(f"\n[{step}] 失败（退出码 {proc.returncode}，耗时 {dt:.0f}s）")
        return False
    print(f"\n[{step}] 完成（耗时 {dt:.0f}s）")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="科普视频一键流水线")
    ap.add_argument("plan")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--skip-diagrams", action="store_true")
    ap.add_argument("--skip-animations", action="store_true")
    ap.add_argument("--skip-narration", action="store_true")
    ap.add_argument("--render-only", action="store_true", help="只渲染与质检")
    ap.add_argument("--resolution", default=None, help="视频分辨率档位")
    ap.add_argument("--force", action="store_true", help="重新生成所有素材")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    plan = str(Path(args.plan).resolve())
    common = ["--workdir", args.workdir] if args.workdir else []
    force = ["--force"] if args.force else []

    if not args.render_only:
        if not args.skip_diagrams:
            if not run("1/7 底图", "gen_diagrams.py", [plan] + common + force):
                return 1
        if not args.skip_animations:
            extra = ["--resolution", args.resolution] if args.resolution else []
            if not run("2/7 动画", "gen_animations.py", [plan] + common + force + extra):
                return 1
        if not args.skip_narration:
            if not run("3/7 配音", "gen_narration.py", [plan] + common + force):
                return 1
        if not run("4/7 时长对齐", "fit_duration.py", [plan] + common):
            return 1
        if not run("5/7 组装", "build_storyboard.py", [plan] + common):
            return 1

    if not run("6/7 渲染", "render_episode.py", [plan] + common):
        return 1

    if not args.no_verify:
        workdir = args.workdir or str(Path(plan).parent)
        video = str(Path(workdir) / "out" / "episode.mp4")
        if not run("7/7 质检", "verify_media.py", [plan, "--workdir", workdir, "--video", video]):
            print("\n[完成] 成片已产出，但质检有问题，请按上面提示修复")
            return 1

    print("\n[完成] 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
