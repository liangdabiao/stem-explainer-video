import React from 'react';
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
  staticFile,
} from 'remotion';

const FONT_STACK =
  '"Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", "Helvetica Neue", Arial, sans-serif';

type Theme = {accent?: string; ink?: string; warn?: string};

type Highlight = {
  x: number; y: number; w: number; h: number;
  label?: string; delay?: number; duration?: number; color?: string;
};

/**
 * 静止层（still）动效引擎 —— 0 积分成本。
 *
 * 科普片里大多数镜头不需要 AI 生成视频：观众看的是「结构」，
 * 而不是「运动」。这时候用代码做动效反而更好：
 *   - 高亮框精确指向要讲的部件（AI 做不到这么准）
 *   - 推镜把观众视线带到该看的地方
 *   - 标注按旁白节奏依次出现
 *
 * ★ 坐标系约定：
 *   高亮框的 x/y/w/h 用**千分比**，相对于**底图本身**（不是裁切后的画面）。
 *   底图以 objectFit:'cover' 铺满画面，比例不同时会有裁切，
 *   所以这里按 cover 的缩放关系换算，保证框精确落在底图元素上。
 */
export const StillMotion: React.FC<{
  /** 底图（相对 public/） */
  src: string;
  /** 本拍总时长（秒） */
  duration: number;
  /** 推镜终点，x/y 用千分比（相对底图） */
  zoomTo?: {x: number; y: number; scale: number};
  /** 高亮框：位置用千分比（相对底图） */
  highlight?: Highlight;
  theme?: Theme;
  width: number;
  height: number;
  /** 底图原始像素尺寸，用于 cover 换算 */
  imageWidth?: number;
  imageHeight?: number;
}> = ({
  src, duration, zoomTo, highlight, theme, width, height,
  imageWidth, imageHeight,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const total = Math.max(1, Math.round(duration * fps));

  // ---- contain 映射：底图如何映射到画面 ----
  // objectFit:'contain' 时，缩放系数 = min(W/iw, H/ih)，整图可见，
  // 上下或左右留白。所以千分比坐标可以线性映射，无需裁切补偿。
  //
  // ★ inset：AI 常把结构/标签画到画面边缘（实测左右 12% 区域有 8~15% 墨水），
  //   再叠字幕就会切到标签。所以在画面内再留一圈安全边距，
  //   让底图整体内缩，边缘内容就不会被切。
  const INSET = 0.045; // 每边 4.5%
  const iw = imageWidth || width;
  const ih = imageHeight || height;
  const availW = width * (1 - INSET * 2);
  const availH = height * (1 - INSET * 2);
  const fitScale = Math.min(availW / iw, availH / ih);
  // 底图居中后左上角在画面中的位置
  const offsetX = (width - iw * fitScale) / 2;
  const offsetY = (height - ih * fitScale) / 2;
  // 底图坐标(千分比) → 画面像素
  const toScreenX = (px: number) => (px / 1000) * iw * fitScale + offsetX;
  const toScreenY = (py: number) => (py / 1000) * ih * fitScale + offsetY;
  const scaleLen = (v: number, axis: 'x' | 'y') =>
    (v / 1000) * (axis === 'x' ? iw : ih) * fitScale;

  // ---- 推镜 ----
  // ★ 缩放上限：底图里的中文标签通常贴着画面边缘，
  //   放大太多会把它们裁掉。所以这里限制最大缩放，
  //   并且优先保住标签所在的外围区域。
  const MAX_SCALE = 1.12;
  const startScale = 1.0;
  const endScale = Math.min(zoomTo?.scale ?? 1.06, MAX_SCALE);
  const rawZoom = interpolate(frame, [0, total * 0.7], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const zoom = startScale + (endScale - startScale) * Easing.out(Easing.cubic)(rawZoom);

  // 目标点保持在原位（画面中心不动）
  const tx = toScreenX(zoomTo?.x ?? 500);
  const ty = toScreenY(zoomTo?.y ?? 500);
  const panX = zoomTo ? ((width / 2) - tx) * (zoom - 1) / zoom : 0;
  const panY = zoomTo ? ((height / 2) - ty) * (zoom - 1) / zoom : 0;

  // ---- 高亮框：跟随推镜一起变换 ----
  let hl = null;
  if (highlight) {
    const appearAt = (highlight.delay ?? 0) * fps;
    const holdEnd = total - (highlight.duration ?? 0) * fps;
    const opacity = interpolate(
      frame,
      [appearAt, appearAt + fps * 0.4,
       Math.max(appearAt + fps * 0.5, holdEnd - fps * 0.3), holdEnd],
      [0, 1, 1, 0],
      {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
    );
    const pulse = 1 + Math.sin(frame / 7) * 0.015;
    const color = highlight.color ?? theme?.accent ?? '#2563eb';

    const bw = scaleLen(highlight.w, 'x');
    const bh = scaleLen(highlight.h, 'y');
    const bx = toScreenX(highlight.x) - bw / 2;
    const by = toScreenY(highlight.y) - bh / 2;

    // 标签放在框外（下方），避免遮挡被框住的部件
    const labelBelow = by + bh + 14 < height - 120;
    const labelStyle: React.CSSProperties = {
      position: 'absolute',
      left: '50%',
      transform: 'translateX(-50%)',
      backgroundColor: color,
      color: '#FFFFFF',
      fontFamily: FONT_STACK,
      fontSize: 26,
      fontWeight: 700,
      padding: '5px 14px',
      borderRadius: 8,
      whiteSpace: 'nowrap',
      boxShadow: '0 3px 10px rgba(0,0,0,0.25)',
      ...(labelBelow
        ? {top: '100%', marginTop: 10}
        : {bottom: '100%', marginBottom: 10}),
    };

    hl = (
      <div
        style={{
          position: 'absolute',
          left: bx,
          top: by,
          width: bw,
          height: bh,
          border: `5px solid ${color}`,
          borderRadius: 12,
          opacity,
          transform: `scale(${pulse})`,
          transformOrigin: 'center',
          boxShadow: `0 0 0 4px rgba(255,255,255,0.85), 0 0 22px ${color}66`,
          pointerEvents: 'none',
        }}
      >
        {highlight.label ? <div style={labelStyle}>{highlight.label}</div> : null}
      </div>
    );
  }

  return (
    <AbsoluteFill style={{backgroundColor: '#FFFFFF'}}>
      <AbsoluteFill
        style={{
          transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
          transformOrigin: 'center center',
        }}
      >
        {/* 底图按 contain + 内缩放置，保证边缘的结构与标签不被裁 */}
        <div
          style={{
            position: 'absolute',
            left: offsetX,
            top: offsetY,
            width: iw * fitScale,
            height: ih * fitScale,
          }}
        >
          <img
            src={staticFile(src)}
            style={{width: '100%', height: '100%', objectFit: 'fill'}}
          />
        </div>
        {/* 高亮框放在图片层内，跟着一起缩放平移 */}
        {hl}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
