// em_check.mjs — KH-10 (CAB-247) EditorModel 層部分 lift の wasm 実証デモ。
//   node em_check.mjs [workDir]   (workDir 既定: work/licE)
//
// 実証内容:
//   [1] 47 製品分の EditorModel 初期化: work/ctors47.json の 47 呼出元に対応する
//       47 組の (product name, kind, property state) を合成して EditorModel ctor (0x180051af0)
//       を実行し、初期化不変式を検証する (vtable/param_6 copy/kind/PM/helper/stack args)。
//   [2] poll2 (0x180052a00) 実行: getStatus≡9 (stub seam) で「編集可」プロパティ
//       (+0x548=1, +0x5c8 dirty=1, +0x550) が立つこと (47 製品全部)。
//   [3] +0x1088 書込側 (0x18002e850) の豆知識検証: thunkB(9)=0 で書込が發火しないこと
//       (= +0x1088 が 0 のまま = poll2 の編集可が維持される) と、+0x1088=1 注入で
//       poll2 が「編集不可」に落ちること (= flag の消費側としての意味)。
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

const workDir = process.argv[2] || 'work/licE';
const Mod = require(path.resolve(workDir, 'mod.cjs'));
const A = 0x04000000;
const EM_CTOR = 0x180051af0, POLL1 = 0x180052830, POLL2 = 0x180052a00, WRITER = 0x18002e850;
const SUBSCRIBE = 0x1800526f0, REGISTER = 0x18002e710, FIRE = 0x18010b180;
const MGR_SLOT = 0x400f020n;   /* getManager の fake manager (0x0400F000) + 0x20 = LicenseManager EventSlot */

// 47 呼出元 (work/ctors47.json) に対応する合成 desc: 製品名スニペット + kind
const ctors47 = JSON.parse(fs.readFileSync('work/ctors47.json', 'utf8'));
const KINDS = [0, 3, 5, 7, 8, 9, 22, 25, 26, 40];

const M = await Mod();
const H = M.HEAPU8;
const dv = new DataView(H.buffer);

let ok = 0, ng = 0;
const fail = (m) => { ng++; console.log('  NG', m); };
const pass = (m) => { ok++; if (m) console.log('  ok', m); };

// アリーナ初期化 + オブジェクト配置
function setup(productIdx) {
  H.fill(0, A, A + 0x8000);
  dv.setBigUint64(A, 0x400100n, true);            // new bump cursor
  dv.setUint32(A + 8, 9, true);                   // getStatus seam cell (licensed)
  const EM = 0x4001100, SUB = 0x4001d00, PM = 0x4003100, DESC = 0x4004100, P7 = 0x4004200, SP = 0x4004240;
  // param_6: 16 u32 (製品パラメタ) — 製品番号で変化させる
  for (let k = 0; k < 16; k++) dv.setUint32(DESC + 4 * k, (0x11100111 * (k + 1) + productIdx * 0x1010) >>> 0, true);
  // param_6+0x40 (FUN_1800524e0 のコピー元): 5 文字列 (SSO) + u16
  const D = DESC + 0x40;
  const name = 'kh' + productIdx.toString(36).padStart(2, '0') + 'product';
  for (const [off, wide] of [[0, 0], [0x20, 0], [0x40, 0], [0x80, 0]]) {
    const s = name.slice(0, wide ? 8 : 7);
    for (let i = 0; i < 16; i++) H[D + off + i] = i < s.length ? s.charCodeAt(i) : 0;
    dv.setBigUint64(D + off + 0x10, BigInt(s.length), true);
    dv.setBigUint64(D + off + 0x18, wide ? 0xFn : 7n, true);
  }
  const ws = name.slice(0, 8);
  for (let i = 0; i < 16; i++) H[D + 0x60 + i] = i < ws.length ? ws.charCodeAt(i) : 0;
  dv.setBigUint64(D + 0x60 + 0x10, BigInt(ws.length), true);
  dv.setBigUint64(D + 0x60 + 0x18, 0xFn, true);
  dv.setUint16(D + 0xa4, 0x1000 + productIdx, true);
  // param_7: kind / PM / apply gate
  dv.setUint32(P7, KINDS[productIdx % KINDS.length], true);
  dv.setBigUint64(P7 + 8, BigInt(PM), true);
  dv.setBigUint64(P7 + 0x18, (productIdx % 5 === 0) ? 1n : 0n, true);
  // SUB 注入: +0x1088 = 0 (編集可), cache クリア
  dv.setUint32(SUB + 0x1088, 0, true);
  dv.setUint32(SUB + 0x548, 0, true);
  dv.setUint32(SUB + 0x5c8, 0, true);
  return { EM, SUB, PM, DESC, P7, SP };
}

console.log('== [1] 47 製品分の EditorModel ctor + [2] poll2「編集可」実証 ==');
let editableCount = 0;
for (let i = 0; i < ctors47.length; i++) {
  const { EM, SUB, PM, DESC, P7, SP } = setup(i);
  const kind = dv.getUint32(P7, true);
  const r = M._function_180051af0(BigInt(EM), BigInt(SP), BigInt(SUB), BigInt(SP), BigInt(SP), 0x4004100n, BigInt(P7));
  if (r !== BigInt(EM)) { fail(`ctor[${i}] ret ${r}`); continue; }
  // 初期化不変式
  const vt = dv.getBigUint64(EM, true);
  if (vt !== 0x1813af778n) fail(`ctor[${i}] vtable ${vt.toString(16)}`);
  if (dv.getBigUint64(EM + 0x270, true) !== BigInt(SUB)) fail(`ctor[${i}] sub`);
  if (dv.getUint32(EM + 0x998, true) !== kind) fail(`ctor[${i}] kind ${dv.getUint32(EM + 0x998, true)}`);
  if (dv.getBigUint64(EM + 0xa90, true) !== BigInt(PM)) fail(`ctor[${i}] PM`);
  if (dv.getUint32(DESC + 4 * 0, true) !== dv.getUint32(EM + 0x9a0, true)) fail(`ctor[${i}] desc copy`);
  const hlp = dv.getBigUint64(EM + 0xac8, true);
  if (!hlp) { fail(`ctor[${i}] helper null`); continue; }
  const gate = (i % 5 === 0) ? 1 : 0;
  const wantState = gate ? 0x1a : 0x17;   // apply_key (gate=1) は状態を 0x1a (unlocked) に更新する
  if (dv.getUint32(Number(hlp), true) !== wantState) fail(`ctor[${i}] key state ${dv.getUint32(Number(hlp), true)} (want ${wantState})`);
  if (H[Number(hlp) + 4] !== 1) fail(`ctor[${i}] key found`);
  // poll2: 編集可
  M._function_180052a00(BigInt(EM));
  const editable = dv.getUint32(SUB + 0x548, true);
  const dirty = H[SUB + 0x5c8];
  if (editable !== 1 || dirty !== 1) { fail(`poll2[${i}] editable=${editable} dirty=${dirty}`); continue; }
  editableCount++;
  // poll1 も同等に立つこと
  dv.setUint32(SUB + 0x548, 0, true);
  M._function_180052830(BigInt(EM));
  if (dv.getUint32(SUB + 0x548, true) !== 1) fail(`poll1[${i}] editable`);
  pass(`product ${i} (ctor site ${ctors47[i].ctor}): editable=1 dirty=1`);
}
console.log(`  → ${editableCount}/${ctors47.length} 製品が「編集可能」として成立`);

console.log('== [3] +0x1088 書込側 (0x18002e850) と flag 消費の検証 ==');
{
  const { EM, SUB, SP, P7 } = setup(0);
  M._function_180051af0(BigInt(EM), BigInt(SP), BigInt(SUB), BigInt(SP), BigInt(SP), 0x4004100n, BigInt(P7));
  // (a) writer: thunkB(9)=0 → 書込なし (+0x1088 は 0 のまま)
  const X = 0x4004400;
  dv.setBigUint64(X + 0x100, BigInt(EM), true);
  M._function_18002e850(BigInt(X), 0n, 0n, 0n);
  if (dv.getUint32(SUB + 0x1088, true) !== 0) fail('writer: thunkB(9)=0 で +0x1088 が変化');
  else pass('writer: getStatus≡9 では +0x1088 を書かない (thunkB(9)=0) → poll2 の編集可を壊さない');
  // (b) +0x1088 = 1 (外部要因で編集ロック) → poll2 は「編集不可」
  dv.setUint32(SUB + 0x1088, 1, true);
  M._function_180052a00(BigInt(EM));
  if (dv.getUint32(SUB + 0x548, true) !== 0) fail('poll2: +0x1088=1 で編集不可になるべき');
  else pass('poll2: +0x1088=1 → 編集不可 (thunkA=1 でも flag が優先)');
  // (c) +0x1088 = 0 に戻す → 再び編集可 (cache 更新 + dirty)
  dv.setUint32(SUB + 0x1088, 0, true);
  M._function_180052a00(BigInt(EM));
  if (dv.getUint32(SUB + 0x548, true) !== 1 || H[SUB + 0x5c8] !== 1) fail('poll2: flag 解除で復帰');
  else pass('poll2: +0x1088=0 → 編集可に復帰 (cache+dirty 更新)');
}

console.log('== [4] subscribe 経路 (CAB-247 残スコープ) の wasm 実証: 状態変化 → poll1/poll2 → [+0x548] 動的更新 ==');
{
  /* KH-11 (CAB-247 残スコープ): subscribe 0x1800526f0 を no-op seam から実 IR に変更し、
   * EditorModel ctor が LicenseManager の EventSlot (mgr+0x20) へ poll1 functor を実登録する。
   * bit 精密な native 照合は em (200/700)・empoll (1000/10000) ctx-fuzz で実証済み (run_all.sh [4])。
   * ここでは wasm 上で (a) 47 製品の動的更新 (b) 10 状態スイープを実証する。
   * 注: manager 側の起火 (0x18010b180) → observer invoke 連鎖は vector-compact の ctrl vtable
   * delete thunk (0x180003360, 尾 `jmp rax`) が未 lift のため本デモでは未実施 = 未解決 (REPORT 記載)。 */
  const X = 0x4004400, STR = 0x4004500, FN = 0x4004600;
  dv.setBigUint64(X + 0x100, 0x4001100n, true);      /* writer の ctx: [X+0x100] = EM */
  dv.setBigUint64(FN, BigInt(WRITER), true);         /* functor {callback VA, i32 0} */
  dv.setUint32(FN + 8, 0, true);
  /* (a) 47 製品: ctor (subscribe 実登録) → cache クリア → poll1 → poll2 で [+0x548]=1 が动態的に立つ */
  let dynamicOk = 0;
  for (let i = 0; i < ctors47.length; i++) {
    const { EM, SUB, SP, P7 } = setup(i);
    M._function_180051af0(BigInt(EM), BigInt(SP), BigInt(SUB), BigInt(SP), BigInt(SP), 0x4004100n, BigInt(P7));
    dv.setUint32(SUB + 0x548, 0, true);
    dv.setUint32(SUB + 0x5c8, 0, true);
    dv.setUint32(A + 8, 9, true);                    /* LicenseManager 状態 = licensed */
    M._function_180052830(BigInt(EM));              /* poll1 (mgr slot 登録コールバック本体) */
    M._function_180052a00(BigInt(EM));              /* poll2 → [+0x548] */
    if (dv.getUint32(SUB + 0x548, true) === 1) dynamicOk++;
    else console.log('  NG product', i, 'editable=', dv.getUint32(SUB + 0x548, true));
  }
  if (dynamicOk === ctors47.length) pass(`subscribe 実 IR 化後の 47 製品: ${dynamicOk}/${ctors47.length} が「編集可」成立 (ctor→subscribe→poll1→poll2)`);
  else fail(`subscribe 実 IR 化後の 47 製品: ${dynamicOk}/${ctors47.length}`);
  /* (b) 10 状態スイープ: status を変えると [+0x548] が追従 (thunkA(s) && [+0x1088]==0) */
  const STAT = [0, 5, 7, 8, 9, 13, 22, 25, 26, 40];
  const thunkA = (s) => [5, 7, 8, 9, 25, 26].includes(s) ? 1 : 0;   /* mask 0x60003a0 */
  let sweepOk = 0;
  for (const s of STAT) {
    const { EM, SUB, SP, P7 } = setup(0);
    M._function_180051af0(BigInt(EM), BigInt(SP), BigInt(SUB), BigInt(SP), BigInt(SP), 0x4004100n, BigInt(P7));
    dv.setUint32(A + 8, s, true);                    /* 状態注入 */
    dv.setUint32(SUB + 0x1088, 0, true);
    M._function_180052a00(BigInt(EM));
    const editable = dv.getUint32(SUB + 0x548, true);
    if (editable === thunkA(s)) sweepOk++;
    else console.log('  NG status', s, 'editable=', editable, 'want', thunkA(s));
  }
  if (sweepOk === STAT.length) pass(`10 状態スイープ: [+0x548] が status に追従 (${sweepOk}/${STAT.length}、thunkA マスク 0x60003a0 と一致)`);
  else fail(`10 状態スイープ: ${sweepOk}/${STAT.length}`);
}

console.log(`\nRESULT ok=${ok} ng=${ng}`);
process.exit(ng ? 1 : 0);
