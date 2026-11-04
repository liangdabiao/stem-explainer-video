"""gen_heart_ai.py — 心脏样片「apiz 生视频路线」第 1 步：生成底图

只做底图，不做视频。底图要先人工/视觉检查通过，再付视频的钱。

产物：
    assets/diagrams/heart_main.png   心脏剖面底图（无任何文字）
    assets/diagrams/first_frame_url.txt  上传后的公网 URL（供 h3 首帧驱动）

★ 底图为什么不带文字：
  AI 视频模型会把图上的文字扭成乱码。所以底图只画结构，
  所有中文标注交给 Remotion 叠加层精确绘制。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]          # skill 根
sys.path.insert(0, str(ROOT / "scripts"))

from lib_apiz import check_ready, balance, generate_diagram, upload  # noqa: E402
from lib_ledger import Ledger, fingerprint  # noqa: E402

WORK = HERE

# ── 底图提示词：9 段式（见 references/diagram-rules.md） ──
PROMPT = """Medical 3D illustration of a human heart, frontal coronal cross-section, anatomical textbook accuracy.

Type: 3D medical illustration, frontal cross-section view of a human heart.

Subject: A human heart cut open in frontal coronal section showing all four chambers clearly separated by the septum: the right atrium in the upper right of the image, the right ventricle in the lower right of the image, the left atrium in the upper left of the image, the left ventricle in the lower left of the image. Four thin flap-like heart valves are visible as small pale structures: two between the atria and the ventricles, two at the outlets of the ventricles. The superior vena cava and inferior vena cava are wide blue tubes entering the right atrium from the lower right. The pulmonary artery is a blue tube leaving the right ventricle. The pulmonary veins are two red tubes entering the left atrium from the upper left. The aorta is a large red tube leaving the left ventricle and arching over the top of the heart. The heart wall is thick muscular tissue.

Layout: vertical portrait, the heart centered in the upper two-thirds of the canvas, the entire heart fits within the central 82% of the canvas with clear white margin on all four sides, generous empty margin at the bottom of the canvas.

Style: soft 3D medical rendering, matte clay-like material, soft studio lighting, gentle ambient occlusion, clean scientific textbook look, no photorealistic skin texture, no gore, no blood splatter.

Color scheme: right-side chambers and the vena cava and pulmonary artery in blue #2563eb, left-side chambers and the pulmonary veins and aorta in red #ef4444, muscular heart wall in deep rose #9f1239, valve structures in pale cream #f5f0e1, background pure white #FFFFFF.

Labels: NO text, NO letters, NO numbers, NO arrows, NO labels, NO legend, NO watermark anywhere in the image.

Quality: publication-ready, crisp clean contours, high contrast, medical textbook anatomical accuracy, clean and uncluttered composition.

Constraints: no watermark, no extra text, no garbled characters, no distortion, no anatomical error, nothing cropped, all elements fully within the canvas.

Background: pure white background #FFFFFF."""


def main() -> int:
    check_ready()
    pts, yuan = balance()
    print(f"余额: {pts:.0f} 积分 ({yuan:.2f} 元)")

    out_dir = WORK / "assets" / "diagrams"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "heart_main.png"

    lg = Ledger(WORK)
    fp = fingerprint("apiz/gpt-image-2.5-flare", PROMPT, kind="image")

    # 幂等：已生成过就直接复用，不重复扣费
    rec = lg.find(fp)
    if rec and rec.get("status") == "done" and out_png.exists():
        print("底图已存在且指纹匹配，跳过生图（不重复扣费）")
    else:
        lg.submit(fp, "image", "heart_main", price=23)
        print("→ 生成底图 2K/high ...（约 40 秒）")
        path, info = generate_diagram(
            PROMPT, out_png,
            model="apiz/gpt-image-2.5-flare",
            ratio="9:16",
            params={"size": "2K", "quality": "high"},
        )
        lg.complete(fp, info.get("task_id", ""), path, info.get("price", 0))
        print(f"底图完成: {path}  扣费 {info.get('price')} 积分  task={info.get('task_id')}")

    # 上传拿公网 URL（供 h3 首帧驱动）
    url_file = out_dir / "first_frame_url.txt"
    if url_file.exists() and url_file.read_text(encoding="utf-8").strip():
        url = url_file.read_text(encoding="utf-8").strip()
        print("首帧 URL 已存在，跳过上传")
    else:
        print("→ 上传到 apiz CDN ...")
        url = upload(out_png, folder="stem-explainer/heart-ai")
        url_file.write_text(url, encoding="utf-8")
        print("首帧 URL:", url)

    pts2, yuan2 = balance()
    print(f"\n本步花费: {pts - pts2:.0f} 积分  剩余: {pts2:.0f} 积分 ({yuan2:.2f} 元)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
