"""lib_ledger.py — 消费台账：让「重复扣费」在技术上不可能发生

★ 为什么需要这个文件：
上一次做样例时，s01 的视频被生成了 3 次（每次 79~91 积分），
但最终只用了最后一次。前两次的钱白花了，原因是：
  1. 没有台账 → 脚本不知道「这个任务已经付过钱了」
  2. 服务端已出片扣费，但本地校验失败 → 成片被丢弃 → 重跑又扣一次

本模块用三道机制堵住这个洞：

  ① 任务台账（ledger.jsonl）
     每次提交生成任务，**先**把 task_id 落盘，再等结果。
     崩了/断了也知道钱花在哪。

  ② 内容指纹（fingerprint）
     指纹 = sha256(模型 + 提示词 + 首尾帧 + 时长 + 分辨率 + 画幅)。
     指纹相同 = 同一个任务。已存在且文件在 → 直接复用，不发请求。

  ③ 断点续跑（resume）
     台账里有 task_id 但文件还没下载 → 用 `apiz tasks get` 把
     **已经付过钱的成片**取回来，绝不重新生成。

依赖：仅标准库 + lib_apiz。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from lib_apiz import ApizError, _run_apiz, download, extract_video_url

LEDGER_NAME = "ledger.jsonl"


# ---------------------------------------------------------------------------
# 指纹
# ---------------------------------------------------------------------------

def fingerprint(
    model: str,
    prompt: str,
    *,
    first_frame: str | None = None,
    last_frame: str | None = None,
    duration: int | None = None,
    resolution: str | None = None,
    ratio: str | None = None,
    kind: str = "video",
) -> str:
    """算内容指纹。相同指纹 = 同一个任务，绝不重复付费。

    只把「真正影响产出结果」的字段纳入指纹：
    改一个字的提示词会产生新指纹（结果可能不同，值得重做）；
    改无关参数不会（结果必然相同，不必重做）。
    """
    parts = [
        kind,
        model,
        (prompt or "").strip(),
        first_frame or "",
        last_frame or "",
        str(duration or ""),
        resolution or "",
        ratio or "",
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 台账读写
# ---------------------------------------------------------------------------

class Ledger:
    """消费台账（JSONL，每行一条记录）。

    记录格式：
        {"ts": "...", "kind": "video", "shot": "s01", "beat": "b1",
         "fingerprint": "ab12...", "task_id": "uuid", "price": 79,
         "status": "submitted|done|failed", "out": "assets/videos/s01_b1.mp4"}
    """

    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)
        self.path = self.workdir / LEDGER_NAME

    # -- 读 --

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def find(self, fp: str) -> dict | None:
        """按指纹找最新一条记录。"""
        hit = None
        for r in self.records():
            if r.get("fingerprint") == fp:
                hit = r
        return hit

    def total_spent(self) -> float:
        """累计消费（积分）。"""
        return float(sum(r.get("price") or 0 for r in self.records()))

    def spent_by_shot(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in self.records():
            sid = r.get("shot") or "?"
            out[sid] = out.get(sid, 0.0) + float(r.get("price") or 0)
        return out

    # -- 写 --

    def append(self, rec: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(rec)
        rec.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def submit(self, fp: str, kind: str, shot: str, beat: str | None = None,
               price: float = 0) -> None:
        """提交任务**之前**落一条 status=submitted 的记录。

        这样即使进程当场崩溃，也知道钱花出去了。
        """
        self.append({
            "kind": kind, "shot": shot, "beat": beat, "fingerprint": fp,
            "status": "submitted", "price": price,
        })

    def complete(self, fp: str, task_id: str, out_path: str | Path,
                 price: float = 0) -> None:
        self.append({
            "kind": "video", "fingerprint": fp, "task_id": task_id,
            "status": "done", "price": price, "out": str(out_path),
        })

    def fail(self, fp: str, reason: str = "") -> None:
        self.append({
            "kind": "video", "fingerprint": fp,
            "status": "failed", "reason": reason[:300],
        })


# ---------------------------------------------------------------------------
# 断点续跑：用 task_id 取回已付费的成片
# ---------------------------------------------------------------------------

def resume_from_task(task_id: str, out_path: str | Path) -> Path | None:
    """按 task_id 取回已经付过费的成片。

    ★ 这是「不重复扣费」的最后一道保险：
    如果上一轮脚本崩在「服务端已出片、本地没保存」，重跑时
    走这条路径，**一分钱都不花**。

    取不到（任务不存在/失败）返回 None。
    """
    try:
        data = _run_apiz(["tasks", "get", task_id], timeout=120, retries=1)
    except ApizError:
        return None
    if not data:
        return None
    status = str(data.get("status", "")).lower()
    if status != "completed":
        return None
    try:
        url = extract_video_url(data)
    except ApizError:
        return None
    try:
        return download(url, out_path)
    except Exception:
        return None


def recover_pending(ledger: Ledger, out_dir: str | Path) -> list[str]:
    """扫描台账，把「已提交但文件不在」的记录用 task_id 救回来。

    返回救回来的文件路径列表。
    """
    out_dir = Path(out_dir)
    recovered: list[str] = []
    for rec in ledger.records():
        if rec.get("status") != "submitted":
            continue
        task_id = rec.get("task_id")
        if not task_id:
            continue
        shot = rec.get("shot") or "unknown"
        beat = rec.get("beat") or ""
        name = f"{shot}_{beat}.mp4" if beat else f"{shot}.mp4"
        target = out_dir / name
        if target.exists() and target.stat().st_size > 0:
            continue
        got = resume_from_task(task_id, target)
        if got:
            ledger.complete(rec.get("fingerprint", ""), task_id, got,
                            rec.get("price") or 0)
            recovered.append(str(got))
    return recovered


if __name__ == "__main__":
    import sys
    wd = sys.argv[1] if len(sys.argv) > 1 else "."
    lg = Ledger(wd)
    recs = lg.records()
    print(f"台账: {lg.path}")
    print(f"记录数: {len(recs)}   累计消费: {lg.total_spent():.0f} 积分")
    by = lg.spent_by_shot()
    if by:
        print("按拍分布:")
        for k, v in sorted(by.items()):
            print(f"  {k}: {v:.0f} 积分")
