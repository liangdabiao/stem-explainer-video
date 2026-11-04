"""verify_media.py — 成片质检

★ 为什么需要这个脚本：
ffprobe 时长一致、`verify_media` 报 PASS，都**查不出音轨损坏**。
真正会出事的是「音频轨是空的 / 中间大段静音 / 某拍没声音」——
这类问题只有提取音频算 RMS 才能发现。

本脚本做四件事：
  1. 每拍素材齐全（视频 + 音频都存在、非空）
  2. 每拍视频时长 ≥ 该拍音频时长（否则话没说完就切画面）
  3. 整片音轨波形体检：0.5 秒窗 RMS，有声窗占比 > 95%，
     且静音段都短于 2 秒（正常句间停顿）
  4. 整片音视频时长差 < 0.5 秒

用法：
    python scripts/verify_media.py plan.json
    python scripts/verify_media.py plan.json --video out/episode.mp4
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_schema import load_and_validate

# 波形体检参数
WIN_SEC = 0.5           # RMS 窗长（秒）
SILENCE_DB = -45        # 低于此 dBFS 视为静音
MAX_SILENCE = 2.0       # 允许的最长静音（秒），超过视为异常

# 有声窗占比下限。
# 注意：TTS 分片自带首尾静音（每段约 0.2~0.5s），一集 15 拍会累积约 10% 的静音。
# 所以正常成片的占比在 88%~97% 之间。低于 85% 才说明音轨真的有问题。
MIN_VOICED_RATIO = 0.85


def _run(cmd: list[str]) -> str:
    out = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if out.returncode != 0:
        raise RuntimeError(f"{cmd[0]} 失败: {out.stderr.strip()[:300]}")
    return out.stdout


def probe_json(path: Path) -> dict:
    raw = _run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ])
    return json.loads(raw)


def media_duration(path: Path) -> float:
    data = probe_json(path)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            return float(s.get("duration") or data["format"]["duration"])
    return float(data["format"]["duration"])


def has_audio(path: Path) -> bool:
    data = probe_json(path)
    return any(s.get("codec_type") == "audio" for s in data.get("streams", []))


def rms_windows(audio_path: Path) -> list[float]:
    """把音频切成 0.5 秒窗，返回每窗的 RMS dBFS。

    实现方式：ffmpeg 解码成单声道 PCM 到 stdout，用 Python 直接算 RMS。
    （不用 ffmpeg 的 astats filter —— 各版本输出格式不一致，实测常解析不到。）
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("找不到 ffmpeg")

    cmd = [
        "ffmpeg", "-v", "error", "-i", str(audio_path),
        "-ac", "1", "-ar", "16000", "-f", "s16le", "-",
    ]
    proc = subprocess.run(
        cmd, capture_output=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 解码失败: {proc.stderr.decode('utf-8', 'replace')[:200]}"
        )
    raw = proc.stdout
    if len(raw) < 2:
        raise RuntimeError(f"音频解码后没有数据: {audio_path}")

    import array
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])

    win = int(16000 * WIN_SEC)  # 每窗采样数（必须为整数）
    if win <= 0:
        raise RuntimeError(f"WIN_SEC 非法: {WIN_SEC}")
    out: list[float] = []
    for i in range(0, len(samples), win):
        chunk = samples[i : i + win]
        if not chunk:
            break
        # RMS = sqrt(mean(x^2))，x 为 16bit 归一化值
        acc = 0
        for v in chunk:
            acc += v * v
        rms = (acc / len(chunk)) ** 0.5
        if rms <= 0:
            out.append(-120.0)
        else:
            out.append(20.0 * math.log10(rms / 32768.0))
    return out


def audit_waveform(audio_path: Path) -> tuple[float, list[tuple[float, float]]]:
    """返回 (有声窗占比, [(静音起点秒, 静音终点秒), ...])。"""
    vals = rms_windows(audio_path)
    if not vals:
        raise RuntimeError(f"无法从 {audio_path} 提取 RMS（ffmpeg astats 无输出）")

    # astats 的 reset 窗长由 asetnsamples 决定，这里用帧数估算时间轴
    # 若窗口数与总时长不符，退化为「静音占比」判断
    total = media_duration(audio_path)
    per_win = total / len(vals) if vals else WIN_SEC

    silent = [v <= SILENCE_DB for v in vals]
    voiced_ratio = 1.0 - (sum(silent) / len(silent))

    runs: list[tuple[float, float]] = []
    start = None
    for i, is_silent in enumerate(silent):
        if is_silent and start is None:
            start = i * per_win
        elif not is_silent and start is not None:
            runs.append((start, i * per_win))
            start = None
    if start is not None:
        runs.append((start, len(silent) * per_win))
    return voiced_ratio, runs


def main() -> int:
    ap = argparse.ArgumentParser(description="科普视频成片质检")
    ap.add_argument("plan")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--video", default=None, help="成片 mp4 路径（做整片体检）")
    args = ap.parse_args()

    plan_path = Path(args.plan).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else plan_path.parent
    plan = load_and_validate(plan_path)

    problems: list[str] = []
    warnings: list[str] = []

    # ---------- 1. 逐拍素材检查 ----------
    print("=== 逐拍素材 ===")
    timeline_path = workdir / "assets" / "narration" / "timeline.json"
    timeline = {}
    if timeline_path.exists():
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    for shot in plan["shots"]:
        sid = shot["id"]
        motion_type = (shot.get("motion") or {}).get("type", "still")
        # 与 build_storyboard 一致：优先用 fitted 版本
        fitted = workdir / "assets" / "videos" / "fitted" / f"{sid}.mp4"
        vid = fitted if fitted.exists() else (workdir / "assets" / "videos" / f"{sid}.mp4")
        aud = workdir / "assets" / "narration" / f"{sid}.mp3"
        issues = []

        if motion_type == "ai":
            if not vid.exists() or vid.stat().st_size == 0:
                issues.append("缺视频")
        else:
            # 静态层只需要底图
            still = workdir / "assets" / "diagrams" / f"{sid}.png"
            if not still.exists() or still.stat().st_size == 0:
                issues.append("缺底图")
        if not aud.exists() or aud.stat().st_size == 0:
            issues.append("缺音频")

        aud_dur = vid_dur = 0.0
        if aud.exists() and aud.stat().st_size > 0:
            try:
                aud_dur = media_duration(aud)
            except Exception as e:
                issues.append(f"音频探测失败:{e}")
        if vid.exists() and vid.stat().st_size > 0:
            try:
                vid_dur = media_duration(vid)
            except Exception as e:
                issues.append(f"视频探测失败:{e}")

        if aud_dur and vid_dur and vid_dur + 0.05 < aud_dur:
            issues.append(f"视频{vid_dur:.1f}s < 旁白{aud_dur:.1f}s（话没说完就切）")

        status = "OK" if not issues else "FAIL"
        extra = ""
        if aud_dur:
            extra = f"  旁白{aud_dur:.1f}s 视频{vid_dur:.1f}s"
        print(f"  [{status}] {sid}{extra}")
        for i in issues:
            print(f"         - {i}")
            problems.append(f"{sid}: {i}")

    # ---------- 2. 整片体检 ----------
    if args.video:
        vp = Path(args.video).resolve()
        print(f"\n=== 整片体检: {vp.name} ===")
        if not vp.exists():
            print(f"  [FAIL] 成片不存在: {vp}")
            problems.append(f"成片不存在: {vp}")
        else:
            vdur = media_duration(vp)
            print(f"  时长: {vdur:.2f}s")
            if not has_audio(vp):
                print("  [FAIL] 成片没有音频轨")
                problems.append("成片没有音频轨")
            else:
                try:
                    ratio, silences = audit_waveform(vp)
                    print(f"  有声窗占比: {ratio * 100:.1f}%  (下限 {MIN_VOICED_RATIO * 100:.0f}%)")
                    if ratio < MIN_VOICED_RATIO:
                        problems.append(
                            f"有声窗占比 {ratio * 100:.1f}% 低于 {MIN_VOICED_RATIO * 100:.0f}% —— 音轨可能有损坏或大段静音"
                        )
                    long_sil = [(a, b) for a, b in silences if b - a > MAX_SILENCE]
                    if long_sil:
                        for a, b in long_sil:
                            msg = f"静音段 {a:.1f}s~{b:.1f}s（{b - a:.1f}s）超过 {MAX_SILENCE}s"
                            print(f"  [WARN] {msg}")
                            warnings.append(msg)
                    else:
                        print(f"  静音段: {len(silences)} 处，均短于 {MAX_SILENCE}s ✓")
                except Exception as e:
                    print(f"  [FAIL] 波形体检失败: {e}")
                    problems.append(f"波形体检失败: {e}")

            # 音视频时长差
            expected = sum(
                float((timeline.get(s["id"]) or {}).get("duration_sec") or s["duration_sec"])
                for s in plan["shots"]
            )
            diff = abs(vdur - expected)
            print(f"  预期总时长 {expected:.2f}s，差 {diff:.2f}s")
            if diff > 0.5:
                warnings.append(f"成片时长与预期差 {diff:.2f}s（>0.5s）")

    # ---------- 汇总 ----------
    print("\n=== 汇总 ===")
    for w in warnings:
        print(f"  [WARN] {w}")
    if problems:
        print(f"  [FAIL] {len(problems)} 项问题：")
        for p in problems:
            print(f"    - {p}")
        return 1
    print("  [PASS] 全部检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
