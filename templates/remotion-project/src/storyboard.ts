import type {Storyboard} from './types';

/**
 * storyboard.json 是运行时产物（由 scripts/build_storyboard.py 生成，
 * 在 .gitignore 里），所以刚 clone 下来时并不存在。
 *
 * 这里用 try/catch 兜底：文件缺失时回退到 storyboard.example.json，
 * 保证 `npm run check`（tsc）在任何状态下都能过。
 */
let data: Storyboard;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  data = require('../storyboard.json') as Storyboard;
} catch {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  data = require('../storyboard.example.json') as Storyboard;
}

export default data;
