# apiz + MiniMax H3 API 手册（含全部实测踩坑）

本文件记录的是**真实跑通过的调用方式**，不是文档抄写。
每一条「坑」都是实测踩出来的，照抄即可绕过。

---

## 一、apiz CLI 基础

```bash
apiz --help
apiz auth status --json          # 鉴权状态
apiz account balance --json       # 余额
apiz models list --category image --json
apiz models list --category video --json
apiz models info minimax/h3 --json
```

鉴权配置在 `~/.config/apiz/config.toml`，不需要在项目里放 key。

> **Windows 注意**：`apiz` 常在 `~/.local/bin/apiz`，不在默认 PATH。
> 脚本里用 `APIZ_BIN` 环境变量覆盖，或把它加进 PATH。

---

## 二、底图：`openai/gpt-image-2`

```bash
apiz generate "<prompt>" \
  --model "openai/gpt-image-2" \
  --image-size "9:16" \
  --wait --wait-timeout 12m --json
```

### ⚠️ 坑 1：`--image-size` 收的是**比例字符串**，不是旧命名

合法值：`'21:9','16:9','5:4','4:3','3:2','1:1','4:5','3:4','2:3','9:16'`

写 `portrait_16_9` / `landscape_16_9` 这类旧命名 → **HTTP 400**。

### ⚠️ 坑 2：`--aspect-ratio` 对图片模型**不生效**

实测传 `--aspect-ratio 9:16` 仍返回 1024×768（4:3）。
**必须用 `--image-size "9:16"`**，实测返回 608×1088（≈0.559，接近 9:16）。

### 坑 3：返回结构

```json
{
  "task_id": "...", "status": "completed",
  "result": {"images": [{"url": "https://cdn-hk.51sux.com/....png",
                         "width": 608, "height": 1088}]},
  "price": 6
}
```

图片 URL 在 `result.images[0].url`。
`lib_apiz.extract_image_url()` 已做多路径兜底，不用自己找。

### 成本与耗时

- **6 积分/张**（约 0.06 元），实测 **34~38 秒**
- 实测竖版 9:16 中文标签笔画准确、结构正确

### 备选模型

| 模型 id | 备注 |
|---|---|
| `openai/gpt-image-2` | **默认**。中文最准，实测验证过 |
| `openai/gpt-image-2/edit` | 图生图，做尾帧用 |
| `fal-ai/nano-banana-2` | 备选，实测响应偏慢 |
| `apiz/seedream-5.0-pro` | 备选 |
| `service-inference/gemini-nano-banana-2.1` | 备选 |

---

## 二之二、底图：`apiz/gpt-image-2.5-flare`（当前默认）

**比 `openai/gpt-image-2` 更强**：支持 1K/2K/4K 三档尺寸 + low/medium/high/xhigh/max 五档质量，
最多 16 张参考图，还能直接指定 width/height。

### ⚠️ 坑 4（flare 专属）：**不要传 `--image-size`**

flare 系（`gpt-image-2.5-*`）传 `--image-size` 会报 `不支持的参数: image_size`。
比例和尺寸都走 `--params`：

```bash
apiz generate "<prompt>" \
  --model "apiz/gpt-image-2.5-flare" \
  --params '{"size":"2K","quality":"high","aspect_ratio":"9:16"}' \
  --wait --wait-timeout 12m --json
```

| 组合 | 输出尺寸 | 实测积分 | 耗时 |
|---|---|---|---|
| 1K + low | 768×1376 | 11 | ~37s |
| 2K + high | 1136×2048 | **60** | ~40s |

> ★ 积分不是线性的：1K→2K + low→high 让价格翻了 5 倍。
> **底图只是给视频当首帧用，1K + low 完全够**（首帧最终会被视频模型重绘，
> 2K 的细节不会保留下来）。终稿也只有在「底图直接当画面用」时才值得 2K。

### 3D 医学插画风（实测非常适合当 AI 视频首帧）

用 `matte clay-like material, soft studio lighting, gentle ambient occlusion` 描述，
出图是干净的 3D 软渲染质感：

- **优点**：AI 视频驱动时形变自然（不像扁平矢量图一变形就崩）
- **缺点**：AI 会把左右关系画反（解剖图高发），需要人工核对后镜像修正

---

## 三、动画：`minimax/h3`（MiniMax-H3 原生 V2）

### ★ 坑 4（最容易错）：`content` 必须是**数组**

h3 走 OpenAI Chat Completions 风格，不是 apiz 默认的纯 prompt 语义。

传字符串 → `Error: content 必须是非空数组`

### ★ 坑 5：画幅参数名是 `ratio`，不是 `aspect_ratio`

不给具体值 → `Error: ratio 不能为 adaptive`

### ★ 坑 6（最阴的）：首尾帧写在**顶层会被静默忽略**

```json
{"content":[...], "first_frame":"URL", "last_frame":"URL"}   ← 接受但【不生效】
{"content":[...], "first_frame_image_url":"URL"}             ← 同上
```

这两种写法服务端都**不报错**，但首帧渲成纯白（`usage.input_image_count: 0`）。
**你以为在做图生视频，其实在做文生视频。**

正确写法 —— 首帧必须放在 `content` 数组里并用 `role` 标注：

```json
{
  "content": [
    {"type": "text", "text": "<动画描述>"},
    {"type": "image_url", "image_url": {"url": "首帧URL"}, "role": "first_frame"},
    {"type": "image_url", "image_url": {"url": "尾帧URL"}, "role": "last_frame"}
  ],
  "duration": 6,
  "resolution": "480p",
  "ratio": "9:16"
}
```

### ⚠️ 关于 `usage.input_image_count` 的重要更正

**不要用 `usage.input_image_count` 判断首帧是否生效。**

实测服务端返回的 `usage` **不一定包含** `input_image_count` 字段 ——
有时是空对象 `{}`。**字段缺失 ≠ 首帧没被消费**。

（用错这个字段会导致：明明首帧生效了，脚本却抛「首帧没有被消费」并中止，
白白浪费已经生成好的视频。）

可靠的判据有两条：

1. **请求侧**：首帧 URL 确实出现在发出的 `content` 数组里
2. **结果侧**：抽帧看第 0 帧是否等于输入图（首帧保真度实测 100%）

计费上也能看出来：4 秒 480p 纯文生 = 48 积分，
带首帧 = 55 积分（多出的 7 是 Context 积分，图片前 5 张免）。

### ★ 坑 7：`resolution` 大小写不一致

合法值：`['480p', '768P', '1080p', '2K']` —— **`768P` 是大写 P**，写成 `768p` 被拒。

### 参数速查

| 参数 | 值 | 说明 |
|---|---|---|
| `duration` | 4~15（整数） | 秒 |
| `resolution` | `480p` / `768P` / `1080p` / `2K` | 注意 `768P` 大写 |
| `ratio` | `9:16` / `16:9` / `1:1` 等 | 必须给具体值 |

### 返回与成本

```json
{"video_url": "https://cdn-hk.51sux.com/v3-tasks/....mp4",
 "usage": {"input_image_count": 1}, "price": 79}
```

| 分辨率 | 积分/秒 | 6 秒视频 | 12 秒视频 |
|---|---|---|---|
| 480p | 12 | 72 + Context 7 = **79** | 144 + 7 = 151 |
| 768P | 18 | 108 + 7 = 115 | 216 + 7 = **223** |
| 1080p | 28 | 168 + 7 = 175 | 336 + 7 = 343 |
| 2K | 30 | 180 + 7 = 187 | 360 + 7 = 367 |

> 每次 Context 7 积分；图片前 5 张免费，超出后 7 积分/张。
> **实测 480p 6 秒只用了 20 秒出片**，远快于排队型服务。
> 768P 12 秒实测 **70 秒**出片。

### 尺寸实测

- `480p` + `9:16` → **480×832**（不是 720×1280）
- `768P` + `9:16` → **768×1376**（实测）
- 底图 `9:16` → 608×1088

→ 480p 适合做**预览**。终稿用 `768P`。
Remotion 合成时按底图画幅铺满即可，视频片段等比放大。

### ⚠️ 坑 8：AI 视频会**自带音轨**

h3 返回的 mp4 里有一条 aac 音频（模型自己配的环境音/心跳声）。

- 合成时必须 `muted`（Remotion 的 `<OffthreadVideo muted>`）
- 用 edge-tts 的旁白替换它
- 不静音就会出现「AI 环境音 + 中文旁白」两层声音打架

### ⚠️ 坑 9：AI 视频会让构图与首帧**略有差异**

AI 会重新解释首帧，主体位置/大小和原图不完全一致（实测心脏占幅明显变大）。
→ **标注引线的锚点必须用「AI 视频帧」上的坐标，不能用原底图的坐标。**
   做法：抽一帧 → 用颜色分割检测各部件质心 → 写进标注组件。

---

## 四、上传 CDN

```bash
apiz upload ./local.png --folder stem-explainer/diagrams --json
```

返回 `public_url`，是公网可访问的，视频模型可直接读。

---

## 五、配音：`apiz speak`

```bash
apiz speak "要念的文本" \
  --voice female-shaonv \
  --model speech-2.8-hd \
  --speed 1.1 \
  --output-file out.mp3
```

- 模型：`speech-2.8-hd` / `speech-2.8-turbo` / `speech-2.6-hd` / `speech-2.6-turbo`
- 语速：`--speed` 0.5~2.0。科普片建议 **1.05~1.15**
- `--output-file` 直接落盘，不用自己下载
- `apiz voices list` 可查全部音色

---

## 六、成本速查

| 环节 | 单价 | 一集 15 拍（每拍 6 秒） |
|---|---|---|
| 底图 | 6 积分/张 | 90 |
| 动画 480p | 79 积分/段 | 1185 |
| 配音 | ~1 积分/句 | ~15 |
| **合计（480p 预览）** | | **≈1290 积分 ≈ 12.9 元** |
| **合计（768P 终稿）** | | **≈1760 积分 ≈ 17.6 元** |

> 终稿省钱的做法：**先用 480p 跑通全片，再只把 768P 重跑一遍视频层**，
> 底图和配音复用。

---

## 七、失败模式速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `content 必须是非空数组` | content 传了字符串 | 改成数组 |
| `ratio 不能为 adaptive` | 没给 ratio | 给具体比例 |
| `resolution 不合法` | 写了 `768p` | 改成 `768P` |
| `image_size 必须是以下之一` | 用了旧命名 | 改成比例字符串 |
| 传了首帧但首帧是纯白 | 首帧写在顶层被忽略 | 移进 content + `role` |
| HTTP 400 | 参数错误 | 重试没用，直接看 message |
| TLS / 连接中断 | 网络抖动 | 重试即可（脚本已内置） |
| `apiz: command not found` | Windows PATH 问题 | 设 `APIZ_BIN` |
| `FileNotFoundError: WinError 2`（跑 npm） | Windows 上 npm 是 `.cmd`，不能直接 subprocess | 脚本已用 `shell=True` 处理 |
| Remotion 报 `404 .../public/assets/xxx.png` | 素材没同步进 `public/` | 跑 `render_episode.py`（会自动同步） |
| Remotion 报 `404 .../public/assets/narration/xxx.mp3` | storyboard 里的路径写错了 | 路径必须相对 `public/`，即 `audio/narration/xxx.mp3` |

---

## 八、⚠️ 首帧是否生效的正确判据（**别再用 input_image_count**）

服务端返回的 `usage` **不一定包含** `input_image_count` 字段（实测有时是空对象 `{}`）。
**字段缺失 ≠ 首帧没被消费。**

用错这个字段的后果：明明首帧生效了，脚本却抛「首帧没有被消费」并中止，
**白白浪费已经生成好的视频**。

可靠判据：

1. **请求侧**：首帧 URL 确实出现在发出的 `content` 数组里
2. **结果侧**：抽帧看第 0 帧是否等于输入图（首帧保真度实测 100%）
3. **计费侧**：4 秒 480p 纯文生 = 48 积分，带首帧 = 55 积分
   （多出的 7 是 Context 积分，图片前 5 张免）

`lib_apiz.generate_animation()` 已按判据 1 实现。

