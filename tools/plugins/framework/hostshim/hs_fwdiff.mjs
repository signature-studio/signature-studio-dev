// hs_fwdiff.mjs — CAB-195 検収: framework build 挙動不変の独立照合 (規則 41 ネガティブコントロール)。
//
// 何を比べるか (定義):
//   A = HEAD (CAB-195) の fw_stage2.sh 相当ビルド (hostshim.c リンク + fw_table.py の hs slot 登録
//       + fw_rt.c fail-soft + decode-miss fail-soft + fw_table.py の return 値伝達変更)
//   B = b8e762d^ (CAB-195 親) の fw_stage2.sh 相当ビルド (上記すべて無し)
//   比較量: exit パス / dispatch 総数 / ff 数 / va calls / alloc count / と dispatch site の
//           ヒストグラム (stderr の [dispatch] 行。fw_rt.c 側 trace は 40 行でキャップ)。
// 使い方: node hs_fwdiff.mjs <work>/fw_image.bin <fwchk_head.cjs> <fwchk_base.cjs>
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve as pathResolve } from 'node:path';

const IMG = process.argv[2];
const A = process.argv[3];
const B = process.argv[4];
const req = createRequire(import.meta.url);
const img = readFileSync(IMG);
const IMAGE_BASE = 0x400000;
const BLK = 0x8a1000;

async function smoke(cjs) {
  const create = req(pathResolve(cjs));
  const mod = await create();
  const H = mod.HEAPU8;
  H.set(img, IMAGE_BASE);
  for (let o = 0; o < 0x100; o++) H[BLK + o] = 0;

  // stderr を捕まえて dispatch site ヒストグラムを作る
  const w = process.stderr.write.bind(process.stderr);
  let buf = '';
  process.stderr.write = (chunk, ...rest) => { buf += chunk; return true; };
  let path = 'return', err = '';
  try {
    mod._function_6c13a0(BigInt(IMAGE_BASE), 1n, 0n, 0n);
  } catch (e) {
    const m = e.message || '';
    if (m.includes('exit(0)') || m.includes('corrupted its heap') || m.includes('exit(102)'))
      path = 'Halt0/RestoreContext';
    else { path = 'TRAP'; err = m.split('\n')[0]; }
  }
  process.stderr.write = w;
  const s = {
    dispatch: Number(mod._fw_dispatch_count()),
    ff: Number(mod._fw_ff_count()),
    va: Number(mod._fw_va_calls()),
    heap: Number(mod._fw_alloc_count()),
    allocBytes: Number(mod._fw_alloc_bytes()),
  };
  const sites = {};
  const re = /\[dispatch\] site=0x([0-9a-f]+)/g;
  let m;
  while ((m = re.exec(buf))) sites[m[1]] = (sites[m[1]] || 0) + 1;
  return { path, err, ...s, sites, logBytes: buf.length };
}

const ra = await smoke(A);
const rb = await smoke(B);
console.error('[fwdiff] HEAD  :', JSON.stringify(ra));
console.error('[fwdiff] parent:', JSON.stringify(rb));
const same = JSON.stringify(ra) === JSON.stringify(rb);
console.error(same
  ? '[fwdiff] SAME — framework build 挙動は CAB-195 変更で不変'
  : '[fwdiff] DIFFER — framework build 挙動が変化している');
process.exit(same ? 0 : 1);
