import React from 'react';
import {
  AbsoluteFill,
  Audio,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  staticFile,
} from 'remotion';

/**
 * HeartCycle —— 心脏复杂工作原理（纯代码驱动的复杂科普动效，0 积分）
 *
 * 这一支不是「静态图 + 高亮」，而是把整颗心脏（四腔、瓣膜、血流、心电）
 * 全部用 SVG + useCurrentFrame 在代码里表达出来。它展示的是本 skill 的核心能力：
 *   —— 凡是「代码能精确表达的连续运动」就用代码做（免费、可控、永远正确），
 *      AI 视频只留给代码确实表达不了的有机运动。
 *
 * 表达的知识点：
 *   1) 心脏分四个腔室（右/左 心房、右/左 心室）
 *   2) 心动周期分期：心房收缩 → 心室收缩 → 舒张期
 *   3) 瓣膜像单向阀：房室瓣（三尖瓣/二尖瓣）与半月瓣（肺动脉瓣/主动脉瓣）
 *      随周期开合，保证血液单向流动
 *   4) 红蓝双电路：蓝=缺氧血（体→右心→肺），红=含氧血（肺→左心→全身）
 *   5) 同步的心电（ECG）节律 + 实时相位标签 + 实时瓣膜状态面板
 *
 * ★ 版面分区（720×1280 设计坐标，自上而下，互不重叠）：
 *   29..67   标题
 *   84..148  相位标签框
 *   195..510 体外大血管
 *   290..800 心脏主体（房室沟 y=510）
 *   825..905 心电条
 *   950..1008 瓣膜状态面板
 *   1018..1076 血色图例
 *   1104..   底部字幕（HTML 层）
 */

const FONT =
  '"Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif';

const BASE_W = 720;
const BASE_H = 1280;

// 颜色
const BLUE = '#2563eb'; // 缺氧血
const RED = '#ef4444'; // 含氧血
const GREEN = '#22c55e'; // 瓣膜开放
const INK = '#171714';
const WALL = '#9aa3af'; // 腔壁灰
const WALL_STRONG = '#5b6675';
const ECG_BLUE = '#0ea5e9';

const CYCLE = 4.0; // 一个心动周期秒数

// ====================== 相位函数 ======================
function gauss(p: number, center: number, sigma: number): number {
  const d = p - center;
  return Math.exp(-(d * d) / (2 * sigma * sigma));
}
// 心房收缩峰值 p≈0.06；心室收缩峰值 p≈0.30
const atrialContraction = (p: number) => gauss(p, 0.06, 0.035);
const ventricularContraction = (p: number) => gauss(p, 0.3, 0.06);

// 平滑台阶：区间 [a,b] 内为 1，边界 0.02 过渡
function band(p: number, a: number, b: number): number {
  const t1 = interpolate(p, [a - 0.02, a + 0.02], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const t2 = interpolate(p, [b - 0.02, b + 0.02], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return Math.max(0, Math.min(1, Math.min(t1, t2)));
}

// 房室瓣：心房收缩期 + 舒张期开；心室射血期关
const avOpen = (p: number) => Math.max(band(p, 0.0, 0.16), band(p, 0.42, 1.0));
// 半月瓣：仅射血期开
const slOpen = (p: number) => band(p, 0.18, 0.42);

// ECG 单周期形状（正值向上）
function ecg(p: number): number {
  return (
    0.16 * gauss(p, 0.05, 0.02) -
    0.18 * gauss(p, 0.175, 0.006) +
    1.0 * gauss(p, 0.2, 0.006) -
    0.3 * gauss(p, 0.225, 0.008) +
    0.28 * gauss(p, 0.36, 0.045)
  );
}

// ====================== 几何 ======================
const GEO = {
  body: {x: 90, y: 290, w: 540, h: 510, rx: 58},
  septum: 360,
  groove: 510,
  RA: {x: 108, y: 305, w: 240, h: 195, cx: 228, cy: 402},
  LA: {x: 372, y: 305, w: 240, h: 195, cx: 492, cy: 402},
  RV: {x: 108, y: 520, w: 240, h: 270, cx: 228, cy: 655},
  LV: {x: 372, y: 520, w: 240, h: 270, cx: 492, cy: 655},
  tricuspid: {x: 228, y: 510},
  mitral: {x: 492, y: 510},
  pulmonary: {x: 150, y: 510},
  aortic: {x: 570, y: 510},
};

// 静态血管管壁
const VESSELS = {
  cava: 'M160 195 L160 310',
  pa: 'M150 510 C150 430 118 395 108 310 L80 295',
  aorta: 'M570 510 C570 430 602 395 612 310 L618 275',
  pv: 'M545 200 L520 310',
};

// 血流路径（亮滴沿此流动）
const FLOWS = {
  venousReturn: 'M160 195 L160 310 L160 402 L228 402',
  raToRv: 'M228 440 L228 510 L228 655',
  rvToPa: 'M228 655 C228 580 150 550 150 510 C150 430 118 395 108 310 L80 295',
  pulmVein: 'M545 200 L520 310 L520 402 L492 402',
  laToLv: 'M492 440 L492 510 L492 655',
  lvToAorta: 'M492 655 C492 580 570 550 570 510 C570 430 602 395 612 310 L618 275',
};

// ====================== 子组件 ======================
const Chamber: React.FC<{
  x: number; y: number; w: number; h: number;
  cx: number; cy: number; scale: number;
  /** 心室腔的独立缩放（收缩时腔变小得快 → 心肌壁相对变厚） */
  innerScale?: number;
  fill: string; label: string; thick?: boolean;
}> = ({x, y, w, h, cx, cy, scale, innerScale, fill, label, thick}) => (
  <g transform={`translate(${cx} ${cy}) scale(${scale}) translate(${-cx} ${-cy})`}>
    <rect
      x={x} y={y} width={w} height={h} rx={26}
      fill={fill} fillOpacity={thick ? 0.4 : 0.22}
      stroke={thick ? WALL_STRONG : WALL} strokeWidth={thick ? 11 : 7}
    />
    {thick ? (
      <g
        transform={`translate(${cx} ${cy}) scale(${innerScale ?? scale}) translate(${-cx} ${-cy})`}
      >
        {/* 内腔（浅＝腔内血）；腔外较深的环带＝心肌壁，收缩时变宽 → 壁相对变厚 */}
        <rect
          x={x + 15} y={y + 15} width={w - 30} height={h - 30} rx={17}
          fill={fill} fillOpacity={0.12} stroke={WALL_STRONG} strokeWidth={5} strokeOpacity={0.6}
        />
      </g>
    ) : null}
    <text
      x={cx} y={cy} fontFamily={FONT} fontSize={32} fontWeight={800}
      fill={INK} textAnchor="middle" dominantBaseline="central"
    >
      {label}
    </text>
  </g>
);

/**
 * 瓣膜：两片叶片 + 阀环（环内是编号，对应下方状态面板）。
 * open: 0 = 关（红，两叶在中心合拢成屏障）→ 1 = 开（绿，两叶贴壁让开通道）。
 *
 * ★ 这里**不用**在图上写名称：四个瓣膜名在下方面板里列，
 *   图上只留编号，避免「肺动脉瓣」与「三尖瓣」这类长名牌互相挤压。
 */
const Valve: React.FC<{x: number; y: number; open: number; num: string}> = ({
  x, y, open, num,
}) => {
  const color = open > 0.5 ? GREEN : RED;
  const op = 0.45 + 0.55 * Math.abs(open - 0.5) * 2;
  const t = open;
  return (
    <g>
      {/* 左叶：关闭时伸到中心形成屏障，开启时缩回贴壁让开通道 */}
      <line
        x1={x - 17} y1={y + 3} x2={x - 17 * t} y2={y + 3 - 10 * t}
        stroke={color} strokeWidth={7} strokeLinecap="round" strokeOpacity={op}
      />
      {/* 右叶 */}
      <line
        x1={x + 17} y1={y + 3} x2={x + 17 * t} y2={y + 3 - 10 * t}
        stroke={color} strokeWidth={7} strokeLinecap="round" strokeOpacity={op}
      />
      {/* 阀环 + 编号 */}
      <circle cx={x} cy={y} r={16} fill="#ffffff" stroke={color} strokeWidth={3.5} />
      <text
        x={x} y={y} fontFamily={FONT} fontSize={19} fontWeight={800}
        fill={color} textAnchor="middle" dominantBaseline="central"
      >
        {num}
      </text>
    </g>
  );
};

const FlowPath: React.FC<{d: string; color: string; active: number; t: number}> = ({
  d, color, active, t,
}) => {
  const offset = -((t * 320) % 1000);
  return (
    <g>
      <path d={d} fill="none" stroke={color} strokeWidth={9} strokeOpacity={0.2} strokeLinecap="round" />
      <path
        d={d} fill="none" stroke={color} strokeWidth={12} strokeOpacity={active}
        strokeLinecap="round" strokeDasharray="26 174" strokeDashoffset={offset}
        pathLength={1000}
        style={{filter: `drop-shadow(0 0 5px ${color})`}}
      />
    </g>
  );
};

const Vessel: React.FC<{d: string; color: string}> = ({d, color}) => (
  <path
    d={d} fill="none" stroke={color} strokeWidth={26}
    strokeOpacity={0.16} strokeLinecap="round" strokeLinejoin="round"
  />
);

const EcgStrip: React.FC<{t: number}> = ({t}) => {
  const x0 = 40, x1 = 680, y0 = 825, h = 80;
  const cycles = 3;
  const cycW = (x1 - x0) / cycles;
  const n = 100;
  const pts: string[] = [];
  for (let c = 0; c <= cycles; c++) {
    for (let i = 0; i < n; i++) {
      const ph = i / n;
      const x = x0 + c * cycW + ph * cycW;
      const y = y0 + h * 0.55 - ecg(ph) * h * 0.36;
      pts.push(`${x.toFixed(1)} ${y.toFixed(1)}`);
    }
  }
  const scroll = (t * 90) % cycW;
  return (
    <g>
      <defs>
        <clipPath id="ecg-clip">
          <rect x={x0} y={y0} width={x1 - x0} height={h} rx={10} />
        </clipPath>
      </defs>
      <text x={x0} y={920} fontFamily={FONT} fontSize={20} fontWeight={800} fill={ECG_BLUE}>
        心电 ECG
      </text>
      <rect
        x={x0} y={y0} width={x1 - x0} height={h} rx={10}
        fill="rgba(255,255,255,0.72)" stroke="#d8dde5" strokeWidth={2}
      />
      <g clipPath="url(#ecg-clip)">
        <g transform={`translate(${-scroll} 0)`}>
          <polyline
            points={pts.join(' ')} fill="none" stroke={ECG_BLUE}
            strokeWidth={3} strokeLinecap="round" strokeLinejoin="round"
          />
        </g>
      </g>
    </g>
  );
};

const PhaseLabel: React.FC<{p: number}> = ({p}) => {
  let txt = '舒张期 · 充盈';
  let col = '#6b7280';
  if (p < 0.16) {
    txt = '心房收缩 · 把血挤进心室';
    col = BLUE;
  } else if (p < 0.42) {
    txt = '心室收缩 · 把血泵出心脏';
    col = RED;
  }
  return (
    <g>
      <rect
        x={40} y={84} width={640} height={64} rx={14}
        fill="#ffffff" fillOpacity={0.95} stroke={col} strokeWidth={4}
        style={{filter: 'drop-shadow(0 4px 14px rgba(0,0,0,0.14))'}}
      />
      <circle cx={78} cy={116} r={13} fill={col} />
      <text
        x={106} y={116} fontFamily={FONT} fontSize={31} fontWeight={800}
        fill={INK} dominantBaseline="central"
      >
        {txt}
      </text>
    </g>
  );
};

/** 瓣膜状态面板：四个瓣膜的实时开/关，编号与图上的阀环对应 */
const ValvePanel: React.FC<{av: number; sl: number}> = ({av, sl}) => {
  const items: {num: string; name: string; open: number}[] = [
    {num: '1', name: '三尖瓣', open: av},
    {num: '2', name: '二尖瓣', open: av},
    {num: '3', name: '肺动脉瓣', open: sl},
    {num: '4', name: '主动脉瓣', open: sl},
  ];
  // 每项：编号徽章 → 名称 → 状态字（按名称实际字数排，避免压字）
  const badgeX = [124, 248, 372, 515];
  const nameX = [140, 264, 388, 531];
  const stateX = [205, 329, 472, 615];
  return (
    <g>
      <rect
        x={40} y={950} width={640} height={58} rx={14}
        fill="rgba(255,255,255,0.92)" stroke="#d8dde5" strokeWidth={2}
      />
      <text
        x={58} y={979} fontFamily={FONT} fontSize={19} fontWeight={800}
        fill={INK} dominantBaseline="central"
      >
        瓣膜
      </text>
      {items.map((it, i) => {
        const isOpen = it.open > 0.5;
        const col = isOpen ? GREEN : RED;
        return (
          <g key={it.num}>
            <circle cx={badgeX[i]} cy={979} r={11} fill="#ffffff" stroke={col} strokeWidth={2.5} />
            <text
              x={badgeX[i]} y={979} fontFamily={FONT} fontSize={14} fontWeight={800}
              fill={col} textAnchor="middle" dominantBaseline="central"
            >
              {it.num}
            </text>
            <text
              x={nameX[i]} y={979} fontFamily={FONT} fontSize={19} fontWeight={700}
              fill={INK} dominantBaseline="central"
            >
              {it.name}
            </text>
            <text
              x={stateX[i]} y={979} fontFamily={FONT} fontSize={19} fontWeight={800}
              fill={col} dominantBaseline="central"
            >
              {isOpen ? '开' : '关'}
            </text>
          </g>
        );
      })}
    </g>
  );
};

/** 血色图例：说明红蓝各代表什么 */
const Legend: React.FC = () => (
  <g>
    <rect x={40} y={1018} width={640} height={58} rx={14} fill="rgba(255,255,255,0.92)" stroke="#d8dde5" strokeWidth={2} />
    <line x1={62} y1={1047} x2={94} y2={1047} stroke={BLUE} strokeWidth={11} strokeLinecap="round" />
    <text x={104} y={1047} fontFamily={FONT} fontSize={22} fontWeight={700} fill={INK} dominantBaseline="central">
      缺氧血 体循环 右心→肺
    </text>
    <line x1={392} y1={1047} x2={424} y2={1047} stroke={RED} strokeWidth={11} strokeLinecap="round" />
    <text x={434} y={1047} fontFamily={FONT} fontSize={22} fontWeight={700} fill={INK} dominantBaseline="central">
      含氧血 肺循环 左心→全身
    </text>
  </g>
);

// ====================== 主组件 ======================
export const HeartCycle: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const p = (t / CYCLE) % 1;

  const scaleAtria = 1 - 0.16 * atrialContraction(p);
  // 心室收缩：心肌壁几乎不变（外框轻微缩），但腔明显变小 → 壁相对变厚
  const scaleVentWall = 1 - 0.05 * ventricularContraction(p);
  const scaleVentCavity = 1 - 0.3 * ventricularContraction(p);
  const bodyPulse = 1 + 0.012 * Math.sin((t / CYCLE) * Math.PI * 2);

  const av = avOpen(p);
  const sl = slOpen(p);

  const filling = Math.max(band(p, 0.0, 0.16), band(p, 0.42, 1.0)); // 充盈 / 心房收缩期
  const ejection = band(p, 0.18, 0.42); // 射血期

  const bcx = GEO.body.x + GEO.body.w / 2;
  const bcy = GEO.body.y + GEO.body.h / 2;

  return (
    <AbsoluteFill style={{backgroundColor: '#f4f7fb'}}>
      <Audio src={staticFile('heart/narration.mp3')} />

      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${BASE_W} ${BASE_H}`}
        preserveAspectRatio="xMidYMid meet"
        style={{position: 'absolute', inset: 0}}
      >
        <text
          x={360} y={48} fontFamily={FONT} fontSize={38} fontWeight={800}
          fill={INK} textAnchor="middle" dominantBaseline="central"
        >
          心脏的工作原理
        </text>

        <PhaseLabel p={p} />
        <EcgStrip t={t} />

        {/* 心脏主体 */}
        <g transform={`translate(${bcx} ${bcy}) scale(${bodyPulse}) translate(${-bcx} ${-bcy})`}>
          <rect
            x={GEO.body.x} y={GEO.body.y} width={GEO.body.w} height={GEO.body.h}
            rx={GEO.body.rx} fill="#ffffff" stroke={WALL} strokeWidth={6}
          />
          <line
            x1={GEO.body.x + 20} y1={GEO.groove} x2={GEO.body.x + GEO.body.w - 20} y2={GEO.groove}
            stroke={WALL} strokeWidth={5} strokeDasharray="10 8"
          />
          <line
            x1={GEO.septum} y1={GEO.body.y + 20} x2={GEO.septum} y2={GEO.body.y + GEO.body.h - 20}
            stroke={WALL} strokeWidth={5} strokeDasharray="10 8"
          />

          <Vessel d={VESSELS.cava} color={BLUE} />
          <Vessel d={VESSELS.pa} color={BLUE} />
          <Vessel d={VESSELS.aorta} color={RED} />
          <Vessel d={VESSELS.pv} color={RED} />

          <FlowPath d={FLOWS.venousReturn} color={BLUE} active={filling} t={t} />
          <FlowPath d={FLOWS.raToRv} color={BLUE} active={filling} t={t} />
          <FlowPath d={FLOWS.rvToPa} color={BLUE} active={ejection} t={t} />
          <FlowPath d={FLOWS.pulmVein} color={RED} active={filling} t={t} />
          <FlowPath d={FLOWS.laToLv} color={RED} active={filling} t={t} />
          <FlowPath d={FLOWS.lvToAorta} color={RED} active={ejection} t={t} />

          <Chamber {...GEO.RA} scale={scaleAtria} fill={BLUE} label="右心房" />
          <Chamber {...GEO.LA} scale={scaleAtria} fill={RED} label="左心房" />
          <Chamber {...GEO.RV} scale={scaleVentWall} innerScale={scaleVentCavity} fill={BLUE} label="右心室" thick />
          <Chamber {...GEO.LV} scale={scaleVentWall} innerScale={scaleVentCavity} fill={RED} label="左心室" thick />

          <Valve x={GEO.tricuspid.x} y={GEO.tricuspid.y} open={av} num="1" />
          <Valve x={GEO.mitral.x} y={GEO.mitral.y} open={av} num="2" />
          <Valve x={GEO.pulmonary.x} y={GEO.pulmonary.y} open={sl} num="3" />
          <Valve x={GEO.aortic.x} y={GEO.aortic.y} open={sl} num="4" />
        </g>

        {/* 体外大血管标签 */}
        <text x={160} y={176} fontFamily={FONT} fontSize={22} fontWeight={700} fill={BLUE} textAnchor="middle">
          静脉血回心
        </text>
        <text x={66} y={258} fontFamily={FONT} fontSize={22} fontWeight={700} fill={BLUE} textAnchor="middle">
          肺
        </text>
        <text x={600} y={180} fontFamily={FONT} fontSize={22} fontWeight={700} fill={RED} textAnchor="middle">
          肺静脉
        </text>
        <text x={624} y={242} fontFamily={FONT} fontSize={22} fontWeight={700} fill={RED} textAnchor="middle">
          全身
        </text>

        <ValvePanel av={av} sl={sl} />
        <Legend />
      </svg>

      {/* 底部字幕（HTML 层，与旁白同步） */}
      <div
        style={{
          position: 'absolute', left: 0, right: 0, bottom: 34,
          display: 'flex', justifyContent: 'center', padding: '0 40px',
          fontFamily: FONT, pointerEvents: 'none',
        }}
      >
        <div
          style={{
            backgroundColor: 'rgba(23,23,20,0.88)', borderRadius: 12,
            padding: '12px 20px', color: '#fff', fontSize: 28,
            fontWeight: 600, lineHeight: 1.35, textAlign: 'center', maxWidth: 660,
          }}
        >
          心脏分四个腔室：心房收缩把血挤进心室，心室收缩把血泵往全身和肺。蓝是缺氧血，红是含氧血，瓣膜像单向阀，循环往复。
        </div>
      </div>
    </AbsoluteFill>
  );
};
