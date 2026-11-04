import React from 'react';
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Series,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from 'remotion';
import {Caption, TermCard, Annotations} from './Caption';
import {StillMotion} from './StillMotion';
import {VectorLayer} from './VectorLayer';
import type {Scene as SceneData} from './types';

export const Scene: React.FC<{
  scene: SceneData;
  fps: number;
  width: number;
  height: number;
  theme?: {bg: string; ink: string; accent: string; warn: string; muted: string};
}> = ({scene, fps, width, height, theme}) => {
  const frame = useCurrentFrame();
  const {fps: cfgFps} = useVideoConfig();

  const motionType = scene.motion?.type ?? 'still';

  // ── AI 视频层：轻微推进，让画面不死板（幅度很小，不影响看结构）──
  const aiScale = interpolate(frame, [0, cfgFps * 6], [1.0, 1.03], {
    extrapolateRight: 'clamp',
  });

  // ── AI 多段接力：每段按其在场景中的累计时长切分 ──
  // 段时长由 plan 里的 duration 决定（storyboard 会写进 motion.beats）
  const beats = scene.motion?.beats;
  const segs: {src: string; dur: number}[] = [];
  if (beats && beats.length > 0 && scene.motion_videos) {
    for (let i = 0; i < beats.length && i < scene.motion_videos.length; i++) {
      segs.push({
        src: scene.motion_videos[i],
        dur: Math.max(0.1, beats[i]?.duration ?? beats[0]?.duration ?? 4),
      });
    }
  }

  return (
    <AbsoluteFill style={{backgroundColor: theme?.bg ?? '#FFFFFF'}}>
      {motionType === 'ai' && segs.length > 0 ? (
        // 多段接力
        <AbsoluteFill style={{transform: `scale(${aiScale})`}}>
          <Series>
            {segs.map((s, i) => (
              <Series.Sequence
                key={i}
                durationInFrames={Math.round(s.dur * cfgFps)}
                layout="none"
              >
                <OffthreadVideo
                  src={staticFile(s.src)}
                  muted
                  style={{width: '100%', height: '100%', objectFit: 'cover'}}
                />
              </Series.Sequence>
            ))}
          </Series>
        </AbsoluteFill>
      ) : motionType === 'ai' && scene.motion_video ? (
        <AbsoluteFill style={{transform: `scale(${aiScale})`}}>
          <OffthreadVideo
            src={staticFile(scene.motion_video)}
            muted
            style={{width: '100%', height: '100%', objectFit: 'cover'}}
          />
        </AbsoluteFill>
      ) : (
        <StillMotion
          src={scene.still_image ?? ''}
          duration={scene.duration_sec}
          zoomTo={scene.motion?.zoomTo}
          highlight={scene.motion?.highlight}
          theme={theme}
          width={width}
          height={height}
          imageWidth={scene.image_width}
          imageHeight={scene.image_height}
        />
      )}

      {/* ★ 代码矢量层：精确几何表达（受力、浸没体积、曲线）。0 积分 */}
      {scene.motion?.vectors && scene.motion.vectors.length > 0 ? (
        <VectorLayer
          elements={scene.motion.vectors}
          width={width}
          height={height}
        />
      ) : null}

      <Audio src={staticFile(scene.narration_audio)} />

      {scene.annotations && scene.annotations.length > 0 ? (
        <Annotations
          items={scene.annotations}
          width={width}
          height={height}
        />
      ) : null}

      {scene.term ? (
        <TermCard term={scene.term} def={scene.term_def} theme={theme} />
      ) : null}

      <Caption text={scene.caption} theme={theme} />
    </AbsoluteFill>
  );
};
