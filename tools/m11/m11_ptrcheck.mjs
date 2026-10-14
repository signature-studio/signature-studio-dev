// M11 実行後の guest ポインタ検査 (#1004 / #403 受入 3 の後半).
// 実行後の guest メモリ全体で、4 バイト整列 word の値が image VA 範囲 [0x400000, 0x400000+0x1ac0000) に入るものを数える。
// ただし実行前 (イメージ載せ直後) から既に範囲内だった word は、PE の定数データであり remap 漏れではないので除外する。
// 残件 (= 実行で新たに範囲内になった word) は JSON の ptrcheck.image_va_words_new に出す。
// ゲート (#2778): 環境変数 (呼出側が指定。run = M11_PTRCHECK_MAX_NEW, survey = M11_PTRCHECK_SURVEY_MAX_NEW) に
//   整数 n を与えたときだけ, image_va_words_new > n で不合格 (呼出側が exit 1)。未設定は情報出力のみ。
//   基準 n は同一 wasm・image の実測値 (ratchet)。値 0 固定にしないのは, 正当な LVA 整数が範囲に入るため (REPORT_N1004 §3・§5)。
//   非整数・負の n は不合格 (fail-closed)。
// M11_PTRCHECK_INJECT=<offset> を与えると、その offset に既知の未 remap 値 0x400000 を書き込む (ネガティブコントロール)。
export const IMG_VA_LO = 0x400000;
export const IMG_VA_SIZE = 0x1ac0000;
const inRange = (v) => v >= IMG_VA_LO && v < IMG_VA_LO + IMG_VA_SIZE;
const hex = (n) => '0x' + n.toString(16);

// 実行前 (イメージ載せ直後・ヒープは 0) に範囲内だった word の offset を記録する。
export function ptrPre(mod, n) {
  const w = new Uint32Array(mod.HEAPU8.buffer, 0, n >>> 2);
  const pre = new Set();
  for (let i = 0; i < w.length; i++) if (inRange(w[i])) pre.add(i);
  return pre;
}

// 実行後の検査。mem 全体を走査する (n は image の長さ。ヒープは image の外側に続く)。
// maxEnv: ゲートの基準を読む環境変数名 (未設定・空なら情報出力のみ)。
export function ptrCheck(mod, pre, maxEnv = 'M11_PTRCHECK_MAX_NEW') {
  const inj = process.env.M11_PTRCHECK_INJECT;
  const w = new Uint32Array(mod.HEAPU8.buffer, 0, mod.HEAPU8.length >>> 2);
  if (inj !== undefined && inj !== '') w[Number(inj) >>> 2] = IMG_VA_LO;
  const offs = [];
  let post = 0;
  for (let i = 0; i < w.length; i++) {
    if (inRange(w[i]) && !pre.has(i)) { post++; if (offs.length < 8) offs.push(hex(i * 4)); }
  }
  const raw = process.env[maxEnv];
  const gated = raw !== undefined && raw !== '';
  const max = gated && /^\d+$/.test(raw) ? Number(raw) : null;
  return {
    ok: post === 0,
    image_va_words_pre: pre.size,
    image_va_words_new: post,
    first_offsets: offs,
    range: [hex(IMG_VA_LO), hex(IMG_VA_LO + IMG_VA_SIZE)],
    injected: inj || null,
    gate: { env: maxEnv, gated, max, pass: !gated || (max !== null && post <= max) },
  };
}
