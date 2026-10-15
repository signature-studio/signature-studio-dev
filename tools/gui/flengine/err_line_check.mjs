// WIN-37 (#3696): errLine の単体検証 (node のみ・wasm と素材は不要)。node err_line_check.mjs → exit 0 = PASS。
//   各値を実際に throw して catch し、cfi_probe.mjs と同じ経路で整形する。
import { errLine } from './err_line.mjs';
const circ = { a: 1 };
circ.self = circ;
const cases = [
  ['Error (message)', new Error('boom'), 'boom'],
  ['Error (複数行)', new Error('first\nsecond'), 'first'],
  ['Error (message 空)', new Error(''), 'Error'],
  ['message 無し object (marker 形)', { m11_dllmain_done: 1, stack: 'Error\n    at f' }, '{"m11_dllmain_done":1}'],
  ['message 無し object', { m11_dllmain_done: false }, '{"m11_dllmain_done":false}'],
  ['循環参照 object', circ, '{a,self}'],
  ['文字列 (複数行)', 'plain\nline2', 'plain'],
  ['null', null, 'null'],
  ['undefined', undefined, 'undefined'],
];
let fail = 0;
for (const [name, v, want] of cases) {
  let got;
  try { throw v; } catch (e) { got = errLine(e); }
  const ok = got === want && !got.includes('\n') && !got.includes('[object Object]');
  if (!ok) fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}: ${JSON.stringify(got)} (want ${JSON.stringify(want)})`);
}
console.log(fail ? `FAIL ${fail} 件` : 'PASS all');
process.exit(fail ? 1 : 0);
