// M11 実行後の guest ポインタ検査 (#1004 / #403 受入 3 の後半).
// 実行後の guest メモリ全体で、4 バイト整列 word の値が image VA 範囲 [0x400000, 0x400000+0x1ac0000) に入るものを数える。
// ただし実行前 (イメージ載せ直後) から既に範囲内だった word は、PE の定数データであり remap 漏れではないので除外する。
// 残件 (= 実行で新たに範囲内になった word) は JSON の ptrcheck.image_va_words_new に出す。
// ゲート (#2778): 環境変数 (呼出側が指定。run = M11_PTRCHECK_MAX_NEW, survey = M11_PTRCHECK_SURVEY_MAX_NEW) に
//   整数 n を与えたときだけ, image_va_words_new > n で不合格 (呼出側が exit 1)。未設定は情報出力のみ。
//   基準 n は同一 wasm・image の実測値 (ratchet)。値 0 固定にしないのは, 正当な LVA 整数が範囲に入るため (REPORT_N1004 §3・§5)。
//   非整数・負の n は不合格 (fail-closed)。
// 分類 (#3113): 新規 word を IR・PE・image から作った定数集合 (m11_ptrclass.py → work/ptrclass/classes.json) で 4 類に分ける。
//   A (code_va): 関数先頭 VA。icall キーとして VA で持つのが設計どおりなので未 remap に数えない。
//   B (unremap_cand): IR がポインタ定数として使うデータ領域 VA で、image の DIR64 地点の値ではないもの。LVA で持つべき値が VA のまま入った未 remap の疑い。
//   D (image_copy): B と同じ数値だが、image の DIR64 地点に実行時の値として入っている (LB=0 の LVA とぶつかる)。イメージ由来のコピーと見なし数えない。
//   C (other): 上記以外 (整数・計算結果)。値だけでは判定しないので数えない。
//   B の件数に基準 (M11_PTRCHECK_UNREMAP_MAX / M11_PTRCHECK_SURVEY_UNREMAP_MAX) を与えると、超えたら不合格。
//   分類ファイルが無いのに基準を与えたら不合格 (fail-closed)。
// M11_PTRCHECK_INJECT=<offset> を与えると、その offset に M11_PTRCHECK_INJECT_VALUE (既定 0x400000) を書き込む (ネガティブコントロール)。
// M11_PTRCHECK_DUMP=<path> を与えると、範囲内の新規 word を "offset value" (10 進) の行で書き出す (分類の検証用)。
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
export const IMG_VA_LO = 0x400000;
export const IMG_VA_SIZE = 0x1ac0000;
const inRange = (v) => v >= IMG_VA_LO && v < IMG_VA_LO + IMG_VA_SIZE;
const hex = (n) => '0x' + n.toString(16);
const M11 = path.dirname(fileURLToPath(import.meta.url));
const CLASSES = process.env.M11_PTRCLASS || path.join(M11, 'work', 'ptrclass', 'classes.json');

// 検証用 env (M11_PTRCHECK_INJECT・M11_PTRCHECK_INJECT_VALUE) の整数。非整数は例外にする (黙って 0 番地や NaN を書かない)。
export function envInt(name, raw) {
  if (!/^(0x[0-9a-fA-F]+|\d+)$/.test(raw)) throw new Error(`${name}=${raw} は整数ではない (10 進または 0x 付き 16 進)`);
  return Number(raw);
}

// 分類の定数集合を読む。ファイルが無い・壊れている場合は available=false (分類は行わず、基準付きなら不合格)。
export function loadClasses(file = CLASSES) {
  try {
    const d = JSON.parse(fs.readFileSync(file, 'utf8'));
    return { available: true, file, code: new Set(d.code), data: new Set(d.data), dataImg: new Set(d.data_image_lva), ir_sha256: d.ir_sha256, pe_sha256: d.pe_sha256, image_sha256: d.image_sha256 };
  } catch (_) {
    return { available: false, file, code: null, data: null, dataImg: null, ir_sha256: null, pe_sha256: null, image_sha256: null };
  }
}

// 実行前 (イメージ載せ直後・ヒープは 0) に範囲内だった word の offset を記録する。
export function ptrPre(mod, n) {
  const w = new Uint32Array(mod.HEAPU8.buffer, 0, n >>> 2);
  const pre = new Set();
  for (let i = 0; i < w.length; i++) if (inRange(w[i])) pre.add(i);
  return pre;
}

// 実行後の検査。mem 全体を走査する (n は image の長さ。ヒープは image の外側に続く)。
// maxEnv: ゲートの基準を読む環境変数名 (未設定・空なら情報出力のみ)。
// unremapEnv: 分類 B (未 remap の疑い) の基準を読む環境変数名。
export function ptrCheck(mod, pre, maxEnv = 'M11_PTRCHECK_MAX_NEW', unremapEnv = 'M11_PTRCHECK_UNREMAP_MAX') {
  const inj = process.env.M11_PTRCHECK_INJECT;
  const w = new Uint32Array(mod.HEAPU8.buffer, 0, mod.HEAPU8.length >>> 2);
  const injRaw = process.env.M11_PTRCHECK_INJECT_VALUE;
  const injV = injRaw ? envInt('M11_PTRCHECK_INJECT_VALUE', injRaw) : IMG_VA_LO;
  if (inj !== undefined && inj !== '') w[envInt('M11_PTRCHECK_INJECT', inj) >>> 2] = injV;
  const cls = loadClasses();
  const offs = [];
  const boffs = [];
  const dump = process.env.M11_PTRCHECK_DUMP;
  const rows = [];
  let post = 0, nA = 0, nB = 0, nC = 0, nD = 0;
  for (let i = 0; i < w.length; i++) {
    if (inRange(w[i]) && !pre.has(i)) {
      post++;
      if (offs.length < 8) offs.push(hex(i * 4));
      if (dump) rows.push((i * 4) + ' ' + w[i]);
      if (cls.available) {
        if (cls.code.has(w[i])) nA++;
        else if (cls.data.has(w[i])) {
          if (cls.dataImg.has(w[i])) nD++;
          else { nB++; if (boffs.length < 8) boffs.push(hex(i * 4)); }
        } else nC++;
      }
    }
  }
  if (dump) fs.writeFileSync(dump, rows.join('\n') + '\n');
  const raw = process.env[maxEnv];
  const gated = raw !== undefined && raw !== '';
  const max = gated && /^\d+$/.test(raw) ? Number(raw) : null;
  const rawU = process.env[unremapEnv];
  const gatedU = rawU !== undefined && rawU !== '';
  const maxU = gatedU && /^\d+$/.test(rawU) ? Number(rawU) : null;
  return {
    ok: post === 0,
    image_va_words_pre: pre.size,
    image_va_words_new: post,
    first_offsets: offs,
    range: [hex(IMG_VA_LO), hex(IMG_VA_LO + IMG_VA_SIZE)],
    injected: inj || null,
    injected_value: inj ? hex(injV) : null,
    gate: { env: maxEnv, gated, max, pass: !gated || (max !== null && post <= max) },
    unremap: {
      classes: { file: path.relative(M11, cls.file), available: cls.available, ir_sha256: cls.ir_sha256, pe_sha256: cls.pe_sha256, image_sha256: cls.image_sha256 },
      code_va: cls.available ? nA : null,
      unremap_cand: cls.available ? nB : null,
      image_copy: cls.available ? nD : null,
      other: cls.available ? nC : null,
      first_offsets: boffs,
      gate: { env: unremapEnv, gated: gatedU, max: maxU, pass: !gatedU || (cls.available && maxU !== null && nB <= maxU) },
    },
  };
}
