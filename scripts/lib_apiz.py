"""lib_apiz.py — apiz.ai 平台封装（底图生成 / 视频生成 / CDN 上传 / 配音）

本模块是 stem-explainer-video skill 的唯一外部依赖入口。所有对 apiz 的调用
都经过这里，方便统一处理：
  - CLI 错误输出是单行 `Error: ...`（不是 JSON），必须先看 returncode
  - 任务类接口要 `--wait` 阻塞等待，返回结构里 URL 藏在不同字段
  - 网络偶发 TLS 中断，需要重试

依赖：apiz CLI（默认 PATH 中的 `apiz`，可用环境变量 APIZ_BIN 覆盖），
以及 Python 标准库。不需要 pip install 任何东西。

自检：python scripts/lib_apiz.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# apiz 可执行文件。用 APIZ_BIN 覆盖（Windows 上常见于 ~/.local/bin/apiz）
APIZ_BIN = os.environ.get("APIZ_BIN", "apiz")

# --- 底图（严格示意图）模型 ---
# apiz/gpt-image-2.5-flare 实测：768×1376 竖版、11 积分/张、约 37 秒。
# 优点：支持 1K/2K/4K 三档尺寸 + low/medium/high/xhigh/max 五档质量，
#      最多 16 张参考图，可直接指定 width/height。
DEFAULT_IMAGE_MODEL = "apiz/gpt-image-2.5-flare"

# 底图默认尺寸与质量档位。2K + high 是「结构细节 + 中文标签」的最佳平衡点。
DEFAULT_IMAGE_SIZE = "2K"
DEFAULT_IMAGE_QUALITY = "high"

# --- 视频（动画）模型 ---
# minimax/h3 实测：支持首帧驱动、480p 6 秒 = 79 积分、约 20 秒出片。
DEFAULT_VIDEO_MODEL = "minimax/h3"

# --- 配音模型 ---
# 默认走 edge-tts（本地库，免费无限量，见 tts_edge）。
# apiz speak 保留为降级方案（edge-tts 不可用时用）。
DEFAULT_TTS_MODEL = "speech-2.8-hd"

# edge-tts 中文音色。实测 zh-CN-YunxiNeural / zh-CN-XiaoxiaoNeural 可用。
EDGE_TTS_VOICES = {
    "male": "zh-CN-YunxiNeural",
    "female": "zh-CN-XiaoxiaoNeural",
    "male_pro": "zh-CN-YunjianNeural",
    "female_pro": "zh-CN-XiaoyiNeural",
    "narrator": "zh-CN-YunyangNeural",
    "news": "zh-CN-XiaoxiaoNeural",
}
DEFAULT_TTS_ENGINE = "edge"
DEFAULT_EDGE_VOICE = EDGE_TTS_VOICES["male"]

# h3 支持的分辨率档位。注意 768P 是大写 P，写成 768p 会被服务端拒绝。
H3_RESOLUTIONS = ("480p", "768P", "1080p", "2K")

# h3 支持的时长范围（秒，整数）
H3_MIN_SECONDS = 4
H3_MAX_SECONDS = 15

# 图片模型支持的画幅比例
IMAGE_RATIOS = (
    "21:9", "16:9", "5:4", "4:3", "3:2",
    "1:1", "4:5", "3:4", "2:3", "9:16",
)

DEFAULT_TIMEOUT = 900  # 单次 apiz 调用 15 分钟上限


class ApizError(RuntimeError):
    """apiz 调用失败。"""


# ---------------------------------------------------------------------------
# 底层调用
# ---------------------------------------------------------------------------

def _run_apiz(args: list[str], timeout: int = DEFAULT_TIMEOUT,
              retries: int = 2, retry_delay: float = 8.0) -> dict:
    """跑 apiz 子命令，返回解析后的 JSON dict。

    失败时抛 ApizError。apiz 的错误输出是单行 `Error: apiz: HTTP 400 — ...`，
    直接原样抛出即可读懂。
    """
    cmd = [APIZ_BIN] + args + ["--json"]
    last_err = ""
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            last_err = f"超时（>{timeout}s）"
        else:
            if proc.returncode == 0:
                out = (proc.stdout or "").strip()
                if not out:
                    return {}
                try:
                    return json.loads(out)
                except json.JSONDecodeError:
                    # speak 成功时输出非 JSON（`Saved x.mp3 (1.23s)`）
                    return {"_raw": out}
            last_err = (proc.stderr or proc.stdout or "").strip()
            # HTTP 400 是参数错误，重试没有意义
            if "HTTP 400" in last_err or "HTTP 401" in last_err or "HTTP 403" in last_err:
                break
        if attempt < retries:
            time.sleep(retry_delay)
    raise ApizError(f"apiz 失败: {last_err or '未知错误'}")


def apiz_path() -> str | None:
    """返回 apiz 可执行文件路径；找不到返回 None。"""
    return shutil.which(APIZ_BIN)


def check_ready() -> None:
    """确认 apiz 可用且已鉴权，否则抛 ApizError 给出可执行的修复建议。"""
    if not apiz_path():
        raise ApizError(
            "找不到 apiz 命令。请先安装并登录 apiz CLI，"
            "或用环境变量 APIZ_BIN 指定其绝对路径。"
        )
    try:
        _run_apiz(["auth", "status"], timeout=60, retries=0)
    except ApizError as e:
        raise ApizError(f"apiz 鉴权失败: {e}") from e


def balance() -> tuple[float, float]:
    """返回 (积分, 元)。"""
    data = _run_apiz(["account", "balance"], timeout=60, retries=1)
    return float(data.get("balance", 0)), float(data.get("balance_yuan", 0))


# ---------------------------------------------------------------------------
# URL 提取
# ---------------------------------------------------------------------------

def _first_http_url(obj: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def extract_image_url(obj: dict) -> str:
    """从 generate 返回里取出图片 URL。

    实测 apiz 图片任务的返回结构：
        {"result": {"images": [{"url": "...", "width": 608, "height": 1088}]}}
    但不同模型/通道的返回会飘，所以按多路径兜底。
    """
    url = _first_http_url(
        obj,
        ("image_url", "download_url", "cdn_url", "public_url", "file_url", "url"),
    )
    if url:
        return url

    for container_key in ("result", "output"):
        container = obj.get(container_key)
        if not isinstance(container, dict):
            continue
        url = _first_http_url(container, ("url", "image_url", "image"))
        if url:
            return url
        imgs = container.get("images")
        if isinstance(imgs, list) and imgs:
            first = imgs[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
            if isinstance(first, dict):
                url = _first_http_url(first, ("url", "image_url"))
                if url:
                    return url

    raise ApizError(
        "无法从 apiz 返回里定位图片 URL。完整返回："
        + json.dumps(obj, ensure_ascii=False)[:800]
    )


def extract_video_url(obj: dict) -> str:
    """从 generate 返回里取出视频 URL。

    实测 h3 返回结构：{"video_url": "https://cdn-hk.51sux.com/v3-tasks/...mp4"}
    """
    url = _first_http_url(
        obj, ("video_url", "download_url", "cdn_url", "public_url", "file_url", "url")
    )
    if url:
        return url
    for container_key in ("result", "output"):
        container = obj.get(container_key)
        if isinstance(container, dict):
            url = _first_http_url(
                container, ("video_url", "url", "video")
            )
            if url:
                return url
            vids = container.get("videos")
            if isinstance(vids, list) and vids:
                first = vids[0]
                if isinstance(first, str) and first.startswith("http"):
                    return first
                if isinstance(first, dict):
                    url = _first_http_url(first, ("url", "video_url"))
                    if url:
                        return url
    raise ApizError(
        "无法从 apiz 返回里定位视频 URL。完整返回："
        + json.dumps(obj, ensure_ascii=False)[:800]
    )


def download(url: str, out_path: str | Path, timeout: int = 180) -> Path:
    """下载 URL 到本地文件。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "stem-explainer-video"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out_path.write_bytes(resp.read())
    if out_path.stat().st_size == 0:
        raise ApizError(f"下载到空文件: {out_path}")
    return out_path


def task_info(data: dict) -> dict:
    """从 apiz 返回里抽出任务元信息。

    ★ task_id 必须回传给上层：它是「这笔钱花在哪了」的唯一凭据，
    也是崩溃后用 `apiz tasks get` 取回已付费成片的钥匙。
    """
    return {
        "task_id": data.get("task_id", ""),
        "price": float(data.get("price") or 0),
        "status": data.get("status", ""),
        "model": data.get("model", ""),
    }


# ---------------------------------------------------------------------------
# 1) 底图：严格示意图
# ---------------------------------------------------------------------------

def generate_diagram(
    prompt: str,
    out_path: str | Path,
    model: str = DEFAULT_IMAGE_MODEL,
    ratio: str = "9:16",
    params: dict | None = None,
    wait: bool = True,
) -> tuple[Path, dict]:
    """生成一张严格示意图并下载到 out_path。

    Args:
        prompt: 底图提示词（应包含：类型/主体/布局/风格/配色 hex/标签/约束/背景）
        out_path: 本地输出路径（.png）
        model: 图片模型，默认 apiz/gpt-image-2.5-flare
        ratio: 画幅比例，如 "9:16" / "16:9" / "1:1"
        params: 额外参数（JSON 合并进请求）
        wait: 是否阻塞等待任务完成

    Returns:
        (输出路径, 任务信息 dict{task_id, price, url})

    ★★ 不同图片模型的参数写法不一样（实测踩过）：
      - apiz/gpt-image-2.5-flare：**不要**传 --image-size（会报
        "不支持的参数: image_size"）。比例走 --params 里的 aspect_ratio，
        尺寸走 size 档位（1K/2K/4K）。
        → 9:16 + 1K = 768x1376（11 积分），9:16 + 2K = 1536x2752（23 积分）
      - openai/gpt-image-2：比例走 --image-size（比例字符串）。
        但它**不支持** size/quality 参数 —— 传了会报同样的错。

    所以这里按模型自动选参数写法。
    """
    if ratio not in IMAGE_RATIOS:
        raise ApizError(f"ratio 必须是 {IMAGE_RATIOS} 之一，收到 {ratio!r}")

    merged = dict(params or {})

    # ★ flare 系（gpt-image-2.5-*）：比例与尺寸都走 --params
    if "2.5" in model or "flare" in model.lower():
        merged.setdefault("aspect_ratio", ratio)
        args = ["generate", prompt, "--model", model]
        if merged:
            args += ["--params", json.dumps(merged, ensure_ascii=False)]
    else:
        # 旧模型：比例走 --image-size，不传 size/quality
        merged.pop("size", None)
        merged.pop("quality", None)
        args = ["generate", prompt, "--model", model, "--image-size", ratio]
        if merged:
            args += ["--params", json.dumps(merged, ensure_ascii=False)]

    if wait:
        args += ["--wait", "--wait-timeout", "12m"]

    data = _run_apiz(args)
    out_path = Path(out_path)
    return download(extract_image_url(data), out_path), task_info(data)


def edit_diagram(
    prompt: str,
    image_url: str,
    out_path: str | Path,
    model: str = "openai/gpt-image-2/edit",
    ratio: str = "9:16",
) -> Path:
    """图生图：在已有示意图基础上做局部修改，产出尾帧。

    重要边界：AI 对「细微机械状态变更」不敏感（实测让它把阀门手轮转开，
    手轮根本没动）。所以尾帧只适合做「结构性变化」，
    精确的状态/几何变更请改用代码绘制。
    """
    args = [
        "generate", prompt, "--model", model, "--image-size", ratio,
        "--params", json.dumps(
            {"content": [{"type": "text", "text": prompt}], "image_urls": [image_url]},
            ensure_ascii=False,
        ),
        "--wait", "--wait-timeout", "12m",
    ]
    data = _run_apiz(args)
    return download(extract_image_url(data), out_path)


# ---------------------------------------------------------------------------
# 2) 动画：首帧驱动的图生视频
# ---------------------------------------------------------------------------

def generate_animation(
    prompt: str,
    out_path: str | Path,
    first_frame_url: str | None = None,
    last_frame_url: str | None = None,
    duration: int = 6,
    resolution: str = "480p",
    ratio: str = "9:16",
    model: str = DEFAULT_VIDEO_MODEL,
    extra_images: list[str] | None = None,
) -> tuple[Path, dict]:
    """用首帧（可选尾帧）驱动生成动画片段。

    ★ 三个必须知道的坑（都是实测踩出来的）：

    1. h3 走 OpenAI Chat Completions 风格，`content` 必须是**数组**，
       传字符串会报 "content 必须是非空数组"。
    2. 画幅参数名是 `ratio`（不是 `aspect_ratio`），不给具体值会报
       "ratio 不能为 adaptive"。
    3. **首尾帧必须写在 content 数组里并用 role 标注**：
         {"type":"image_url","image_url":{"url":...},"role":"first_frame"}
       顶层写 `first_frame` / `last_frame` / `first_frame_image_url`
       都会被**静默接受但不生效**（首帧渲成纯白）。

    Returns:
        (输出路径, 任务信息 dict{task_id, price, url})

    Args:
        prompt: 动画提示词（描述「什么在动、什么必须保持不动」）
        first_frame_url: 首帧图公网 URL（严格底图）
        last_frame_url: 尾帧图公网 URL（可选）
        duration: 时长（秒），4~15 的整数
        resolution: 分辨率档位，'480p' / '768P' / '1080p' / '2K'
        ratio: 画幅比例
        extra_images: 其他参考图 URL 列表
    """
    if not (H3_MIN_SECONDS <= duration <= H3_MAX_SECONDS):
        raise ApizError(
            f"duration 必须是 {H3_MIN_SECONDS}~{H3_MAX_SECONDS} 的整数，收到 {duration}"
        )
    if resolution not in H3_RESOLUTIONS:
        raise ApizError(f"resolution 必须是 {H3_RESOLUTIONS} 之一，收到 {resolution!r}")

    content: list[dict] = [{"type": "text", "text": prompt}]
    if first_frame_url:
        content.append({
            "type": "image_url",
            "image_url": {"url": first_frame_url},
            "role": "first_frame",
        })
    if last_frame_url:
        content.append({
            "type": "image_url",
            "image_url": {"url": last_frame_url},
            "role": "last_frame",
        })
    for u in extra_images or []:
        content.append({"type": "image_url", "image_url": {"url": u}})

    payload = {
        "content": content,
        "duration": duration,
        "resolution": resolution,
        "ratio": ratio,
    }
    args = [
        "generate", prompt, "--model", model,
        "--params", json.dumps(payload, ensure_ascii=False),
        "--wait", "--wait-timeout", "12m",
    ]
    data = _run_apiz(args)

    # ★ 关键原则：**服务端已扣费，成片就不能丢**
    # 之前这里会因为校验误报而 raise，把已经付过钱的成片扔掉，
    # 导致重跑又扣一次费。现在只做记录，不阻断流程。
    if first_frame_url:
        sent = json.dumps(payload, ensure_ascii=False)
        if first_frame_url not in sent:
            print("  [WARN] 首帧 URL 没有进入请求体，本次首帧可能未生效")

    out_path = Path(out_path)
    return download(extract_video_url(data), out_path), task_info(data)


# ---------------------------------------------------------------------------
# 3) 上传：把本地图变成公网 URL
# ---------------------------------------------------------------------------

def upload(local_path: str | Path, folder: str = "stem-explainer") -> str:
    """上传本地文件到 apiz CDN，返回公网 URL。"""
    data = _run_apiz(["upload", str(local_path), "--folder", folder], timeout=300)
    url = _first_http_url(data, ("public_url", "cdn_url", "file_url", "url"))
    if not url:
        raise ApizError(
            "无法从 upload 返回取 URL: " + json.dumps(data, ensure_ascii=False)[:400]
        )
    return url


# ---------------------------------------------------------------------------
# 4) 配音
# ---------------------------------------------------------------------------

def speak(
    text: str,
    out_path: str | Path,
    voice: str = "female-shaonv",
    model: str = DEFAULT_TTS_MODEL,
    speed: float = 1.0,
) -> Path:
    """用 apiz speak 生成配音 mp3（降级方案）。

    apiz speak 内置 --output-file 直接落盘，不用自己下载。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "speak", text,
        "--voice", voice,
        "--model", model,
        "--speed", str(speed),
        "--output-file", str(out_path),
    ]
    _run_apiz(args, timeout=180)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise ApizError(f"apiz speak 声称成功但文件不存在或为空: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# 4b) 配音：edge-tts（默认）
# ---------------------------------------------------------------------------

def edge_tts_available() -> bool:
    """检查 edge-tts 是否可用。"""
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def speak_edge(
    text: str,
    out_path: str | Path,
    voice: str = DEFAULT_EDGE_VOICE,
    rate: str = "+0%",
) -> Path:
    """用 edge-tts 生成配音 mp3（默认方案，免费、无限量）。

    edge-tts 是本地 Python 库，直接调微软 Edge 的在线 TTS 服务。
    实测可用（zh-CN-YunxiNeural / zh-CN-XiaoxiaoNeural 等）。

    Args:
        text: 要念的文本
        out_path: 输出 mp3 路径
        voice: 音色名（完整 voice id，如 zh-CN-YunxiNeural）
        rate: 语速，edge-tts 格式（"+10%" 表示快 10%，"-10%" 表示慢）

    注意：edge-tts 的语速用「百分比字符串」，不是 apiz speak 的倍率浮点数。
    """
    try:
        import asyncio

        import edge_tts
    except ImportError as e:
        raise ApizError(
            "edge-tts 不可用，请先安装：pip install edge-tts\n"
            "（若必须用云端 TTS，可设 meta.tts_engine='apiz'）"
        ) from e

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        comm = edge_tts.Communicate(text, voice, rate=rate)
        await comm.save(str(out_path))

    try:
        asyncio.run(_run())
    except Exception as e:
        raise ApizError(f"edge-tts 合成失败: {e}") from e

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise ApizError(f"edge-tts 声称成功但文件不存在或为空: {out_path}")
    return out_path


def synth_voice(
    text: str,
    out_path: str | Path,
    engine: str = DEFAULT_TTS_ENGINE,
    voice: str | None = None,
    model: str = DEFAULT_TTS_MODEL,
    speed: float = 1.0,
) -> Path:
    """按 engine 分发到对应的 TTS 实现。

    engine="edge"（默认）→ edge-tts，免费无限量
    engine="apiz"          → apiz speak，消耗积分
    engine="auto"         → 有 edge-tts 就用，没有才退回 apiz
    """
    engine = (engine or DEFAULT_TTS_ENGINE).lower()

    if engine == "apiz":
        return speak(text, out_path, voice=voice or "female-shaonv",
                     model=model, speed=speed)

    if engine in ("edge", "auto"):
        if edge_tts_available():
            v = voice or DEFAULT_EDGE_VOICE
            # 允许用 "male"/"female" 这类简称
            v = EDGE_TTS_VOICES.get(v, v)
            # apiz 的倍率换算成 edge-tts 的百分比
            pct = int(round((speed - 1.0) * 100))
            rate = f"{pct:+d}%"
            return speak_edge(text, out_path, voice=v, rate=rate)
        if engine == "edge":
            raise ApizError(
                "edge-tts 未安装。请执行 pip install edge-tts，"
                "或把 meta.tts_engine 改成 'apiz' 使用云端 TTS。"
            )
        # auto 且 edge-tts 不可用 → 退回 apiz
        print("[提示] edge-tts 不可用，自动退回 apiz speak（消耗积分）")
        return speak(text, out_path, voice=voice or "female-shaonv",
                     model=model, speed=speed)

    raise ApizError(f"未知 TTS 引擎: {engine!r}（可选 edge / apiz / auto）")


def list_voices() -> list[dict]:
    """列出可用音色。"""
    data = _run_apiz(["voices", "list"], timeout=60, retries=1)
    items = data if isinstance(data, list) else (data.get("data") or data.get("voices") or [])
    return items


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loc = apiz_path()
    print(f"apiz 位置: {loc or '未找到（请确认在 PATH 或设置 APIZ_BIN）'}")
    if not loc:
        raise SystemExit(1)
    try:
        check_ready()
        print("鉴权: OK")
    except ApizError as e:
        print(f"鉴权失败: {e}")
        raise SystemExit(1)
    try:
        pts, yuan = balance()
        print(f"余额: {pts:.2f} 积分 ({yuan:.2f} 元)")
    except ApizError as e:
        print(f"余额查询失败: {e}")
    print(f"默认底图模型: {DEFAULT_IMAGE_MODEL}")
    print(f"默认视频模型: {DEFAULT_VIDEO_MODEL}  分辨率档位: {H3_RESOLUTIONS}")
