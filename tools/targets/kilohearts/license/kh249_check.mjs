// kh249_check.mjs — KH-11 (#249) ブラウザ分類 0x180ef7fc0 の検査 (module F)。[1][2] は lift 済み IR の実行、[3] は機械語読解の式の再実装 (lift IR 未検証・§6.2)
//   node kh249_check.mjs [workDir]   (workDir 既定: work/licF)
// [1] lift 済み実 IR の分類 thunk A (0x1800b4ac0) / C (0x1800b4ae0) を status 0..40 で実行し、ブラウザの
//     エントリ採否ゲート (0x180ef8732〜0x180ef87c8) の真理値表を再構成 (getStatus は stub 9 を実行)
// [2] ブラウザ分類関数 function_180ef7fc0 自体を実行し、最初の未 lift callee (0x180112a30) の fail-fast に
//     到達することを確認 (= lift IR が emcc を通り入口から実行される)
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const Mod = require(path.resolve(process.argv[2] || 'work/licF', 'mod.cjs'));
const M = await Mod();
let ok = 0, ng = 0;
const chk = (c, m) => { if (c) { ok++; } else { ng++; console.log('  NG', m); } };
const A = (s) => Number(M['_function_1800b4ac0'](BigInt(s), 0n, 0n, 0n) & 0xffn) !== 0;   // 許可集合
const C = (s) => Number(M['_function_1800b4ae0'](BigInt(s), 0n, 0n, 0n) & 0xffn) !== 0;   // s==25
const GS = Number(M['_function_180054bd0'](0n, 0n, 3n, 0n)) | 0;                    // stub getStatus
chk(GS === 9, 'getStatus stub != 9: ' + GS);
const allowed = [], noLic = [];
for (let s = 0; s <= 40; s++) { if (A(s)) allowed.push(s); if (C(s)) noLic.push(s); }
chk(JSON.stringify(allowed) === JSON.stringify([5, 7, 8, 9, 25, 26]), 'thunk A 許可集合 ' + allowed);
chk(JSON.stringify(noLic) === JSON.stringify([25]), 'thunk C 集合 ' + noLic);
// ゲート (0x180ef8732..0x180ef87c8): A(s)? (r13 = !C(s)) : 0 ; r13 != 0 → 登録 (unlocked, locked=r13^1=0)
//   r13 == 0 のとき global flag [0x182358298] が非 0 なら「locked」で登録、0 なら非表示
const gate = (s, flag) => { const r13 = A(s) ? (C(s) ? 0 : 1) : 0; return r13 ? 'listed/unlocked' : (flag ? 'listed/locked' : 'hidden'); };
const tbl = {};
for (const f of [0, 1]) { tbl[f] = {}; for (let s = 0; s <= 40; s++) { const g = gate(s, f); (tbl[f][g] ||= []).push(s); } }
console.log('  gate flag=0:', JSON.stringify(tbl[0]));
console.log('  gate flag=1:', JSON.stringify(tbl[1]));
chk(gate(GS, 0) === 'listed/unlocked' && gate(GS, 1) === 'listed/unlocked', 'status 9 は flag 無関係に listed/unlocked');
chk(JSON.stringify(tbl[0]['listed/unlocked']) === JSON.stringify([5, 7, 8, 9, 26]), 'unlocked 集合');
chk(gate(25, 0) === 'hidden' && gate(25, 1) === 'listed/locked', 'status 25 (No license)');
// [2] 入口実行
let msg = null;
try { M['_function_180ef7fc0'](0x04000000n, 0n, 0n, 0n); } catch (e) { msg = String(e && e.message || e); }
console.log('  entry run ->', msg);
chk(msg && /unlifted callee 0x180112a30/.test(msg), '入口実行が最初の未 lift callee 0x180112a30 に到達しない: ' + msg);
// [3] カテゴリ割当 (0x180ef82aa〜0x180ef830b の機械語読解を node へ移植・independent に PE から free-list を読む)
//   cat = (id=='grup') ? 3 : ([entry+0x22] != 0) ? 2 : (id ∈ list@0x180ef825b..) ? 1 : 0   (名前表: 0 Essential / 1 Premium / 2 Hosts / 3 Groups)
import fs from 'node:fs';
const CORE = path.resolve('..', 'work', 'winpkg', 'HeartCore.core_64');
const pe = fs.readFileSync(CORE); const lfanew = pe.readUInt32LE(0x3c); const nsec = pe.readUInt16LE(lfanew + 6);
const optsz = pe.readUInt16LE(lfanew + 20); const secs = [];
for (let i = 0; i < nsec; i++) { const o = lfanew + 24 + optsz + i * 40; secs.push({ va: pe.readUInt32LE(o + 12), vs: pe.readUInt32LE(o + 8), raw: pe.readUInt32LE(o + 20), rs: pe.readUInt32LE(o + 16) }); }
const rd = (va, n) => { const r = va - 0x180000000; for (const s of secs) if (r >= s.va && r < s.va + Math.max(s.vs, s.rs)) return pe.subarray(s.raw + r - s.va, s.raw + r - s.va + n); throw new Error('va ' + va.toString(16)); };
// movups xmm0,[rip+d] (7B) の参照先: 0x180ef8262+0x14ab2ea (後半 16B) / 0x180ef826d+0x14ab2d3 (前半 16B)、計 28B = 7 dword
const hi = rd(0x180ef8262 + 0x14ab2ea, 16), lo = rd(0x180ef826d + 0x14ab2d3, 16);
const list = Buffer.concat([lo, hi.subarray(4)]);   // [rax+0] = lo(16B), [rax+0xc] = hi(16B) (12..28 が重なる)
const freeIds = new Set(); for (let i = 0; i < 28; i += 4) freeIds.add(list.readUInt32LE(i));
const fcc = (id) => id.charCodeAt(0) * 2 ** 24 + id.charCodeAt(1) * 2 ** 16 + id.charCodeAt(2) * 2 ** 8 + id.charCodeAt(3);
// 注: 本節は lift IR (function_180ef7fc0) を通した検証ではない (入口は未 lift callee で停止する = [2])。機械語読解の式の再実装であり、
//     式の定数を PE の命令バイトと照合 ([3a]) し、式を壊すと結果が変わること ([3b] 負律対照) を確認するところまで。
const mkCat = (ids, c = { grup: 'grup', t_grup: 3, t_flag: 2, t_in: 1, t_out: 0 }) =>
  (id, flag22) => id === c.grup ? c.t_grup : flag22 ? c.t_flag : (ids.has(fcc(id)) ? c.t_in : c.t_out);
const cat = mkCat(freeIds);
const piPath = path.resolve('..', 'work', 'winpkg', 'product_index.json');
if (!fs.existsSync(piPath)) { console.error('FAIL: ' + piPath + ' が無い。python3 scripts/kh249_product_index.py で生成 (入力: plugins-kilohearts)'); process.exit(1); }
const plugins = JSON.parse(fs.readFileSync(piPath, 'utf8')).plugins.filter(p => p.id !== 'core');
const dist = (f) => JSON.stringify([0, 1, 2, 3].map(k => plugins.filter(p => f(p.id) === k).map(p => p.id)));
const prem = plugins.filter(p => cat(p.id, 0) === 1).map(p => p.id).sort();
chk(freeIds.size === 7, 'list size ' + freeIds.size);
chk(JSON.stringify(prem) === JSON.stringify(['kdsp', 'kfat', 'kpeq', 'ksco', 'ksft', 'ksge', 'ksws']), 'category1 ids ' + prem);
chk(plugins.length === 45 && plugins.filter(p => cat(p.id, 0) === 0).length === 38, 'category0 count');
chk(cat('grup', 0) === 3 && cat('ksgn', 1) === 2, 'grup/hosts flag');
// [3a] 式の定数を命令バイトから照合 (0x180ef82d7..0x180ef82f2): mov r8d,[rbp-0x48]; mov edx,3; cmp r8d,'grup'; je; mov edx,2; cmp byte [rbp-0x36],0; jne
const code = rd(0x180ef82d7, 0x1c).toString('hex');
chk(/^448b45b8ba030000004181f87075726774[0-9a-f]{2}ba02000000807dca0075/.test(code), 'grup 比較/カテゴリ定数 3,2/entry+0x22 の命令バイト ' + code);
// [3b] 負律対照: 式を壊すと結果が変わる (変わらなければ検査が自明 = NG)
const base = dist(cat);
const mut = {
  'list 空': mkCat(new Set()),
  'list 1 id 欠落': mkCat(new Set([...freeIds].slice(1))),
  'list にダミー id 追加': mkCat(new Set([...freeIds, fcc('kscm')])),
  'grup→別 id': mkCat(freeIds, { grup: 'kscm', t_grup: 3, t_flag: 2, t_in: 1, t_out: 0 }),
  'in/out 入替': mkCat(freeIds, { grup: 'grup', t_grup: 3, t_flag: 2, t_in: 0, t_out: 1 }),
};
for (const [k, f] of Object.entries(mut)) chk(dist(f) !== base, '負律対照 (' + k + ') で結果が変わらない');
console.log('  category1 (Premium):', prem.join(','), ' category0 (Essential):', plugins.filter(p => cat(p.id, 0) === 0).length, ' mutation controls:', Object.keys(mut).length);
console.log(`kh249_check ok=${ok} ng=${ng}`);
process.exit(ng ? 1 : 0);
