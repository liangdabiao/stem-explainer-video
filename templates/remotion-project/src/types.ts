export type Annotation = {
  text: string;
  /** 相对画面左上角的位置，单位是画幅的千分比，避免写死像素 */
  x: number;
  y: number;
  /** 可选：强调色（默认用主题主色） */
  color?: string;
  /** 可选：出现延迟（秒），用来配合旁白节奏 */
  delay?: number;
};

/**
 * ★ 动效分层 —— 成本控制的核心
 *
 * 一拍的动效 = 底图（严格示意图）+ 动效层（分两种手段）+ 文字层
 *
 *   still   静态底图 + 代码动效（推镜/高亮/标注/矢量）。0 积分
 *   ai      minimax/h3 生成视频。79 积分/段。只在「运动本身是知识点」时用
 *
 * 矢量层（motion.vectors）可以叠加在 still 或 ai 之上：
 *   AI 负责有机运动，矢量层负责精确几何（受力、浸没体积、曲线）。
 *   两者叠加 = 一拍既有真实运动，又有严格正确的物理关系。
 */
export type Motion = {
  type: 'still' | 'ai';
  /** still 层：推镜目标点（千分比）与放大倍数 */
  zoomTo?: {x: number; y: number; scale: number};
  /** still 层：高亮框 */
  highlight?: {
    x: number; y: number; w: number; h: number;
    label?: string; delay?: number; duration?: number; color?: string;
  };
  /**
   * 代码矢量层元素（0 积分）。
   * 坐标系是**画幅千分比**（0~1000），与画幅解耦。
   */
  vectors?: VectorElement[];
  /**
   * AI 多段接力的分段定义。
   * 一拍播放多段 AI 视频，上一段末帧接下一段首帧，
   * 表达「连续过程」（如：注入 → 漂浮 → 下沉）。
   */
  beats?: {duration: number; prompt?: string}[];
};

/** 代码矢量层的元素定义 */
export type VectorElement = {
  kind: 'arrow' | 'poly' | 'path' | 'curve' | 'wave' | 'dot' | 'box' | 'label';
  /** 起点（千分比）。arrow/dot/box/label 用 */
  x1?: number;
  y1?: number;
  /** 终点（千分比）。arrow 用 */
  x2?: number;
  y2?: number;
  /** 宽高（千分比）。box 用 */
  w?: number;
  h?: number;
  /** 顶点列（千分比）。poly/path 用 */
  points?: [number, number][];
  /** 曲线参数方程，x 与 y 均为千分比。curve 用 */
  fn?: string;
  /** 波形振幅（千分比）。wave 用 */
  amplitude?: number;
  /** 波形波长（千分比）。wave 用 */
  wavelength?: number;
  /** 标注文字 */
  label?: string;
  /** 颜色 */
  color?: string;
  /** 出现延迟（秒） */
  delay?: number;
  /** 生长时长（秒），默认 1.0 */
  duration?: number;
  /** 线条粗细（像素），默认 6 */
  weight?: number;
  /** 是否填充。poly 用 */
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

export type Scene = {
  id: string;
  /** 旁白原文 */
  narration: string;
  /** 旁白音频路径（相对 public/） */
  narration_audio: string;
  /** 动画片段路径（相对 public/）—— motion.type='ai' 时使用 */
  motion_video?: string;
  /**
   * AI 多段接力（beats 链）。
   * 一拍里播放多段 AI 视频，上一段的末帧接下一段的首帧，
   * 从而表达「连续过程」而不是一个简单动效。
   * 存在时优先于 motion_video。
   */
  motion_videos?: string[];
  /** 静态底图路径（相对 public/）—— motion.type='still' 时使用 */
  still_image?: string;
  /** 本拍时长（秒） */
  duration_sec: number;
  /** 屏幕字幕 */
  caption: string;
  /** 可选：卡片标题 */
  title?: string;
  /** 可选：术语（教学卡左上角大字） */
  term?: string;
  /** 可选：术语释义 */
  term_def?: string;
  /** 可选：画面标注层（确定性文字） */
  annotations?: Annotation[];
  /** 可选：本拍要点（一句话） */
  takeaway?: string;
  /** 动效配置 */
  motion?: Motion;
  /** 底图原始宽度（像素），静态层做 cover 换算用 */
  image_width?: number;
  /** 底图原始高度（像素） */
  image_height?: number;
};

export type Theme = {
  bg: string;
  ink: string;
  accent: string;
  warn: string;
  muted: string;
};

export type Storyboard = {
  title: string;
  lang?: string;
  style?: string;
  width: number;
  height: number;
  fps: number;
  ratio?: string;
  resolution?: string;
  theme?: Theme;
  scenes: Scene[];
};
