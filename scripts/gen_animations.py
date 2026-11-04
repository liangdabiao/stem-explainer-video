"""gen_animations.py — 第 2 层：把严格底图变成「复杂动效」

★ 这一层的设计是本 skill 的核心。科普片的说服力来自**动效的连续性与层次**，
不是来自单段动画好看。所以这里支持两种形态：

  ┌─ beats 链（多段接力）──────────────────────────────────────┐
  │  s01_b1.mp4  ① 底图驱动：水压逐渐增大                       │
  │      ↓ 上一段的末帧作为下一段的首帧                          │
  │  s01_b2.mp4  ② 接力：阀门开始转动                           │
  │      ↓                                                      │
  │  s01_b3.mp4  ③ 接力：水流喷出                               │
  └────────────────────────────────────────────────────────────┘
  → 三段拼起来是一条**连续演进**的物理过程，这才有科普价值。

  ┌─ 单段（简单动效）────────────────────────────────────────┐
  │  s02.mp4  底图驱动：水流平稳流动                             │
  └────────────────────────────────────────────────────────────┘

★ 三道防浪费机制（这是上一版最大的教训）：
  1. 幂等：内容指纹命中台账 → 直接复用，不发请求
  2. 断点续跑：台账里有 task_id 但文件缺失 → 用 apiz tasks get 取回已付费成片
  3. 提交前记账：崩了也知道钱花在哪

用法：
    python scripts/gen_animations.py plan.json [--force] [--only s01]
    python scripts/gen_animations.py plan.json --resolution 768P
    python scripts/gen_animations.py plan.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lib_apiz as apiz
from lib_ledger import Ledger, fingerprint, recover_pending
from plan_schema import load_and_validate


def extract_last_frame(video: Path, out_png: Path) -> Path:
    """抽取视频最后一帧（PNG），用来接力下一段。

    这是 beats 链的技术关键：上一段的末帧 = 下一段的首帧，
    于是多段动画在视觉上是连续的。
    """
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-sseof", "-0.5", "-i", str(video),
        "-frames:v", "1", str(out_png),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not out_png.exists() or out_png.stat().st_size == 0:
        raise RuntimeError(f"抽取末帧失败: {r.stderr.strip()[:200]}")
    return out_png


def upload_or_reuse(png: Path, url_cache: dict, key: str, folder: str) -> str:
    """上传图片到 CDN（带缓存，避免重复上传）。"""
    if key in url_cache:
        return url_cache[key]
    url = apiz.upload(png, folder=folder)
    url_cache[key] = url
    return url


def main() -> int:
    ap = argparse.ArgumentParser(description="用严格底图驱动视频动画生成")
    ap.add_argument("plan", help="plan.json 路径")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default=None, help="只处理这些 shot id，逗号分隔")
    ap.add_argument("--resolution", default=None, help="覆盖分辨率档位（480p/768P/1080p/2K）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要发的请求，不真跑")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else plan_path.parent
    plan = load_and_validate(plan_path)
    meta = plan["meta"]
    ledger = Ledger(workdir)

    urls_path = workdir / "assets" / "diagrams" / "urls.json"
    if not urls_path.exists():
        print(f"[FAIL] 找不到 {urls_path}\n请先跑 gen_diagrams.py")
        return 1
    urls = json.loads(urls_path.read_text(encoding="utf-8"))

    out_dir = workdir / "assets" / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = workdir / "assets" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    chain_urls_path = out_dir / "chain_urls.json"
    chain_urls: dict[str, str] = {}
    if chain_urls_path.exists():
        try:
            chain_urls = json.loads(chain_urls_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            chain_urls = {}

    only = set(args.only.split(",")) if args.only else None

    # ★ 断点续跑：先把上次「已付钱但没存下来」的成片救回来
    recovered = recover_pending(ledger, out_dir)
    if recovered:
        print(f"[恢复] 从台账取回 {len(recovered)} 段已付费成片（未重复扣费）：")
        for r in recovered:
            print(f"        {r}")

    # 收集目标：motion.type == 'ai' 的拍
    targets, skipped_by_motion = [], []
    for s in plan["shots"]:
        if only is not None and s["id"] not in only:
            continue
        motion = (s.get("motion") or {}).get("type", "still")
        if motion != "ai":
            skipped_by_motion.append((s["id"], motion))
            continue
        targets.append(s)

    if skipped_by_motion:
        groups: dict[str, list[str]] = {}
        for sid, m in skipped_by_motion:
            groups.setdefault(m, []).append(sid)
        for m, ids in groups.items():
            label = {"still": "静态底图+代码动效", "precise": "代码精确动画"}.get(m, m)
            print(f"[跳过 {len(ids)} 拍] motion.type={m}（{label}，不消耗 AI 视频额度）")
            print(f"         {', '.join(ids)}")
        print()

    if not targets:
        print("[SKIP] 没有 motion.type='ai' 的拍，本次不生成任何 AI 视频")
        print("[提示] 只有「运动本身就是知识点」的拍才值得用 AI 视频。")
        print("       其余用 still（静态图+高亮/推镜），成本为 0。")
        return 0

    resolution = args.resolution or meta["resolution"]
    ratio = meta["ratio"]
    model = meta["video_model"]

    apiz.check_ready()
    pts, yuan = apiz.balance()
    print(f"[余额] {pts:.2f} 积分 ({yuan:.2f} 元)")
    print(f"[设置] model={model} resolution={resolution} ratio={ratio}")

    # 统计这一轮要生成几段（先报数，让人知道要花多少）
    n_beats = sum(len(expand_beats(s)) for s in targets)
    print(f"[计划] {len(targets)} 拍，展开为 {n_beats} 段 AI 视频\n")

    done, skipped, failed = 0, 0, []
    for shot in targets:
        sid = shot["id"]
        beats = expand_beats(shot)
        prev_url: str | None = None   # 上一段末帧的公网 URL（接力用）

        for beat in beats:
            bid = beat["id"]
            mp4 = out_dir / f"{sid}_{bid}.mp4" if len(beats) > 1 else out_dir / f"{sid}.mp4"
            prompt = beat["prompt"]
            duration = int(round(float(beat.get("duration") or shot["duration_sec"])))

            # ---- 确定首帧 ----
            first_url = prev_url
            if first_url is None:
                if beat.get("first_frame") == "diagram" or first_url is None:
                    first_url = urls.get(sid)
                if not first_url:
                    # 没有底图 → 这一段没有严格性来源，跳过
                    if beat.get("first_frame") == "prev":
                        print(f"[FAIL] {sid}/{bid} 需要上一段接力，但没有可用的首帧")
                        failed.append(f"{sid}/{bid}")
                        continue
                    first_url = urls.get(sid)
            if not first_url:
                print(f"[FAIL] {sid}/{bid} 没有底图 URL，先跑 gen_diagrams.py")
                failed.append(f"{sid}/{bid}")
                continue

            last_url = beat.get("last_frame_url") or urls.get(f"{sid}__last")

            fp = fingerprint(
                model, prompt, first_frame=first_url, last_frame=last_url or "",
                duration=duration, resolution=resolution, ratio=ratio, kind="video",
            )

            # ---- 幂等检查 ----
            if mp4.exists() and not args.force:
                print(f"[跳过] {sid}/{bid} 已存在: {mp4.name}")
                skipped += 1
                prev_url = chain_urls.get(f"{sid}_{bid}") or prev_url
                continue

            rec = ledger.find(fp)
            if rec and rec.get("status") == "done" and mp4.exists():
                print(f"[复用] {sid}/{bid} 台账命中（已付 {rec.get('price')} 积分）")
                skipped += 1
                continue

            # ---- 断点续跑：已付费但文件不在 → 取回而不是重新生成 ----
            if rec and rec.get("task_id"):
                got = recover_one(rec["task_id"], mp4)
                if got:
                    print(f"[续跑] {sid}/{bid} 取回已付费成片 {mp4.name}（未重复扣费）")
                    ledger.complete(fp, rec["task_id"], mp4, rec.get("price") or 0)
                    done += 1
                    prev_url = chain_tail_url(got, sid, bid, chain_urls,
                                              frames_dir, chain_urls_path)
                    continue

            if args.dry_run:
                payload = {
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": first_url},
                         "role": "first_frame"},
                    ] + ([{"type": "image_url", "image_url": {"url": last_url},
                           "role": "last_frame"}] if last_url else []),
                    "duration": duration,
                    "resolution": resolution,
                    "ratio": ratio,
                }
                print(f"[DRY] {sid}/{bid}: {json.dumps(payload, ensure_ascii=False)[:400]}")
                continue

            # ---- 真正生成 ----
            print(f"[动画] {sid}/{bid}  {duration}s {resolution}")
            t0 = time.time()
            ledger.submit(fp, "video", sid, bid)
            try:
                _, info = apiz.generate_animation(
                    prompt=prompt,
                    out_path=mp4,
                    first_frame_url=first_url,
                    last_frame_url=last_url,
                    duration=duration,
                    resolution=resolution,
                    ratio=ratio,
                    model=model,
                )
            except apiz.ApizError as e:
                print(f"  [FAIL] {sid}/{bid}: {e}")
                ledger.fail(fp, str(e))
                failed.append(f"{sid}/{bid}")
                continue
            ledger.complete(fp, info.get("task_id", ""), mp4, info.get("price", 0))
            print(f"  [OK] {mp4.name}  ({time.time() - t0:.0f}s, "
                  f"{info.get('price')} 积分, task={info.get('task_id', '')[:8]})")
            done += 1

            # ---- 接力：抽末帧 → 上传 → 作为下一段首帧 ----
            if len(beats) > 1:
                prev_url = chain_tail_url(mp4, sid, bid, chain_urls,
                                          frames_dir, chain_urls_path)

    total_spent = ledger.total_spent()
    print(f"\n[汇总] 生成 {done} 段，跳过 {skipped} 段，失败 {len(failed)} 段")
    print(f"[台账] 累计消费 {total_spent:.0f} 积分（{total_spent / 100:.2f} 元）")
    for sid, v in sorted(ledger.spent_by_shot().items()):
        print(f"        {sid}: {v:.0f} 积分")
    if failed:
        print(f"[失败] {', '.join(failed)}")
        return 1
    if not args.dry_run:
        print(f"[下一步] python scripts/gen_narration.py {plan_path}")
    return 0


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def expand_beats(shot: dict) -> list[dict]:
    """把一拍的动画配置展开成 beat 列表。

    两种写法都支持：
      A) 简写：shot.animation = {prompt, duration}          → 1 拍
      B) 链式：shot.animation.beats = [{prompt, duration}, …] → N 拍接力
    """
    anim = shot.get("animation") or {}
    beats = anim.get("beats")
    if isinstance(beats, list) and beats:
        out = []
        for i, b in enumerate(beats):
            b = dict(b)
            b.setdefault("id", f"b{i + 1}")
            b.setdefault("duration", anim.get("duration") or shot.get("duration_sec"))
            b.setdefault("first_frame", "diagram" if i == 0 else "prev")
            out.append(b)
        return out
    if anim.get("prompt"):
        return [{
            "id": "b1",
            "prompt": anim["prompt"],
            "duration": anim.get("duration") or shot.get("duration_sec"),
            "first_frame": "diagram",
        }]
    return []


def recover_one(task_id: str, mp4: Path) -> Path | None:
    """按 task_id 取回已付费成片。"""
    from lib_ledger import resume_from_task
    return resume_from_task(task_id, mp4)


def chain_tail_url(
    video: Path, sid: str, bid: str, cache: dict,
    frames_dir: Path, cache_path: Path,
) -> str | None:
    """抽末帧 → 上传 CDN → 返回 URL（用于接力下一段）。"""
    key = f"{sid}_{bid}"
    if key in cache:
        return cache[key]
    try:
        png = frames_dir / f"{sid}_{bid}_last.png"
        extract_last_frame(video, png)
        url = apiz.upload(png, folder="stem-explainer/frames")
    except (RuntimeError, apiz.ApizError) as e:
        print(f"  [WARN] 接力末帧处理失败: {e}")
        return None
    cache[key] = url
    try:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except OSError:
        pass
    return url


if __name__ == "__main__":
    raise SystemExit(main())
