// lic_check.mjs — KH-9 ライセンス stub モジュール (A: stub 本体 / B: 対照) の node 実行検証。
//   node lic_check.mjs <workDir>          (workDir/licA/mod.cjs と workDir/licB/mod.cjs を検証)
//
// 検証内容:
//   [A] stub 14 関数が「ライセンス済み」定数を返すこと (引数非依存 = deref なし)
//   [A] getStatusAndDaysLeft / keyInit / applyKey のメモリ書き込み形状
//   [A] 状態マージ 0x1800b4b10 (実 IR のまま) の優先度テーブル
//   [B] 分類 thunk 5 種 (実 IR) に 9 を入力した値 == モジュール A の stub 定数 (等価検証)
//   [B] 実マージに 9 を入力した全組合せが「許可側」になること
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

const work = process.argv[2];
const MA = await (require(path.resolve(work, 'licA/mod.cjs')))();
const MB = await (require(path.resolve(work, 'licB/mod.cjs')))();
const H = (M) => M.HEAPU8;
const DV = (M) => new DataView(M.HEAPU8.buffer, M.HEAPU8.byteOffset, M.HEAPU8.byteLength);

const F = { getStatus: '180054bd0', stDays: '1800549c0', hasTag: '1800548a0', getPending: '180054ac0',
            thkA: '1800b4ac0', thkB: '1800b4ad0', thk25: '1800b4ae0', thk9: '1800b4af0', thk13: '1800b4b00',
            merge: '1800b4b10', isMaster: '180021d50', verify: '180021bd0', applyKey: '1800219b0',
            keyInit: '180021490', khsUnlock: '180002780' };
const ex = (M, k) => { const f = M['_function_' + F[k]]; if (!f) throw new Error('export missing: ' + k); return f; };

let ok = 0, fail = [];
const chk = (name, cond, got) => { if (cond) { ok++; } else { fail.push({ name, got: String(got) }); } };
const MALLOC = (M, n) => { const p = Number(M._malloc(n)); if (!p) throw new Error('malloc'); return p; };

// ---- [A] stub 定数返し (引数に 0 / garbage / 実ポインタの 3 種を入れても同じ値)
const dvA = DV(MA);
const scratch = MALLOC(MA, 256);
H(MA).fill(0, scratch, scratch + 256);
const B = (v) => BigInt(v);   // 引数は全て BigInt 化して渡す (wasm i64 ABI)
for (const argset of [[0, 0, 0, 0], [0x16, 0xdead, 1, 0], [scratch, scratch, 3, 0]].map(a => a.map(B))) {
  chk('A.getStatus==9', Number(ex(MA, 'getStatus')(argset[0], argset[1], argset[2], argset[3]) & 0xffffffffn) === 9, 'getStatus');
  chk('A.hasTag==1', Number(ex(MA, 'hasTag')(argset[0], 0n, 0n, 0n) & 0xffn) === 1, 'hasTag');
  chk('A.getPending==0', Number(ex(MA, 'getPending')(argset[0], 0n, 0n, 0n) & 0xffn) === 0, 'getPending');
  chk('A.thkA==1', Number(ex(MA, 'thkA')(argset[0], 0n, 0n, 0n) & 0xffn) === 1, 'thkA');
  chk('A.thkB==0', Number(ex(MA, 'thkB')(argset[0], 0n, 0n, 0n) & 0xffn) === 0, 'thkB');
  chk('A.thk25==0', Number(ex(MA, 'thk25')(argset[0], 0n, 0n, 0n) & 0xffn) === 0, 'thk25');
  chk('A.thk9==1', Number(ex(MA, 'thk9')(argset[0], 0n, 0n, 0n) & 0xffn) === 1, 'thk9');
  chk('A.thk13==0', Number(ex(MA, 'thk13')(argset[0], 0n, 0n, 0n) & 0xffn) === 0, 'thk13');
  chk('A.isMaster==1', Number(ex(MA, 'isMaster')(0n, 0n, 0n, 0n) & 0xffn) === 1, 'isMaster');
  chk('A.verify==26', Number(ex(MA, 'verify')(BigInt(scratch), 0n, 0n, 0n) & 0xffffffffn) === 26, 'verify');
  chk('A.khsUnlock nop', Number(ex(MA, 'khsUnlock')(BigInt(scratch), 0n, 0n, 0n) & 0xffffffffn) === 0, 'khsUnlock');
}
// getStatusAndDaysLeft: {out}=9, {out+4}=0, ret==out
{
  const p = MALLOC(MA, 64); H(MA).fill(0xee, p, p + 64);
  const r = Number(ex(MA, 'stDays')(BigInt(p), 0n, 0n, 0n) & 0xffffffffn);
  chk('A.stDays ret==out', r === p, r);
  chk('A.stDays [out]==9', dvA.getUint32(p, true) === 9, dvA.getUint32(p, true));
  chk('A.stDays [out+4]==0', dvA.getUint32(p + 4, true) === 0, dvA.getUint32(p + 4, true));
}
// keyInit: state=0x17, found=1, SSO size=0 cap=0xf
{
  const p = MALLOC(MA, 64); H(MA).fill(0, p, p + 64);
  const r = Number(ex(MA, 'keyInit')(BigInt(p), BigInt(scratch), 0n, 0n) & 0xffffffffn);
  chk('A.keyInit ret==out', r === p, r);
  chk('A.keyInit state==0x17', dvA.getUint32(p, true) === 0x17, dvA.getUint32(p, true));
  chk('A.keyInit found==1', H(MA)[p + 4] === 1, H(MA)[p + 4]);
  chk('A.keyInit size==0', dvA.getBigUint64(p + 24, true) === 0n, dvA.getBigUint64(p + 24, true));
  chk('A.keyInit cap==0xf', dvA.getBigUint64(p + 32, true) === 15n, dvA.getBigUint64(p + 32, true));
}
// applyKey: state=0x1a, ret 1
{
  const p = MALLOC(MA, 64); H(MA).fill(0, p, p + 64);
  const r = Number(ex(MA, 'applyKey')(BigInt(p), BigInt(scratch), 0n, 0n) & 0xffffffffn);
  chk('A.applyKey ret==1', r === 1, r);
  chk('A.applyKey state==0x1a', dvA.getUint32(p, true) === 0x1a, dvA.getUint32(p, true));
}
// [A] merge (実 IR): 優先度テーブル class {5,7,8,26}=4 > {9}=3 > {25}=2 > {27}=1 > 他=0
{
  const mg = ex(MA, 'merge');
  const cases = [[9, 26, 26], [26, 9, 26], [25, 9, 9], [9, 25, 9], [24, 9, 9], [9, 24, 9], [13, 9, 9], [9, 13, 9],
                 [28, 9, 9], [9, 28, 9], [27, 9, 9], [9, 27, 9], [5, 8, 5], [8, 5, 8], [0, 9, 9], [22, 22, 22], [9, 9, 9], [7, 26, 7]];
  for (const [x, y, want] of cases) {
    const g = Number(mg(BigInt(x), BigInt(y), 0n, 0n) & 0xffffffffn);
    chk(`A.merge(${x},${y})==${want}`, g === want, g);
  }
}// ---- [B] 実 IR の分類 thunk に 9 を入力 == モジュール A の stub 定数
{
  const pairs = [['thkA', 1], ['thkB', 0], ['thk25', 0], ['thk9', 1], ['thk13', 0]];
  for (const [k, want] of pairs) {
    const a = Number(ex(MA, k)(9n, 0n, 0n, 0n) & 0xffn);
    const b = Number(ex(MB, k)(9n, 0n, 0n, 0n) & 0xffn);
    chk(`B.${k}(9) == stubA(${want})`, b === want && a === b, `A=${a} B=${b}`);
  }
  // thunk の全状態スイープ (実 IR): 許可集合の裏取り
  const ac0 = []; for (let s = 0; s <= 40; s++) ac0.push(Number(ex(MB, 'thkA')(BigInt(s), 0n, 0n, 0n) & 0xffn));
  const allowed = ac0.map((v, s) => v ? s : -1).filter(s => s >= 0);
  chk('B.thkA allowed set == {5,7,8,9,25,26}', JSON.stringify(allowed) === JSON.stringify([5, 7, 8, 9, 25, 26]), JSON.stringify(allowed));
  const ad0 = []; for (let s = 0; s <= 40; s++) ad0.push(Number(ex(MB, 'thkB')(BigInt(s), 0n, 0n, 0n) & 0xffn));
  const allowedB = ad0.map((v, s) => v ? s : -1).filter(s => s >= 0);
  chk('B.thkB allowed set == {5,7,8,26}', JSON.stringify(allowedB) === JSON.stringify([5, 7, 8, 26]), JSON.stringify(allowedB));
}
// [B] 実 merge に stub 定数 9 を入力: どの相手状态でも「9 以上の class」側 = ライセンス済み側に分岐
{
  const mg = ex(MB, 'merge');
  const cls = { 5: 4, 7: 4, 8: 4, 9: 3, 25: 2, 26: 4, 27: 1 };
  let allOk = true, bad = [];
  for (let s = 0; s <= 28; s++) {
    const m1 = Number(mg(9n, BigInt(s), 0n, 0n) & 0xffffffffn), m2 = Number(mg(BigInt(s), 9n, 0n, 0n) & 0xffffffffn);
    // 9 とのマージは、相手が class4 ({5,7,8,26}) なら相手、それ以外なら 9 (class3) — 常に「未満状態に落ちない」
    const want = (cls[s] ?? 0) > 3 ? s : 9;
    if (m1 !== want || m2 !== want) { allOk = false; bad.push(`s=${s}: m(9,s)=${m1} m(s,9)=${m2} want=${want}`); }
  }
  chk('B.merge(9,s) licensed side for all s<=28', allOk, bad.join(', '));
  chk('B.getStatus==9', Number(ex(MB, 'getStatus')(0n, 0n, 0n, 0n) & 0xffffffffn) === 9, 'B.getStatus');
}

console.log(JSON.stringify({ ok, fail }, null, 1));
process.exit(fail.length ? 1 : 0);
