"""pad_diagram.py — 给底图加安全边距，防止结构/标签被裁切

★ 为什么需要：
AI 生图常把结构画到画面边缘（实测左右 12% 区域有 8~15% 的墨水），
而科普片的字幕条要占底部空间、术语卡要占顶部空间。
边缘的部件和中文标签一旦被裁掉，观众就看不到「管道」两个字在哪。

本脚本做两件事：
  1. 检查底图四边的墨水分布，报告哪些边「太满」
  2. 给四周加白边（letterbox），把内容完整收进安全区

用法：
    python scripts/pad_diagram.py plan.json            # 检查
    python scripts/pad_diagram.py plan.json --pad      # 加白边
    python scripts/pad_diagram.py plan.json --pad --margin 0.08
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_schema import load_and_validate

# 判定「太满」的阈值：该边缘区域内墨水占比超过此值就认为有东西贴边
EDGE_INK_LIMIT = 0.04   # 4%
# 检查范围：边缘各占画幅的比例
EDGE_SCAN = 0.12


def edge_ink_ratio(img) -> dict:
    """返回四边的墨水占比。"""
    from PIL import Image
    g = img.convert("L")
    w, h = g.size
    px = g.load()
    m, n = int(h * EDGE_SCAN), int(w * EDGE_SCAN)

    def frac(x0, y0, x1, y1):
        tot = dark = 0
        for y in range(y0, y1, 3):
            for x in range(x0, x1, 3):
                tot += 1
                if px[x, y] < 235:
                    dark += 1
        return dark / max(1, tot)

    return {
        "top": frac(0, 0, w, m),
        "bottom": frac(0, h - m, w, h),
        "left": frac(0, 0, n, h),
        "right": frac(w - n, 0, w, h),
    }


def pad_image(src: Path, dst: Path, margin: float) -> tuple[int, int]:
    """给底图四周加白边，原内容缩进 margin 比例。"""
    from PIL import Image
    im = Image.open(src).convert("RGB")
    w, h = im.size
    mx, my = int(w * margin), int(h * margin)
    new = Image.new("RGB", (w + mx * 2, h + my * 2), (255, 255, 255))
    new.paste(im, (mx, my))
    new.save(dst, "PNG")
    return new.size


def main() -> int:
    ap = argparse.ArgumentParser(description="检查/修补底图安全边距")
    ap.add_argument("plan")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--pad", action="store_true", help="实际加白边")
    ap.add_argument("--margin", type=float, default=0.06, help="白边比例（默认 0.06）")
    ap.add_argument("--replace", action="store_true", help="直接覆盖原图（默认另存 _padded.png）")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else plan_path.parent
    plan = load_and_validate(plan_path)

    from PIL import Image

    dg = workdir / "assets" / "diagrams"
    if not dg.exists():
        print(f"[FAIL] 找不到 {dg}\n请先跑 gen_diagrams.py")
        return 1

    needs_pad = []
    for shot in plan["shots"]:
        sid = shot["id"]
        if (shot.get("motion") or {}).get("type", "still") != "still":
            continue
        p = dg / f"{sid}.png"
        if not p.exists():
            continue

        with Image.open(p) as im:
            ratios = edge_ink_ratio(im)
        tight = [k for k, v in ratios.items() if v > EDGE_INK_LIMIT]
        mark = "⚠️ " if tight else "✓ "
        detail = " ".join(f"{k}={v * 100:.1f}%" for k, v in ratios.items())
        print(f"  {mark}{sid}: {detail}")
        if tight:
            needs_pad.append((sid, p, tight))

    if not needs_pad:
        print("\n[OK] 所有底图的安全边距都没问题")
        return 0

    print(f"\n[需要处理] {len(needs_pad)} 张底图有内容贴边: "
          f"{', '.join(s for s, _, _ in needs_pad)}")
    if not args.pad:
        print("[提示] 加 --pad 执行修补")
        return 0

    for sid, p, tight in needs_pad:
        dst = p if args.replace else p.with_name(f"{sid}_padded.png")
        size = pad_image(p, dst, args.margin)
        print(f"  [已修补] {sid} {tight} → {dst.name} {size}")

    print("\n[注意] 修补后的文件名带 _padded，构建 storyboard 时请同步更新引用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
