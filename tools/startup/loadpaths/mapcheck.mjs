// mapcheck.mjs — stdin の JSON 配列 (Win パス) を pathreg JS ミラー (createMapper) で VFS パスへ写像して JSON 配列で返す。
// 写像規則は tools/shimx/pathreg を import するだけで再実装しない (check.py が /fl/<rel> との一致を検査する)。
import { createMapper } from '../../shimx/pathreg/js/pathmap.mjs';

let s = '';
for await (const c of process.stdin) s += c;
const m = createMapper();
process.stdout.write(JSON.stringify(JSON.parse(s).map((p) => m.map(p))));
