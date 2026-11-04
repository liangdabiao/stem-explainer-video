import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {Scene} from './Scene';
import storyboard from './storyboard';

export const StemVideo: React.FC = () => {
  let cursor = 0;
  const theme = storyboard.theme;

  return (
    <AbsoluteFill style={{backgroundColor: theme?.bg ?? '#FFFFFF'}}>
      {storyboard.scenes.map((s) => {
        const frames = Math.round(s.duration_sec * storyboard.fps);
        const from = cursor;
        cursor += frames;
        return (
          <Sequence key={s.id} from={from} durationInFrames={frames}>
            <Scene
              scene={s}
              fps={storyboard.fps}
              width={storyboard.width}
              height={storyboard.height}
              theme={theme}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
