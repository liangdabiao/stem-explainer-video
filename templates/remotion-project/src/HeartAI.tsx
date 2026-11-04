import React from 'react';
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from 'remotion';

const FONT_STACK =
  '"Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", "Helvetica Neue", Arial, sans-serif';

const INK = '#171714';
const BLUE = '#2563eb';
const RED = '#ef4444';
const ROSE = '#9f1239';
const GREEN = '#10b981';

/**
 * ★ 心搏相位（全部来自对 AI 视频的逐帧像素实测，不是猜的）
 *
 * 实测：右心室腔「深蓝面积」在 0~12 秒内以 **2.0 秒**为周期变化，
 *       谷底（心室腔最小＝心室正在收缩）在 t = 0.50, 2.50, 4.50, 6.50, 8.50, 10.50。
 *       → 收缩期 = 周期内 t∈[0.25, 0.75]，舒张期 = 其余。
 *
 * 所以：房室瓣在收缩期关闭、在舒张期打开。
 */
const BEAT_CYCLE = 2.0;

/** 相位 p∈[0,1) → 心室收缩强度 0~1 */
const contraction = (p: number): number => {
  // 收缩期占 p∈[0.125, 0.375]，用平滑凸起表示
  const d = Math.abs(p - 0.25);
  const w = 0.16;
  if (d >= w) return 0;
  const x = d / w;
  return Math.cos((x * Math.PI) / 2) ** 2;
};

/** 相位 p∈[0,1) → 是否处于心室收缩期 */
const isSystole = (p: number): boolean => p >= 0.125 && p <= 0.375;

/** 标注牌 —— 不透明白底 + 彩色描边 + 引线 */
const Tag: React.FC<{
  x: number;
  y: number;
  text: string;
  color: string;
  anchorX: number;
  anchorY: number;
  side: 'left' | 'right';
  appearAt: number;
}> = ({x, y, text, color, anchorX, anchorY, side, appearAt}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(
    frame,
    [appearAt * fps, appearAt * fps + fps * 0.35],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  if (opacity <= 0.01) return null;

  const joint = {x: side === 'left' ? x + 96 : x - 96, y};

  return (
    <>
      <svg
        width="100%"
        height="100%"
        style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}
      >
        <polyline
          points={`${anchorX},${anchorY} ${joint.x},${joint.y} ${x},${y}`}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeOpacity={0.9 * opacity}
          strokeLinejoin="round"
        />
        <circle cx={anchorX} cy={anchorY} r={5.5} fill={color} opacity={opacity} />
      </svg>
      <div
        style={{
          position: 'absolute',
          left: x,
          top: y,
          transform: 'translate(-50%, -50%)',
          opacity,
          fontFamily: FONT_STACK,
          fontSize: 29,
          fontWeight: 800,
          color: INK,
          backgroundColor: 'rgba(255,255,255,0.96)',
          border: `3px solid ${color}`,
          borderRadius: 10,
          padding: '7px 14px',
          whiteSpace: 'nowrap',
          boxShadow: '0 4px 14px rgba(0,0,0,0.2)',
        }}
      >
        {text}
      </div>
    </>
  );
};

/** 顶部术语条 */
const TermBar: React.FC<{term: string; def: string}> = ({term, def}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const y = interpolate(frame, [0, fps * 0.4], [-120, 0], {
    extrapolateRight: 'clamp',
  });
  const fade = interpolate(frame, [0, fps * 0.35], [0, 1], {
    extrapolateRight: 'clamp',
  });
  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        transform: `translateY(${y}px)`,
        opacity: fade,
        fontFamily: FONT_STACK,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 16,
          backgroundColor: 'rgba(255,255,255,0.96)',
          borderBottom: `4px solid ${ROSE}`,
          padding: '13px 24px 15px',
          boxShadow: '0 4px 18px rgba(0,0,0,0.14)',
        }}
      >
        <div style={{fontSize: 37, fontWeight: 800, color: ROSE, whiteSpace: 'nowrap'}}>
          {term}
        </div>
        <div style={{fontSize: 24, fontWeight: 600, color: '#4b5563'}}>{def}</div>
      </div>
    </div>
  );
};

/** 底部字幕 */
const Sub: React.FC<{text: string; from: number; to: number}> = ({text, from, to}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const local = frame - from * fps;
  const dur = (to - from) * fps;
  if (local < 0 || local > dur) return null;
  const opacity = interpolate(local, [0, fps * 0.25], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 40,
        display: 'flex',
        justifyContent: 'center',
        padding: '0 36px',
        opacity,
        fontFamily: FONT_STACK,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          backgroundColor: 'rgba(23,23,20,0.9)',
          borderRadius: 12,
          padding: '12px 20px',
          color: '#FFFFFF',
          fontSize: 32,
          fontWeight: 700,
          lineHeight: 1.32,
          textAlign: 'left',
          maxWidth: 660,
          boxShadow: '0 6px 22px rgba(0,0,0,0.3)',
        }}
      >
        {text}
      </div>
    </div>
  );
};

/**
 * 心跳节律条 —— 顶部一条滚动的心电脉冲 + 当前相位文字。
 *
 * ★ 相位不是编的：脉冲位置由对 AI 视频的实测搏动周期（2.0s）驱动，
 *   收缩期高亮与画面里心室腔实际缩小的时段对齐。
 */
const RhythmBar: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const t = frame / fps;
  const p = (t % BEAT_CYCLE) / BEAT_CYCLE;

  const W = width;
  const H = 58;
  const y0 = 78;

  // 生成一条心电样式的脉冲（每个周期两个峰：心房 + 心室）
  const points: string[] = [];
  const steps = 240;
  for (let i = 0; i <= steps; i++) {
    const q = (i / steps) * 3; // 画 3 个周期
    const ph = (q % 1 + 1) % 1;
    let v = 0;
    // P 波（心房）: 中心 0.10
    v += 0.16 * Math.exp(-(((ph - 0.10) / 0.035) ** 2));
    // QRS 群（心室）: 中心 0.25
    v -= 0.30 * Math.exp(-(((ph - 0.225) / 0.016) ** 2));
    v += 1.00 * Math.exp(-(((ph - 0.25) / 0.014) ** 2));
    v -= 0.28 * Math.exp(-(((ph - 0.278) / 0.018) ** 2));
    // T 波: 中心 0.42
    v += 0.28 * Math.exp(-(((ph - 0.42) / 0.055) ** 2));
    const x = (i / steps) * W;
    const y = y0 + H - (v + 0.35) * H;
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }

  const systole = isSystole(p);
  const phaseText = systole ? '心室收缩期' : '心室舒张期';

  return (
    <svg
      width="100%"
      height={y0 + H + 6}
      style={{position: 'absolute', top: 0, left: 0, pointerEvents: 'none'}}
    >
      <rect x={0} y={y0} width={W} height={H} fill="rgba(255,255,255,0.88)" />
      <line x1={0} y1={y0 + H / 2} x2={W} y2={y0 + H / 2} stroke="#e3e8ef" strokeWidth={1.5} />
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={systole ? RED : ROSE}
        strokeWidth={3}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* 当前时刻游标 */}
      <line
        x1={(p * W) / 1}
        y1={y0}
        x2={(p * W) / 1}
        y2={y0 + H}
        stroke={systole ? RED : GREEN}
        strokeWidth={3.5}
      />
      <rect
        x={W - 176}
        y={y0 + 5}
        width={166}
        height={H - 10}
        rx={8}
        fill={systole ? 'rgba(239,68,68,0.14)' : 'rgba(16,185,129,0.14)'}
        stroke={systole ? RED : GREEN}
        strokeWidth={2}
      />
      <text
        x={W - 93}
        y={y0 + H / 2 + 1}
        fontFamily={FONT_STACK}
        fontSize={23}
        fontWeight={800}
        fill={systole ? RED : '#047857'}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {phaseText}
      </text>
    </svg>
  );
};

/**
 * 瓣膜特写小窗 —— AI 视频做不出的精确状态，用代码画。
 *
 * ★ 为什么必须有这个：实测 AI 生成的瓣膜是**静态奶白结构**，
 *   不会真的开合（帧差热力图上瓣膜区几乎没有变化）。
 *   而「瓣膜是单向阀」正是旁白第三句的核心知识点。
 *   → 用代码画两片叶子的开合，并按实测搏动相位驱动。
 */
const ValveWindow: React.FC<{appearAt: number}> = ({appearAt}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const p = (t % BEAT_CYCLE) / BEAT_CYCLE;

  const opacity = interpolate(
    frame,
    [appearAt * fps, appearAt * fps + fps * 0.4],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  if (opacity <= 0.01) return null;

  // 房室瓣：心室收缩期关闭，舒张期打开
  const open = isSystole(p) ? 0 : 1;
  const color = open > 0.5 ? GREEN : RED;
  const spread = 26 * open;

  // 卡片位置：右下角，避开字幕与图例
  const cw = 236;
  const ch = 152;
  const cx = 720 - cw - 20;
  const cy = 1280 - ch - 214;

  return (
    <div
      style={{
        position: 'absolute',
        left: cx,
        top: cy,
        width: cw,
        height: ch,
        backgroundColor: 'rgba(255,255,255,0.96)',
        border: `3px solid ${color}`,
        borderRadius: 14,
        boxShadow: '0 8px 26px rgba(0,0,0,0.22)',
        opacity,
        fontFamily: FONT_STACK,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 14,
          top: 10,
          fontSize: 24,
          fontWeight: 800,
          color: INK,
        }}
      >
        房室瓣
      </div>
      <div
        style={{
          position: 'absolute',
          right: 14,
          top: 10,
          fontSize: 22,
          fontWeight: 800,
          color,
        }}
      >
        {open > 0.5 ? '开' : '关'}
      </div>

      <svg width={cw} height={ch} style={{position: 'absolute', inset: 0}}>
        {/* 血流通道（竖直向下） */}
        <path
          d={`M ${cw / 2 - 34} 52 L ${cw / 2 - 34} 132`}
          stroke={open > 0.5 ? BLUE : '#c9ced6'}
          strokeWidth={13}
          strokeLinecap="round"
          opacity={0.85}
        />
        <path
          d={`M ${cw / 2 + 34} 52 L ${cw / 2 + 34} 132`}
          stroke={open > 0.5 ? BLUE : '#c9ced6'}
          strokeWidth={13}
          strokeLinecap="round"
          opacity={0.85}
        />
        {/* 通道壁 */}
        <path
          d={`M ${cw / 2 - 46} 48 L ${cw / 2 - 46} 138`}
          stroke="#6b7280"
          strokeWidth={4}
          strokeLinecap="round"
        />
        <path
          d={`M ${cw / 2 + 46} 48 L ${cw / 2 + 46} 138`}
          stroke="#6b7280"
          strokeWidth={4}
          strokeLinecap="round"
        />
        {/* 两片瓣膜叶：
            关闭 = 两片从左右壁伸到中央下方合拢（血液被挡住）
            开启 = 两片退回贴壁，中央通道完全敞开 */}
        <line
          x1={cw / 2 - 40}
          y1={64}
          x2={cw / 2 - 40 + 40 * open}
          y2={64 + 34 + 20 * (1 - open)}
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
        />
        <line
          x1={cw / 2 + 40}
          y1={64}
          x2={cw / 2 + 40 - 40 * open}
          y2={64 + 34 + 20 * (1 - open)}
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
        />
        {/* 血流方向箭头（开启时向下流） */}
        {open > 0.5 ? (
          <g opacity={0.9}>
            <path
              d={`M ${cw / 2} 100 L ${cw / 2} 122`}
              stroke={BLUE}
              strokeWidth={6}
              strokeLinecap="round"
            />
            <path
              d={`M ${cw / 2 - 9} 114 L ${cw / 2} 126 L ${cw / 2 + 9} 114`}
              fill="none"
              stroke={BLUE}
              strokeWidth={6}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </g>
        ) : null}
        {/* 反向箭头（关闭时挡住回流） */}
        {open <= 0.5 ? (
          <g opacity={0.95}>
            <path
              d={`M ${cw / 2} 142 L ${cw / 2} 120`}
              stroke={RED}
              strokeWidth={6}
              strokeLinecap="round"
            />
            <path
              d={`M ${cw / 2 - 9} 128 L ${cw / 2} 116 L ${cw / 2 + 9} 128`}
              fill="none"
              stroke={RED}
              strokeWidth={6}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <text
              x={cw / 2 + 60}
              y={134}
              fontSize={19}
              fontWeight={800}
              fill={RED}
              textAnchor="middle"
            >
              挡住
            </text>
          </g>
        ) : null}
      </svg>
    </div>
  );
};

/** 血流图例 */
const Legend: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [fps * 0.5, fps * 0.9], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  if (opacity <= 0.01) return null;
  const items = [
    {c: BLUE, t: '缺氧血 → 回心房'},
    {c: RED, t: '含氧血 → 泵往全身'},
  ];
  return (
    <div
      style={{
        position: 'absolute',
        left: 20,
        bottom: 200,
        display: 'flex',
        flexDirection: 'column',
        gap: 7,
        opacity,
        fontFamily: FONT_STACK,
        pointerEvents: 'none',
      }}
    >
      {items.map((it) => (
        <div
          key={it.t}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            backgroundColor: 'rgba(255,255,255,0.93)',
            borderRadius: 8,
            padding: '6px 11px',
            fontSize: 20,
            fontWeight: 700,
            color: INK,
            boxShadow: '0 3px 10px rgba(0,0,0,0.14)',
          }}
        >
          <span
            style={{
              width: 15,
              height: 15,
              borderRadius: 4,
              backgroundColor: it.c,
              display: 'inline-block',
            }}
          />
          {it.t}
        </div>
      ))}
    </div>
  );
};

/**
 * 心脏科普样片 —— **apiz 生视频路线**（AI 视频底层 + 代码精确标注层）。
 *
 * 底层：h3 首帧驱动生成的 AI 视频 → 有机的搏动、血液流动、软渲染质感。
 * 叠加层：代码精确绘制 → 解剖标注、节律条、瓣膜开合小窗、字幕、图例。
 *
 * ★ 分工原则（这一版的核心）：
 *   AI 负责「有机运动」—— 软组织形变、血液流动、材质质感；
 *   代码负责「精确状态」—— 瓣膜开合、相位对齐、标注位置、全部文字。
 *   两件事都交给 AI 或都交给代码都会出硬伤。
 */
export const HeartAI: React.FC<{
  videoSrc: string;
  durationSec: number;
  parts: {src: string; text: string; from: number; to: number}[];
}> = ({videoSrc, durationSec, parts}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  // 极轻微推进（≤1.02），只增加纵深，不改变可读的解剖关系
  const scale = interpolate(frame, [0, durationSec * fps], [1.0, 1.02], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{backgroundColor: '#FFFFFF'}}>
      <AbsoluteFill style={{transform: `scale(${scale})`}}>
        <OffthreadVideo
          src={staticFile(videoSrc)}
          muted
          style={{width: '100%', height: '100%', objectFit: 'cover'}}
        />
      </AbsoluteFill>

      <TermBar term="心脏：泵的动力" def="四腔两泵，一次完整心动周期" />

      {/* ★ 心跳节律条：与画面里的真实搏动同步 */}
      <RhythmBar />

      {/* 解剖标注 */}
      <ScaleAnnotations sourceWidth={768} sourceHeight={1376} />

      {/* 血流图例 */}
      <Legend />

      {/* 瓣膜特写（第三句旁白时才出现） */}
      <ValveWindow appearAt={8.9} />

      {/* 字幕（逐句时间轴） */}
      {parts.map((p, i) => (
        <Sub key={i} text={p.text} from={p.from} to={p.to} />
      ))}

      {/* 旁白（edge-tts，免费） */}
      {parts.map((p, i) => (
        <Sequence
          key={i}
          from={Math.round(p.from * fps)}
          durationInFrames={Math.round((p.to - p.from) * fps)}
        >
          <Audio src={staticFile(p.src)} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

/**
 * 标注层：坐标从「视频帧坐标系(768×1376)」映射到画布(720×1280)。
 * 视频用 objectFit: cover，先按 cover 缩放再换算。
 */
const ScaleAnnotations: React.FC<{sourceWidth: number; sourceHeight: number}> = ({
  sourceWidth,
  sourceHeight,
}) => {
  const canvasW = 720;
  const canvasH = 1280;
  const scale = Math.max(canvasW / sourceWidth, canvasH / sourceHeight);
  const drawnW = sourceWidth * scale;
  const drawnH = sourceHeight * scale;
  const offX = (drawnW - canvasW) / 2;
  const offY = (drawnH - canvasH) / 2;

  const P = (x: number, y: number) => ({
    x: x * scale - offX,
    y: y * scale - offY,
  });

  const items: {
    key: string;
    text: string;
    color: string;
    at: {x: number; y: number};
    anchor: {x: number; y: number};
    side: 'left' | 'right';
    appearAt: number;
  }[] = [
    {
      key: 'ra',
      text: '右心房',
      color: BLUE,
      at: {x: 104, y: 268},
      anchor: P(232, 383),
      side: 'left',
      appearAt: 0.6,
    },
    {
      key: 'rv',
      text: '右心室',
      color: BLUE,
      at: {x: 92, y: 800},
      anchor: P(210, 740),
      side: 'left',
      appearAt: 1.7,
    },
    {
      key: 'la',
      text: '左心房',
      color: RED,
      at: {x: 620, y: 268},
      anchor: P(536, 389),
      side: 'right',
      appearAt: 2.8,
    },
    {
      key: 'lv',
      text: '左心室',
      color: RED,
      at: {x: 636, y: 856},
      anchor: P(516, 700),
      side: 'right',
      appearAt: 3.9,
    },
    {
      // 主动脉：移到画面右上空白，不再压在大动脉弓上
      key: 'ao',
      text: '主动脉',
      color: RED,
      at: {x: 592, y: 196},
      anchor: P(432, 152),
      side: 'right',
      appearAt: 5.2,
    },
    {
      // 上腔静脉：上移，避开蓝管本体
      key: 'svc',
      text: '上腔静脉',
      color: BLUE,
      at: {x: 100, y: 212},
      anchor: P(196, 216),
      side: 'left',
      appearAt: 7.0,
    },
    {
      key: 'pv',
      text: '肺静脉',
      color: RED,
      at: {x: 636, y: 520},
      anchor: P(690, 404),
      side: 'right',
      appearAt: 8.2,
    },
    {
      key: 'ivc',
      text: '下腔静脉',
      color: BLUE,
      at: {x: 104, y: 962},
      anchor: P(176, 992),
      side: 'left',
      appearAt: 9.8,
    },
  ];

  return (
    <>
      {items.map((it) => (
        <Tag
          key={it.key}
          x={it.at.x}
          y={it.at.y}
          text={it.text}
          color={it.color}
          anchorX={it.anchor.x}
          anchorY={it.anchor.y}
          side={it.side}
          appearAt={it.appearAt}
        />
      ))}
    </>
  );
};
