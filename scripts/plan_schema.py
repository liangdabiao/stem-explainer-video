"""plan_schema.py — 科普视频计划（plan.json）的结构定义与校验

一个 plan 描述一集科普视频的全部内容：每一拍讲什么、画面底图长什么样、
怎么动、旁白念什么。整套流水线只认这一个文件。

最小示例见 examples/pipe-valve/plan.json。
"""

from __future__ import annotations

import json
from pathlib import Path

# 顶层必填字段
REQUIRED_TOP = ("meta", "shots")

# 每一拍必填字段
REQUIRED_SHOT = ("id", "narration")

# ★ 动效分层：这是控制成本的关键开关
#   still  —— 静态底图 + Remotion 代码动效（高亮/推镜/标注/矢量）。0 积分，默认
#   ai     —— 视频模型生成。79 积分/段。**只在运动本身是知识点时用**
MOTION_TYPES = ("still", "ai")

# 矢量元素的合法类型
VECTOR_KINDS = ("arrow", "poly", "path", "curve", "wave", "dot", "box", "label")

# meta 里建议给的字段（有合理默认值）
META_DEFAULTS = {
    "title": "未命名科普片",
    "lang": "zh",
    "width": 720,
    "height": 1280,
    "fps": 30,
    "ratio": "9:16",
    "resolution": "480p",
    "image_model": "apiz/gpt-image-2.5-flare",
    "image_size": "2K",
    "image_quality": "medium",
    "video_model": "minimax/h3",
    "voice": "zh-CN-YunxiNeural",
    "tts_engine": "edge",
    "tts_model": "speech-2.8-hd",
    "tts_speed": 1.0,
    "theme": {
        "bg": "#FFFFFF",
        "ink": "#171714",
        "accent": "#2563eb",
        "warn": "#ef4444",
        "muted": "#6b7280",
    },
}


def default_meta() -> dict:
    """返回带默认值的 meta。"""
    import copy
    return copy.deepcopy(META_DEFAULTS)


def load_plan(path: str | Path) -> dict:
    """读取 plan.json，填入 meta 默认值。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    meta = default_meta()
    meta.update(data.get("meta") or {})
    data["meta"] = meta
    return data


def validate(plan: dict) -> list[str]:
    """校验 plan，返回问题列表（空列表 = 通过）。"""
    problems: list[str] = []

    for key in REQUIRED_TOP:
        if key not in plan:
            problems.append(f"缺少顶层字段: {key}")
    if problems:
        return problems

    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        problems.append("shots 必须是非空数组")
        return problems

    seen_ids: set[str] = set()
    for i, shot in enumerate(shots):
        tag = f"shots[{i}]"
        sid = shot.get("id")
        if not sid:
            problems.append(f"{tag}: 缺少 id")
        else:
            if sid in seen_ids:
                problems.append(f"{tag}: id 重复 ({sid})")
            seen_ids.add(sid)
            tag = f"shots[{i}]({sid})"

        for key in REQUIRED_SHOT:
            if key not in shot or not str(shot.get(key, "")).strip():
                problems.append(f"{tag}: 缺少 {key}")

        # ★ 动效类型决定这一拍会不会花 AI 视频的钱
        motion_cfg = shot.get("motion") or {}
        motion = motion_cfg.get("type", "still")
        if motion not in MOTION_TYPES:
            problems.append(
                f"{tag}: motion.type={motion!r} 非法，只能是 {MOTION_TYPES}"
            )

        # ai 层必须给动画提示词；still 层不需要（用底图 + 代码动效）
        anim = shot.get("animation") or {}
        if motion == "ai" and not anim.get("prompt") and not anim.get("beats"):
            problems.append(
                f"{tag}: motion.type='ai' 但没有 animation.prompt / animation.beats"
            )
        if motion == "still" and (anim.get("prompt") or anim.get("beats")):
            problems.append(
                f"{tag}: motion.type='still' 却写了 animation —— "
                "still 层不会生成视频，这段提示词是浪费。"
                "确实需要 AI 动效就改成 'ai'。"
            )

        # ★★ 防浪费硬约束：AI 段必须写明「为什么必须是视频」
        #    没有理由 = 没有理由花这笔钱 = 不允许生成。
        #    这条是本 skill 最重要的成本闸门。
        if motion == "ai":
            reason = (motion_cfg.get("ai_reason") or "").strip()
            if not reason:
                problems.append(
                    f"{tag}: motion.type='ai' 但没写 motion.ai_reason —— "
                    "必须说明「这个运动为什么用代码画不出来」，"
                    "否则这拍应该用 still + 代码矢量层（0 积分）。"
                )
            elif len(reason) < 8:
                problems.append(
                    f"{tag}: motion.ai_reason 太短（{reason!r}），"
                    "写清楚运动本身为什么是知识点"
                )
            # beats 链：每段都要有提示词，且时长合法
            beats = anim.get("beats") or []
            for bi, b in enumerate(beats):
                if not (b.get("prompt") or "").strip():
                    problems.append(f"{tag}: animation.beats[{bi}] 缺少 prompt")
                bd = b.get("duration")
                if bd is not None and not (4 <= float(bd) <= 15):
                    problems.append(
                        f"{tag}: animation.beats[{bi}].duration={bd} 超出 4~15 秒"
                    )

        # 矢量层校验
        vectors = (motion_cfg.get("vectors") or [])
        for vi, v in enumerate(vectors):
            kind = v.get("kind")
            if kind not in VECTOR_KINDS:
                problems.append(
                    f"{tag}: motion.vectors[{vi}].kind={kind!r} 非法，"
                    f"只能是 {VECTOR_KINDS}"
                )
            if kind in ("poly", "path"):
                pts = v.get("points") or []
                if len(pts) < (3 if kind == "poly" else 2):
                    problems.append(
                        f"{tag}: motion.vectors[{vi}]（{kind}）的 points 不够"
                    )
            if kind == "curve" and not (v.get("fn") or "").strip():
                problems.append(f"{tag}: motion.vectors[{vi}]（curve）缺少 fn")

        # 提醒：静层完全没动效 = 这拍是死图
        if motion == "still" and not vectors and not (motion_cfg.get("zoomTo")
                                                     or motion_cfg.get("highlight")):
            problems.append(
                f"{tag}: motion.type='still' 但没有任何动效配置"
                "（zoomTo / highlight / vectors 至少要有一个）—— 这会是一张死图"
            )

        dur = shot.get("duration_sec")
        if dur is None:
            problems.append(f"{tag}: 缺少 duration_sec")
        elif not (4 <= float(dur) <= 15):
            problems.append(f"{tag}: duration_sec={dur} 超出 h3 支持的 4~15 秒")

        # 动画时长必须和 duration_sec 对齐，否则画面和声音会错位
        if motion == "ai":
            beats = anim.get("beats") or []
            if beats:
                # 多段接力：各段时长之和应约等于本拍时长
                total_beat = sum(float(b.get("duration") or 0) for b in beats)
                if total_beat and dur is not None:
                    if abs(total_beat - float(dur)) > 1.5:
                        problems.append(
                            f"{tag}: beats 各段时长之和({total_beat:.1f}s) 与 "
                            f"duration_sec({dur}) 相差超过 1.5 秒，会音画错位"
                        )
            else:
                ad = anim.get("duration")
                if ad is None:
                    ad = shot.get("duration_sec")
                if ad is not None and dur is not None and abs(float(ad) - float(dur)) > 0.01:
                    problems.append(
                        f"{tag}: animation.duration({ad}) 与 duration_sec({dur}) 不一致，"
                        "会导致音画错位"
                    )

        if not (shot.get("diagram") or {}).get("prompt") and motion != "ai":
            problems.append(
                f"{tag}: 没有 diagram.prompt（still 层必须有底图）"
            )

    return problems


def load_and_validate(path: str | Path) -> dict:
    """读取并校验；有问题直接抛异常。"""
    plan = load_plan(path)
    problems = validate(plan)
    if problems:
        raise ValueError(
            "plan 校验未通过:\n  - " + "\n  - ".join(problems)
        )
    return plan


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "plan.json"
    try:
        plan = load_and_validate(p)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
    n = len(plan["shots"])
    total = sum(float(s.get("duration_sec", 0)) for s in plan["shots"])
    print(f"[OK] {p}: {n} 拍，预计时长 {total:.1f}s")
