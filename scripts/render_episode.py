"""render_episode.py — Remotion 渲染成片

流程：storyboard.json + assets/ → templates/remotion-project/ → out/episode.mp4

工程模板在 templates/remotion-project/（本 skill 自带，不依赖外部路径）。
本脚本会把 storyboard.json 和素材同步进工程目录，再调 `npm run render`。

首次使用需要先装依赖：
    cd templates/remotion-project && npm install

用法：
    python scripts/render_episode.py plan.json
    python scripts/render_episode.py plan.json --preview   # 低码率快渲
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
TEMPLATE_DIR = SKILL_ROOT / "templates" / "remotion-project"

# Windows 上 npm 是 .cmd 批处理，不能直接 subprocess（WinError 2）
# 用 shell=True 走 cmd/POSIX shell 才能找到它
IS_WIN = os.name == "nt"


def run_cmd(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """跑外部命令。Windows 下用 shell=True 以便找到 npm.cmd。"""
    return subprocess.run(
        cmd, cwd=cwd, shell=IS_WIN,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def find_npm() -> str | None:
    """定位 npm。Windows 下优先找 npm.cmd。"""
    for name in ("npm.cmd", "npm"):
        p = shutil.which(name)
        if p:
            return p
    return shutil.which("npm")


def sync_assets(workdir: Path) -> None:
    """把 storyboard.json 与素材同步进 Remotion 工程。"""
    storyboard = workdir / "storyboard.json"
    if not storyboard.exists():
        raise SystemExit(f"[FAIL] 找不到 {storyboard}，请先跑 build_storyboard.py")
    shutil.copy2(storyboard, TEMPLATE_DIR / "storyboard.json")

    assets_dst = TEMPLATE_DIR / "public" / "assets"
    for sub in ("videos", "diagrams"):
        src = workdir / "assets" / sub
        dst = assets_dst / sub
        dst.mkdir(parents=True, exist_ok=True)
        if src.exists():
            for f in src.iterdir():
                if f.is_file() and f.suffix in (".mp4", ".png", ".jpg"):
                    shutil.copy2(f, dst / f.name)

    # fitted/ 子目录：时长补齐过的视频
    fitted_src = workdir / "assets" / "videos" / "fitted"
    fitted_dst = assets_dst / "videos" / "fitted"
    fitted_dst.mkdir(parents=True, exist_ok=True)
    if fitted_src.exists():
        for f in fitted_src.iterdir():
            if f.is_file() and f.suffix == ".mp4":
                shutil.copy2(f, fitted_dst / f.name)
    audio_dst = TEMPLATE_DIR / "public" / "audio" / "narration"
    audio_dst.mkdir(parents=True, exist_ok=True)
    audio_src = workdir / "assets" / "narration"
    if audio_src.exists():
        for f in audio_src.iterdir():
            if f.is_file() and f.suffix == ".mp3":
                shutil.copy2(f, audio_dst / f.name)


def main() -> int:
    ap = argparse.ArgumentParser(description="Remotion 渲染科普视频")
    ap.add_argument("plan")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--preview", action="store_true", help="低码率快速预览")
    ap.add_argument("--out", default=None, help="成片输出路径")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else plan_path.parent

    npm = find_npm()
    if not npm:
        print("[FAIL] 找不到 npm。请安装 Node.js (>=20) 并确保 npm 在 PATH 中。")
        return 1

    if not (TEMPLATE_DIR / "node_modules").exists():
        print("[准备] 首次使用，安装 Remotion 依赖（需要几分钟）...")
        r = run_cmd([npm, "install"], TEMPLATE_DIR)
        if r.returncode != 0:
            print(f"[FAIL] npm install 失败:\n{r.stdout[-1500:]}\n{r.stderr[-800:]}")
            return 1

    sync_assets(workdir)

    out_path = Path(args.out).resolve() if args.out else (workdir / "out" / "episode.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    npx = "npx.cmd" if IS_WIN and shutil.which("npx.cmd") else "npx"
    cmd = [
        npx, "remotion", "render", "src/index.ts", "StemVideo",
        str(out_path),
        "--codec=h264", "--pixel-format=yuv420p",
    ]
    cmd.append("--crf=23" if args.preview else "--crf=18")
    cmd += ["--concurrency=1", "--log=error"]

    print(f"[渲染] {out_path}")
    r = subprocess.run(cmd, cwd=TEMPLATE_DIR, shell=IS_WIN)
    if r.returncode != 0:
        print(f"[FAIL] 渲染失败（退出码 {r.returncode}）")
        return 1

    print(f"[OK] {out_path}  ({out_path.stat().st_size / 1048576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
