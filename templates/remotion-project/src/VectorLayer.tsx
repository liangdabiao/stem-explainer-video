import React from 'react';
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from 'remotion';

/**
 * VectorLayer —— 代码矢量层（0 积分的「精确表达」）
 *
 * ★ 为什么需要这一层：
 *   AI 视频擅长「有机运动」（流体、燃烧、粒子、晃动），
 *   但**不擅长精确几何**：受力矢量必须严格竖直、浸没体积必须准确、
 *   曲线必须符合方程。AI 画出来必然歪，而代码画出来永远精确。
 *
 *   所以一拍的完整动效 = AI 段链（有机制的运动）
 *                    + VectorLayer（精确的物理关系）
 *
 * 支持的矢量元素（plan.json 的 motion.vectors 配置）：
 *   arrow     箭头（受力方向、流向）—— 从起点生长到终点
 *   poly      多边形（浸没体积 V排）—— 按顺序描出并可填充
 *   path      折线/曲线路径 —— 逐段描出
 *   curve     函数曲线 —— 按参数方程绘制（x 为千分比）
 *   wave      波形 —— 正弦/水波/声波
 *   dot       标注圆点 + 文字
 *   box       虚线框 + 文字
 *   label     纯文字（不依赖图形）
 *
 * 所有坐标用**千分比**（0~1000），与画幅解耦，改画幅不用重算。
 */

export type VectorElement = {
  kind: 'arrow' | 'poly' | 'path' | 'curve' | 'wave' | 'dot' | 'box' | 'label';
  /** 起点（千分比）。arrow/dot 用 */
  x1?: number;
  y1?: number;
  /** 终点（千分比）。arrow 用 */
  x2?: number;
  y2?: number;
  /** 宽高（千分比），kind='box' 时用 */
  w?: number;
  h?: number;
  /** 顶点列（千分比），kind='poly' / 'path' 时用 */
  points?: [number, number][];
  /** 曲线参数方程，kind='curve' 时用；x 为千分比，y 为千分比 */
  fn?: string;
  /** 波形参数，kind='wave' 时用 */
  amplitude?: number;
  wavelength?: number;
  /** 标注文字 */
  label?: string;
  /** 颜色 */
  color?: string;
  /** 出现延迟（秒），用来配合旁白节奏 */
  delay?: number;
  /** 生长时长（秒），默认 1.0 */
  duration?: number;
  /** 线条粗细（画面像素），默认 6 */
  weight?: number;
  /** 是否填充（poly 用），默认 false */
  fill?: boolean;
  /** 填充透明度 0~1 */
  opacity?: number;
  /** 文字相对图形的偏移（千分比） */
  dx?: number;
  dy?: number;
  /** 文字大小（像素），默认 28 */
  fontSize?: number;
  /** 是否虚线 */
  dashed?: boolean;
};

const FONT = '"Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif';

const px = (v: number, w: number) => (v / 1000) * w;
const py = (v: number, h: number) => (v / 1000) * h;

export const VectorLayer: React.FC<{
  elements?: VectorElement[];
  width: number;
  height: number;
  /** 整体不透明度（用于淡入淡出） */
  opacity?: number;
}> = ({elements, width, height, opacity = 1}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  if (!elements || elements.length === 0) return null;

  return (
    <AbsoluteFill style={{pointerEvents: 'none', opacity}}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        style={{position: 'absolute', inset: 0}}
      >
        {elements.map((el, i) => (
          <VectorShape
            key={i}
            el={el}
            frame={frame}
            fps={fps}
            width={width}
            height={height}
          />
        ))}
      </svg>
    </AbsoluteFill>
  );
};

const VectorShape: React.FC<{
  el: VectorElement;
  frame: number;
  fps: number;
  width: number;
  height: number;
}> = ({el, frame, fps, width, height}) => {
  const color = el.color ?? '#ef4444';
  const delay = el.delay ?? 0;
  const dur = el.duration ?? 1.0;
  const weight = el.weight ?? 6;

  // 生长进度 0 → 1
  const t = interpolate(
    frame,
    [delay * fps, (delay + dur) * fps],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );
  const grow = Easing.out(Easing.cubic)(t);
  // 淡入
  const appear = interpolate(t, [0, 0.12], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  // 淡出（可选）
  const fadeOut = interpolate(t, [0.88, 1], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const alpha = appear * fadeOut;

  if (alpha <= 0.01) return null;

  // ── 箭头（受力矢量）──
  if (el.kind === 'arrow') {
    const x1 = px(el.x1 ?? 0, width);
    const y1 = py(el.y1 ?? 0, height);
    const x2 = px(el.x2 ?? 0, width);
    const y2 = py(el.y2 ?? 0, height);
    const ex = x1 + (x2 - x1) * grow;
    const ey = y1 + (y2 - y1) * grow;

    const ang = Math.atan2(y2 - y1, x2 - x1);
    const headLen = 26;
    const headWidth = 13;
    const hx = x2 - headLen * Math.cos(ang);
    const hy = y2 - headLen * Math.sin(ang);
    const p1 = `${hx + headWidth * Math.sin(ang)},${hy - headWidth * Math.cos(ang)}`;
    const p2 = `${hx - headWidth * Math.sin(ang)},${hy + headWidth * Math.cos(ang)}`;

    return (
      <g opacity={alpha}>
        <line
          x1={x1} y1={y1} x2={ex} y2={ey}
          stroke={color} strokeWidth={weight} strokeLinecap="round"
        />
        {grow > 0.85 ? (
          <polygon
            points={`${x2},${y2} ${p1} ${p2}`}
            fill={color}
          />
        ) : null}
        {el.label ? (
          <VectorText
            el={el}
            x={x2 + (el.dx ?? 0) * width / 1000}
            y={y2 + (el.dy ?? 0) * height / 1000}
            color={color}
            alpha={alpha}
            anchor="middle"
          />
        ) : null}
      </g>
    );
  }

  // ── 多边形（浸没体积 V排）──
  if (el.kind === 'poly') {
    const pts = el.points ?? [];
    if (pts.length < 3) return null;
    const n = Math.max(2, Math.ceil(pts.length * grow));
    const shown = pts.slice(0, n);
    const poly = shown
      .map((p) => `${px(p[0], width)},${py(p[1], height)}`)
      .join(' ');
    const closed = grow > 0.98 ? ' ' + `${px(pts[0][0], width)},${py(pts[0][1], height)}` : '';
    return (
      <g opacity={alpha}>
        {el.fill ? (
          <polygon
            points={(poly + closed).trim()}
            fill={color}
            fillOpacity={(el.opacity ?? 0.22)}
          />
        ) : null}
        <polyline
          points={(poly + closed).trim()}
          fill="none"
          stroke={color}
          strokeWidth={weight}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={el.dashed ? '14 10' : undefined}
        />
        {el.label ? (
          <VectorText
            el={el}
            x={px(pts[0][0], width) + (el.dx ?? 0) * width / 1000}
            y={py(pts[0][1], height) + (el.dy ?? 0) * height / 1000}
            color={color}
            alpha={alpha}
            anchor="start"
          />
        ) : null}
      </g>
    );
  }

  // ── 折线路径 ──
  if (el.kind === 'path') {
    const pts = el.points ?? [];
    if (pts.length < 2) return null;
    const n = Math.max(2, Math.ceil(pts.length * grow));
    const shown = pts.slice(0, n);
    const d = shown
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(p[0], width)} ${py(p[1], height)}`)
      .join(' ');
    return (
      <g opacity={alpha}>
        <path
          d={d}
          fill="none"
          stroke={color}
          strokeWidth={weight}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={el.dashed ? '14 10' : undefined}
        />
        {el.label ? (
          <VectorText
            el={el}
            x={px(pts[pts.length - 1][0], width) + (el.dx ?? 0) * width / 1000}
            y={py(pts[pts.length - 1][1], height) + (el.dy ?? 0) * height / 1000}
            color={color}
            alpha={alpha}
            anchor="start"
          />
        ) : null}
      </g>
    );
  }

  // ── 函数曲线 ──
  if (el.kind === 'curve') {
    const fn = el.fn;
    if (!fn) return null;
    let f: (x: number) => number;
    try {
      // eslint-disable-next-line no-new-func
      f = new Function('x', `return (${fn});`) as (x: number) => number;
    } catch {
      return null;
    }
    const steps = 80;
    const pts: string[] = [];
    const limit = Math.max(1, Math.round(steps * grow));
    for (let i = 0; i <= limit; i++) {
      const xRatio = (i / steps) * 1000;
      let yRatio: number;
      try {
        yRatio = f(xRatio);
      } catch {
        continue;
      }
      if (!Number.isFinite(yRatio)) continue;
      pts.push(`${px(xRatio, width)} ${py(yRatio, height)}`);
    }
    if (pts.length < 2) return null;
    return (
      <g opacity={alpha}>
        <polyline
          points={pts.join(' ')}
          fill="none"
          stroke={color}
          strokeWidth={weight}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {el.label ? (
          <VectorText
            el={el}
            x={width / 2}
            y={height * 0.9}
            color={color}
            alpha={alpha}
            anchor="middle"
          />
        ) : null}
      </g>
    );
  }

  // ── 波形 ──
  if (el.kind === 'wave') {
    const amp = (el.amplitude ?? 30) / 1000 * height;
    const wl = (el.wavelength ?? 200) / 1000 * width;
    const nWaves = 3;
    const steps = 120;
    const pts: string[] = [];
    for (let i = 0; i <= steps * grow; i++) {
      const x = (i / steps) * width;
      const phase = (x / wl) * Math.PI * 2;
      // 振幅包络：中间大两端小，像真实的驻波
      const env = Math.sin((i / steps) * Math.PI);
      const y = height * 0.5 + Math.sin(phase) * amp * env;
      pts.push(`${x} ${y}`);
    }
    if (pts.length < 2) return null;
    return (
      <g opacity={alpha}>
        <polyline
          points={pts.join(' ')}
          fill="none"
          stroke={color}
          strokeWidth={weight}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {el.label ? (
          <VectorText
            el={el}
            x={width / 2}
            y={height * 0.5 - amp - 12}
            color={color}
            alpha={alpha}
            anchor="middle"
          />
        ) : null}
      </g>
    );
  }

  // ── 标注圆点 ──
  if (el.kind === 'dot') {
    const cx = px(el.x1 ?? 0, width);
    const cy = py(el.y1 ?? 0, height);
    const r = 10 + 6 * grow;
    return (
      <g opacity={alpha}>
        <circle cx={cx} cy={cy} r={r} fill={color} />
        <circle cx={cx} cy={cy} r={r + 6 * grow} fill="none" stroke={color} strokeWidth={3} opacity={0.5} />
        {el.label ? (
          <VectorText
            el={el}
            x={cx + (el.dx ?? 0) * width / 1000}
            y={cy + (el.dy ?? 0) * height / 1000}
            color={color}
            alpha={alpha}
            anchor="start"
          />
        ) : null}
      </g>
    );
  }

  // ── 虚线框 ──
  if (el.kind === 'box') {
    const x = px(el.x1 ?? 0, width);
    const y = py(el.y1 ?? 0, height);
    const w = px(el.w ?? 0, width);
    const h = px(el.h ?? 0, height);
    return (
      <g opacity={alpha}>
        <rect
          x={x} y={y} width={w * grow} height={h}
          fill="none"
          stroke={color}
          strokeWidth={weight}
          strokeDasharray="14 10"
          rx={8}
        />
        {el.label ? (
          <VectorText
            el={el}
            x={x + (el.dx ?? 0) * width / 1000}
            y={y + (el.dy ?? 0) * height / 1000}
            color={color}
            alpha={alpha}
            anchor="start"
          />
        ) : null}
      </g>
    );
  }

  // ── 纯文字 ──
  if (el.kind === 'label') {
    return (
      <VectorText
        el={el}
        x={px(el.x1 ?? 0, width)}
        y={py(el.y1 ?? 0, height)}
        color={color}
        alpha={alpha}
        anchor="middle"
      />
    );
  }

  return null;
};

const VectorText: React.FC<{
  el: VectorElement;
  x: number;
  y: number;
  color: string;
  alpha: number;
  anchor: 'start' | 'middle' | 'end';
}> = ({el, x, y, color, alpha, anchor}) => {
  const size = el.fontSize ?? 28;
  return (
    <text
      x={x}
      y={y}
      fontFamily={FONT}
      fontSize={size}
      fontWeight={500}
      fill={color}
      textAnchor={anchor}
      dominantBaseline="central"
      opacity={alpha}
      stroke="#FFFFFF"
      strokeWidth={size * 0.18}
      paintOrder="stroke"
    >
      {el.label}
    </text>
  );
};
