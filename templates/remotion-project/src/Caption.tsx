import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';

const FONT_STACK =
  '"Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", "Helvetica Neue", Arial, sans-serif';

/**
 * 字幕层 —— 完全确定性渲染（不经过任何 AI 模型）
 * 科普片用深底白字，和白底示意图对比强烈，可读性最好。
 */
export const Caption: React.FC<{text: string; theme?: Theme}> = ({text, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ink = theme?.ink ?? '#171714';

  const opacity = interpolate(frame, [fps * 0.35, fps * 0.7], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const y = interpolate(frame, [fps * 0.35, fps * 0.8], [16, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 64,
        display: 'flex',
        justifyContent: 'center',
        padding: '0 48px',
        opacity,
        transform: `translateY(${y}px)`,
        fontFamily: FONT_STACK,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          backgroundColor: 'rgba(255,255,255,0.94)',
          borderLeft: `6px solid ${theme?.accent ?? '#2563eb'}`,
          borderRadius: 10,
          padding: '14px 22px',
          color: ink,
          fontSize: 38,
          fontWeight: 700,
          lineHeight: 1.3,
          textAlign: 'left',
          maxWidth: 640,
          boxShadow: '0 6px 24px rgba(0,0,0,0.18)',
        }}
      >
        {text}
      </div>
    </div>
  );
};

type Theme = {accent?: string; ink?: string};

/**
 * 术语卡片 —— 科普片的核心信息层。
 * 用「术语 + 释义」的形式在画面上方固定一条，帮助观众抓住概念。
 */
export const TermCard: React.FC<{term: string; def?: string; theme?: Theme}> = ({
  term,
  def,
  theme,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const slide = interpolate(frame, [0, fps * 0.4], [-600, 0], {
    extrapolateRight: 'clamp',
  });
  const fade = interpolate(frame, [0, fps * 0.3], [0, 1], {
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        transform: `translateY(${slide}px)`,
        opacity: fade,
        fontFamily: FONT_STACK,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          backgroundColor: 'rgba(255,255,255,0.96)',
          borderBottom: `4px solid ${theme?.accent ?? '#2563eb'}`,
          padding: '16px 28px 18px',
          boxShadow: '0 4px 18px rgba(0,0,0,0.14)',
        }}
      >
        <div
          style={{
            fontSize: 40,
            fontWeight: 800,
            color: theme?.accent ?? '#2563eb',
            lineHeight: 1.1,
            whiteSpace: 'nowrap',
          }}
        >
          {term}
        </div>
        {def ? (
          <div
            style={{
              fontSize: 26,
              color: '#444c5a',
              lineHeight: 1.35,
              fontWeight: 500,
              borderLeft: '2px solid #d8dde5',
              paddingLeft: 16,
            }}
          >
            {def}
          </div>
        ) : null}
      </div>
    </div>
  );
};

/**
 * 标注层 —— 在画面指定位置叠加文字/引线。
 * 坐标用千分比（0~1000），这样换画幅也不会错位。
 */
export const Annotations: React.FC<{
  items: {text: string; x: number; y: number; color?: string; delay?: number}[];
  width: number;
  height: number;
}> = ({items, width, height}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {items.map((it, i) => {
        const appearAt = (it.delay ?? 0) * fps;
        const opacity = interpolate(
          frame,
          [appearAt, appearAt + fps * 0.3],
          [0, 1],
          {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
        );
        if (opacity <= 0) return null;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: (it.x / 1000) * width,
              top: (it.y / 1000) * height,
              transform: 'translate(-50%, -50%)',
              opacity,
              fontFamily: FONT_STACK,
              fontSize: 30,
              fontWeight: 700,
              color: it.color ?? '#171714',
              backgroundColor: 'rgba(255,255,255,0.92)',
              border: `3px solid ${it.color ?? '#2563eb'}`,
              borderRadius: 8,
              padding: '6px 14px',
              whiteSpace: 'nowrap',
              boxShadow: '0 3px 12px rgba(0,0,0,0.16)',
            }}
          >
            {it.text}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
