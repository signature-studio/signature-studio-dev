// NSIS 3 (Unicode, deflate) インストーラのヘッダから、ライセンスページ等の文字列を取り出す (LGL-5, #88)。
// Xfer の Win インストーラ (OTT / Serum 2) は規約を NSIS ヘッダの文字列表に持ち、スタンドアロンの License.txt が無い。
// 対象: 圧縮ヘッダが raw deflate (SetCompressor zlib / 非ソリッド)。LZMA / bzip2 / ソリッドは NsisError で明示的に拒否する。
// NSIS 構造 (fileform.h): firstheader = flags(4) + 0xDEADBEEF(4) + "NullsoftInst"(12) + length_of_header(4) + length_of_following_data(4)
//   直後に [4 byte: 長さ | 0x80000000 (圧縮)] + 圧縮ヘッダ。展開後ヘッダ = flags(4) + block_header[8] {offset, num} + ...
//   block 3 = 文字列表 (UTF-16LE, NUL 区切り)、block 4 = 言語表 (文字列表の終端)。offset は展開ヘッダ先頭からのバイト位置。
import { closeSync, fstatSync, openSync, readSync } from "node:fs";
import { inflateRawSync } from "node:zlib";

export class NsisError extends Error {}

const SIG = Buffer.from("efbeadde4e756c6c736f6674496e7374", "hex"); // 0xDEADBEEF + "NullsoftInst"
const NB_STRINGS = 3;
const NB_LANGTABLES = 4;
const SCAN_LIMIT = 16 << 20;
const CHUNK = 4 << 20;

function readAt(fd, pos, len) {
  const b = Buffer.alloc(len);
  let got = 0;
  while (got < len) {
    const n = readSync(fd, b, got, len - got, pos + got);
    if (n <= 0) break;
    got += n;
  }
  return b.subarray(0, got);
}

// firstheader の位置 (flags の先頭) を探す。NSIS は 512 バイト境界に置く
function findFirstHeader(fd, size) {
  const limit = Math.min(size, SCAN_LIMIT);
  for (let base = 0; base < limit; base += CHUNK) {
    const buf = readAt(fd, base, Math.min(CHUNK + SIG.length, size - base));
    for (let i = buf.indexOf(SIG); i >= 0; i = buf.indexOf(SIG, i + 1)) {
      const flagsPos = base + i - 4;
      if (flagsPos >= 0 && flagsPos % 512 === 0) return flagsPos;
    }
  }
  return -1;
}

// 展開済みヘッダ (Buffer) を返す
export function readNsisHeader(file) {
  const fd = openSync(file, "r");
  try {
    const size = fstatSync(fd).size;
    const at = findFirstHeader(fd, size);
    if (at < 0) throw new NsisError("NSIS firstheader が見つからない (NSIS インストーラではない)");
    const fh = readAt(fd, at, 32);
    if (fh.length < 32) throw new NsisError("firstheader が途中で切れている");
    const hdrLen = fh.readInt32LE(20);
    const word = fh.readUInt32LE(28);
    const compressed = (word & 0x80000000) !== 0;
    const len = word & 0x7fffffff;
    if (len <= 0 || at + 32 + len > size) throw new NsisError(`圧縮ヘッダ長が不正 (${len})`);
    const body = readAt(fd, at + 32, len);
    if (!compressed) return body;
    let hdr;
    try {
      hdr = inflateRawSync(body);
    } catch (e) {
      throw new NsisError(`ヘッダが raw deflate ではない (LZMA / bzip2 / ソリッドは未対応): ${e.message}`);
    }
    if (hdr.length !== hdrLen) throw new NsisError(`展開後ヘッダ長 ${hdr.length} が firstheader の記載 ${hdrLen} と不一致`);
    return hdr;
  } finally {
    closeSync(fd);
  }
}

// 文字列表の全文字列 (空でないもの)
export function nsisStrings(hdr) {
  const blk = (i) => hdr.readInt32LE(4 + i * 8);
  const from = blk(NB_STRINGS);
  const to = blk(NB_LANGTABLES);
  if (!(from > 0 && from < to && to <= hdr.length)) throw new NsisError(`文字列表の範囲が不正 (${from}..${to}, header ${hdr.length})`);
  const bytes = hdr.subarray(from, to - ((to - from) % 2));
  return bytes.toString("utf16le").split("\0").filter((s) => s.length > 0);
}

// LicenseData の文字列は先頭 1 文字が RichEdit EM_STREAMIN の形式 (SF_TEXT=1 / SF_RTF=2、Unicode ビルドは |SF_UNICODE=0x10)。
// ライセンス文の候補 [{ fmt: "text" | "rtf", body }] を重複除いて返す (どれが規約かは呼び出し側が内容署名で選ぶ)
export function nsisLicenseCandidates(file, { minChars = 200 } = {}) {
  const seen = new Map();
  for (const s of nsisStrings(readNsisHeader(file))) {
    const code = s.charCodeAt(0) & 0x0f;
    const flagged = s.charCodeAt(0) === code || s.charCodeAt(0) === (code | 0x10);
    if (!flagged || (code !== 1 && code !== 2) || s.length - 1 < minChars) continue;
    seen.set(s, { fmt: code === 2 ? "rtf" : "text", body: s.slice(1) });
  }
  return [...seen.values()];
}
