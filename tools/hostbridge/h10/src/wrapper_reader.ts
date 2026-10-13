// Reader model of Fruity Wrapper_x64.dll's plugin-state loader (event 213 / .fst "wrapper chunk").
// Source of truth: fw:0x870da0 (SaveRestoreState load: version gate) → fw:0x875af0 (record loop, version >= 5)
// with the stream helpers fw:0x74a8e0 / 0x74a970 / 0x74aa40 / 0x74abd0 (decompile in ../evidence/, byte-level checks in ../analysis/h10_check.py).
// Browser-safe (Uint8Array only, no node: imports).

/** newest wrapper-chunk version the Wrapper accepts (fw:0x870f6d `cmp ver,0xc; jle`); its own writer always emits 12 (fw:0x870e97). */
export const MAX_VERSION = 12;

export type ReadStatus = 'ok' | 'rejected-newer-version' | 'ignored-minus1' | 'legacy-reader' | 'too-short';

export interface RecordInfo {
  id: number;
  size: number;
  /** offset of the payload inside the chunk */
  offset: number;
  /** id is handled by the reader loop (fw:0x875af0); others are skipped without being read */
  known: boolean;
}

/** ids the record loop dispatches on (asm-derived table in analysis/h10_check.py EXPECT) */
export const KNOWN_IDS = [0x01, 0x02, 0x1e, 0x1f, 0x20, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a] as const;

export interface WrapperFields {
  /** record 1 (0x14 B): MIDI in/out port, pitch-bend range … (absent → port −1/−1, fw:0x8744b0) */
  midi?: Uint8Array;
  /** record 2 (0x19 B, zero-filled when shorter); absent → u32@9 = 0x7900 (fw:0x8744d0 with param 0) */
  record2: Uint8Array;
  /** record 30: read but never used after the loop */
  io30?: Uint8Array;
  /** records 31 / 32: input / output routing, 12-byte entries; absent → 0 entries → plugin default routing */
  inputs: Uint8Array;
  outputs: Uint8Array;
  /** record 50 u32; absent → 0 (= VST2 effect!) because the buffer is zero-filled */
  plugclass: number;
  plugclassPresent: boolean;
  /** record 51 (VST2 uniqueID, u32) */
  magic: number;
  /** record 52 (16 B) */
  cid: Uint8Array;
  /** record 53 (plugin state) */
  state?: Uint8Array;
  /** records 54 / 55 / 56 / 58 */
  name?: string;
  path?: string;
  vendor?: string;
  clapId?: string;
  /** record 57 u32 — written from TVSTPlugin+0x9c4 = dispatcher(effGetVstVersion=58); default 1 when absent. NOT an entry-point hint. */
  vstVersion: number;
}

export interface WrapperRead {
  status: ReadStatus;
  version: number;
  records: RecordInfo[];
  fields: WrapperFields;
  /** record loop ended exactly at the end of the chunk */
  consumedAll: boolean;
  /** strings are decoded as UTF-8 when version >= 9, ANSI (latin1 model) otherwise (fw:0x875d1f `cmp ecx,9`) */
  stringEncoding: 'ansi' | 'utf8';
}

function emptyFields(): WrapperFields {
  const record2 = new Uint8Array(0x19);
  new DataView(record2.buffer).setUint32(9, 0x7900, true);
  return { record2, inputs: new Uint8Array(0), outputs: new Uint8Array(0), plugclass: 0, plugclassPresent: false, magic: 0, cid: new Uint8Array(16), vstVersion: 1 };
}

/** FUN_0074a970: zero-fill N bytes, then copy min(size, N) bytes of the record */
function fixed(payload: Uint8Array, n: number): Uint8Array {
  const out = new Uint8Array(n);
  out.set(payload.subarray(0, Math.min(n, payload.length)));
  return out;
}

function decode(payload: Uint8Array, enc: 'ansi' | 'utf8'): string {
  return new TextDecoder(enc === 'utf8' ? 'utf-8' : 'latin1').decode(payload);
}

export function readWrapperChunk(buf: Uint8Array): WrapperRead {
  const fields = emptyFields();
  const out: WrapperRead = { status: 'too-short', version: 0, records: [], fields, consumedAll: false, stringEncoding: 'ansi' };
  if (buf.length < 4) return out;
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const version = dv.getInt32(0, true);
  out.version = version;
  if (version > MAX_VERSION) { out.status = 'rejected-newer-version'; return out; }
  if (version === -1) { out.status = 'ignored-minus1'; return out; }
  if (version < 5) { out.status = 'legacy-reader'; return out; }
  out.status = 'ok';
  const enc: 'ansi' | 'utf8' = version > 8 ? 'utf8' : 'ansi';
  out.stringEncoding = enc;
  let pos = 4;
  const header = (p: number): { id: number; size: number } | undefined =>
    p + 12 <= buf.length ? { id: dv.getUint32(p, true), size: Number(dv.getBigUint64(p + 4, true)) } : undefined;
  while (pos < buf.length) {
    let h = header(pos);
    if (!h) break; // truncated header: the stream helper reads garbage/zero here; the model stops
    pos += 12;
    const seekTo = pos + h.size; // fw:0x74abd0 seeks to (first header's pos + first header's size)
    if (h.id === 0) { // fw:0x74a8e0 re-reads one more header when id == 0
      const h2 = header(pos);
      if (!h2) break;
      pos += 12;
      h = h2;
    }
    const payload = buf.subarray(pos, Math.min(buf.length, pos + h.size));
    const known = (KNOWN_IDS as readonly number[]).includes(h.id);
    out.records.push({ id: h.id, size: h.size, offset: pos, known });
    switch (h.id) {
      case 0x01: fields.midi = fixed(payload, 0x14); break;
      case 0x02: fields.record2 = fixed(payload, 0x19); break;
      case 0x1e: fields.io30 = fixed(payload, 0x10); break;
      case 0x1f: fields.inputs = fixed(payload, Math.floor(h.size / 12) * 12); break;
      case 0x20: fields.outputs = fixed(payload, Math.floor(h.size / 12) * 12); break;
      case 0x32: fields.plugclass = new DataView(fixed(payload, 0x10).buffer).getUint32(0, true); fields.plugclassPresent = true; break;
      case 0x33: fields.magic = new DataView(fixed(payload, 4).buffer).getUint32(0, true); break;
      case 0x34: fields.cid = fixed(payload, 0x10); break;
      case 0x35: fields.state = payload.slice(); break;
      case 0x36: fields.name = decode(payload, enc); break;
      case 0x37: fields.path = decode(payload, enc).replace(/\//g, '\\'); break; // fw:0x8760bd StringReplace('/' → '\')
      case 0x38: fields.vendor = decode(payload, enc); break;
      case 0x39: fields.vstVersion = new DataView(fixed(payload, 4).buffer).getUint32(0, true); break;
      case 0x3a: fields.clapId = decode(payload, enc); break;
      default: break; // unknown id: skipped
    }
    pos = seekTo;
  }
  out.consumedAll = pos === buf.length;
  return out;
}

export interface Record2Flags {
  flags: number;
  /** 0x400000: per-option bits are NOT applied (the plugin keeps its default options) — FL's DB writer always sets it (0x407908) */
  useDefaultOptions: boolean;
  /** 0x400: saved for 64-bit only */
  only64: boolean;
  /** 0x100000: the bitness bit is meaningful (a single architecture was recorded) */
  singleArch: boolean;
  /** fw:0x876565: singleArch && (only64 != hostIs64) → the plugin would need the other-bitness bridge */
  bitnessMismatch: boolean;
}

export function interpretRecord2(record2: Uint8Array, hostIs64 = true): Record2Flags {
  const flags = new DataView(record2.buffer, record2.byteOffset, record2.byteLength).getUint32(9, true);
  const only64 = (flags & 0x400) !== 0;
  const singleArch = (flags & 0x100000) !== 0;
  return { flags, useDefaultOptions: (flags & 0x400000) !== 0, only64, singleArch, bitnessMismatch: singleArch && only64 !== hostIs64 };
}

const EXT: Record<number, string> = { 0: '.dll', 1: '.dll', 2: '.dll', 3: '.dll', 4: '.dll', 5: '.dll', 7: '.vst3', 8: '.vst3', 9: '.component', 10: '.component', 11: '.clap', 12: '.clap' };

function guidText(g: Uint8Array): string {
  const h = (a: number, b: number, rev: boolean): string => Array.from(g.subarray(a, b)).map((x) => x.toString(16).padStart(2, '0')).reduce<string[]>((acc, x) => (rev ? [x, ...acc] : [...acc, x]), []).join('').toUpperCase();
  return `{${h(0, 4, true)}-${h(4, 6, true)}-${h(6, 8, true)}-${h(8, 10, false)}-${h(10, 16, false)}}`;
}

/** The query the Wrapper sends to the FL host (message 7) to locate the plugin file: fw:0x871fe0 + fw:0x79e540 */
export function hostQuery(f: WrapperFields): string {
  const cls = f.plugclass;
  let q = f.path ?? ((f.name ?? '') + (EXT[cls] ?? ''));
  q += `|class=${cls}`;
  if (f.name) q += `|name=${f.name}`;
  if (f.magic !== 0) q += `|vstid=${f.magic | 0}`;
  if (f.cid.some((b) => b !== 0)) q += `|guid=${guidText(f.cid)}`;
  if (f.clapId) q += `|id=${f.clapId}`;
  return q;
}
