// M11 実行後の guest ポインタ検査 (#1004 / #403 受入 3 の後半).
// 実行後の guest メモリ全体で、4 バイト整列 word の値が image VA 範囲 [0x400000, 0x400000+0x1ac0000) に入るものを数える。
// ただし実行前 (イメージ載せ直後) から既に範囲内だった word は、PE の定数データであり remap 漏れではないので除外する。
// 残件 (= 実行で新たに範囲内になった word) は情報出力のみ (JSON の ptrcheck.image_va_words_new)。exit は変えない。
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
export function ptrCheck(mod, pre) {
  const inj = process.env.M11_PTRCHECK_INJECT;
  const w = new Uint32Array(mod.HEAPU8.buffer, 0, mod.HEAPU8.length >>> 2);
  if (inj !== undefined && inj !== '') w[Number(inj) >>> 2] = IMG_VA_LO;
  const offs = [];
  let post = 0;
  for (let i = 0; i < w.length; i++) {
    if (inRange(w[i]) && !pre.has(i)) { post++; if (offs.length < 8) offs.push(hex(i * 4)); }
  }
  return {
    ok: post === 0,
    image_va_words_pre: pre.size,
    image_va_words_new: post,
    first_offsets: offs,
    range: [hex(IMG_VA_LO), hex(IMG_VA_LO + IMG_VA_SIZE)],
    injected: inj || null,
  };
}
