import React from 'react';
import {Composition} from 'remotion';
import {StemVideo} from './StemVideo';
import {HeartCycle} from './HeartCycle';
import {HeartAI} from './HeartAI';
import storyboard from './storyboard';

/** 心脏样片「apiz 生视频路线」的时间轴（秒） */
const HEART_AI_PARTS = [
  {src: 'heart-ai/s1.mp3', text: '心脏有四个腔室，四个瓣膜。', from: 0.15, to: 3.10},
  {
    src: 'heart-ai/s2.mp3',
    text: '心房先收缩，把血挤进心室；心室再收缩，把血泵往全身和肺。',
    from: 3.30,
    to: 8.90,
  },
  {
    src: 'heart-ai/s3.mp3',
    text: '瓣膜是单向阀，血只能朝一个方向流。',
    from: 9.10,
    to: 12.45,
  },
];

export const Root: React.FC = () => {
  const totalFrames = storyboard.scenes.reduce(
    (acc, s) => acc + Math.round(s.duration_sec * storyboard.fps),
    0,
  );

  return (
    <>
      <Composition
        id="StemVideo"
        component={StemVideo}
        width={storyboard.width}
        height={storyboard.height}
        fps={storyboard.fps}
        durationInFrames={Math.max(1, totalFrames)}
        defaultProps={{}}
      />
      {/* 复杂科普动效样片：心脏的复杂工作原理（纯代码驱动，0 积分） */}
      <Composition
        id="HeartCycle"
        component={HeartCycle}
        width={720}
        height={1280}
        fps={30}
        durationInFrames={366}
        defaultProps={{}}
      />
      {/* 心脏样片 · apiz 生视频路线：h3 首帧驱动的有机搏动 + 代码精确标注层 */}
      <Composition
        id="HeartAI"
        component={HeartAI}
        width={720}
        height={1280}
        fps={30}
        durationInFrames={375}
        defaultProps={{
          videoSrc: 'heart-ai/heart_main.mp4',
          durationSec: 12.5,
          parts: HEART_AI_PARTS,
        }}
      />
    </>
  );
};
