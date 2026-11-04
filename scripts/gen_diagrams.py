"""gen_diagrams.py — 第 1 层：生成「严格底图」

流程：plan.json → apiz 图片模型 → assets/diagrams/sNN.png → 上传 CDN → urls.json

底图是整片视频的「严格性来源」：结构对不对、中文标签准不准，全看这一步。
之后视频模型只负责让它动，不会改坏结构。

用法：
    python scripts/gen_diagrams.py plan.json [--force] [--only s01,s02]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lib_apiz as apiz
from lib_ledger import Ledger, fingerprint
from plan_schema import load_and_validate


def main() -> int:
    ap = argparse.ArgumentParser(description="生成科普视频严格底图")
    ap.add_argument("plan", help="plan.json 路径")
    ap.add_argument("--workdir", default=None, help="工作目录（默认取 plan.json 所在目录）")
    ap.add_argument("--force", action="store_true", help="已存在的底图也重新生成")
    ap.add_argument("--only", default=None, help="只处理这些 shot id，逗号分隔")
    ap.add_argument("--no-upload", action="store_true", help="不上传 CDN（后续步骤会失败）")
    ap.add_argument("--size", default=None, help="尺寸档位：1K / 2K / 4K")
    ap.add_argument("--quality", default=None,
                    help="质量档位：low / medium / high / xhigh / max")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else plan_path.parent
    plan = load_and_validate(plan_path)
    meta = plan["meta"]
    ledger = Ledger(workdir)

    only = set(args.only.split(",")) if args.only else None
    out_dir = workdir / "assets" / "diagrams"
    out_dir.mkdir(parents=True, exist_ok=True)
    urls_path = out_dir / "urls.json"

    # 复用上次的上传记录，避免重复上传
    urls: dict[str, str] = {}
    if urls_path.exists():
        try:
            urls = json.loads(urls_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            urls = {}

    targets = [
        s for s in plan["shots"]
        if (only is None or s["id"] in only) and (s.get("diagram") or {}).get("prompt")
    ]
    if not targets:
        print("[SKIP] 没有需要生成底图的拍")
        return 0

    apiz.check_ready()
    pts, yuan = apiz.balance()
    print(f"[余额] {pts:.2f} 积分 ({yuan:.2f} 元)")

    default_size = args.size or meta.get("image_size", apiz.DEFAULT_IMAGE_SIZE)
    default_quality = args.quality or meta.get("image_quality", apiz.DEFAULT_IMAGE_QUALITY)

    done, skipped, failed = 0, 0, []
    for shot in targets:
        sid = shot["id"]
        png = out_dir / f"{sid}.png"
        diag = shot["diagram"]
        model = diag.get("model") or meta["image_model"]
        ratio = diag.get("ratio") or meta["ratio"]

        # 合并参数：plan 里指定的 > 命令行 > meta > 库默认值
        params = dict(diag.get("params") or {})
        params.setdefault("size", default_size)
        params.setdefault("quality", default_quality)

        fp = fingerprint(
            model, diag["prompt"], kind="image",
            ratio=ratio, resolution=f"{params.get('size')}/{params.get('quality')}",
        )

        if png.exists() and not args.force:
            print(f"[跳过] {sid} 底图已存在: {png.name}")
            skipped += 1
        else:
            # ★ 幂等：同一份提示词已经付过费且文件还在 → 直接复用
            rec = ledger.find(fp)
            if rec and rec.get("status") == "done" and png.exists():
                print(f"[复用] {sid} 台账命中同一任务（已付 {rec.get('price')} 积分）")
                skipped += 1
            else:
                print(f"[生图] {sid}  model={model} ratio={ratio} "
                      f"size={params.get('size')} quality={params.get('quality')}")
                t0 = time.time()
                # 提交前先记账（崩了也知道钱花在哪）
                ledger.submit(fp, "image", sid)
                try:
                    _, info = apiz.generate_diagram(
                        prompt=diag["prompt"],
                        out_path=png,
                        model=model,
                        ratio=ratio,
                        params=params,
                    )
                except apiz.ApizError as e:
                    print(f"  [FAIL] {sid}: {e}")
                    ledger.fail(fp, str(e))
                    failed.append(sid)
                    continue
                ledger.complete(fp, info.get("task_id", ""), png, info.get("price", 0))
                print(f"  [OK] {png.name}  ({time.time() - t0:.0f}s, "
                      f"{info.get('price')} 积分, task={info.get('task_id', '')[:8]})")

        # 上传 CDN（视频模型需要公网 URL 才能读图）
        if args.no_upload:
            continue
        try:
            url = apiz.upload(png, folder="stem-explainer/diagrams")
        except apiz.ApizError as e:
            print(f"  [FAIL] {sid} 上传失败: {e}")
            failed.append(sid)
            continue
        urls[sid] = url
        print(f"  [上传] {url}")
        urls_path.write_text(
            json.dumps(urls, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        done += 1

    print(f"\n[汇总] 生成 {done} 张，跳过 {skipped} 张，失败 {len(failed)} 张")
    if failed:
        print(f"[失败] {', '.join(failed)}")
        return 1
    print(f"[下一步] python scripts/gen_animations.py {plan_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
