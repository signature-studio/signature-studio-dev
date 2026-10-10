// FLP / FST / FSC container layer: lossless parse + write.
// Layout: "FLhd" u32 hdrLen(=6) { u16 format, u16 nChannels, u16 ppq } "FLdt" u32 dtLen { event* }
// Event: u8 id; id<64 => 1B, <128 => 2B LE, <192 => 4B LE, >=192 => varint(7bit LSB-first, MSB=continue) len + payload.
// Extended event (FL 25.2+; verified against FLEngine_x64.dll writer 0xa9ec60 / reader 0xa9e7a0):
//   id byte 0xAC, then u32 LE extended id; the payload framing is chosen by (extId & 0xF0000000):
//   0x00000000 => 1B, 0x40000000 => 2B, 0x80000000 => 4B, 0xC0000000 => varint len + payload, other => no payload.
// Browser-safe: Uint8Array/DataView only (no Node APIs).

export const BYTE = 0;
export const WORD = 64;
export const DWORD = 128;
export const TEXT = 192;
export const DATA = 208;
/** escape byte that introduces a 32-bit extended event id */
export const EXT_ESCAPE = 0xac;

export type EventKind = 'byte' | 'word' | 'dword' | 'text' | 'data';

export function kindOf(id: number): EventKind {
  if (id < WORD) return 'byte';
  if (id < DWORD) return 'word';
  if (id < TEXT) return 'dword';
  if (id < DATA) return 'text';
  return 'data';
}

export interface FlpEvent {
  /** event id: 0..255 for ordinary events, the full u32 id (e.g. 0xC0000101) when ext === true */
  id: number;
  /** extended-id event (on-disk: 0xAC + u32 id) */
  ext?: boolean;
  /** payload (BYTE/WORD/DWORD: raw LE bytes; TEXT/DATA: payload without length prefix). Subarray of the source buffer when parsed. */
  data: Uint8Array;
  /** byte offset of the first byte of the event inside the source file (parse only; ignored by writer) */
  off: number;
  /** Non-canonical varint length bytes (only set when the on-disk encoding differs from the minimal encoding). */
  lenEnc?: Uint8Array;
}

export interface FlpHeader {
  /** declared FLhd length (normally 6) */
  hdrLen: number;
  format: number;
  nChannels: number;
  ppq: number;
  /** bytes of the FLhd body beyond the 6 standard bytes (only when hdrLen > 6) */
  hdrExtra: Uint8Array;
}

export interface FlpFile {
  header: FlpHeader;
  /** declared FLdt length */
  dtLen: number;
  events: FlpEvent[];
  /** bytes after the last well-formed event inside the declared FLdt range (usually empty) */
  dtSlack: Uint8Array;
  /** bytes after the FLdt block (usually empty) */
  trailer: Uint8Array;
  /** non-fatal parse notes (e.g. dtLen mismatch) */
  warnings: string[];
}

export class FlpParseError extends Error {}

const MAGIC_FLHD = 0x64684c46; // "FLhd" LE
const MAGIC_FLDT = 0x74644c46; // "FLdt" LE
const NO_PAYLOAD = -1;

/** payload class of an extended id, expressed as an ordinary-id class value (0 byte / 64 word / 128 dword / 192 varlen / -1 none) */
export function classOfExt(id: number): number {
  switch ((id & 0xf0000000) >>> 0) {
    case 0x00000000:
      return BYTE;
    case 0x40000000:
      return WORD;
    case 0x80000000:
      return DWORD;
    case 0xc0000000:
      return TEXT;
    default:
      return NO_PAYLOAD;
  }
}

/** payload class (BYTE/WORD/DWORD/TEXT, or -1) of an event */
export function classOf(e: { id: number; ext?: boolean }): number {
  return e.ext ? classOfExt(e.id) : e.id < WORD ? BYTE : e.id < DWORD ? WORD : e.id < TEXT ? DWORD : TEXT;
}

export function encodeVarint(n: number): Uint8Array {
  const out: number[] = [];
  do {
    let b = n & 0x7f;
    n = Math.floor(n / 128);
    if (n > 0) b |= 0x80;
    out.push(b);
  } while (n > 0);
  return Uint8Array.from(out);
}

export function parseFlp(buf: Uint8Array): FlpFile {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const warnings: string[] = [];
  if (buf.length < 14 || dv.getUint32(0, true) !== MAGIC_FLHD) throw new FlpParseError('not an FLhd file');
  const hdrLen = dv.getUint32(4, true);
  if (hdrLen < 6 || 8 + hdrLen + 8 > buf.length) throw new FlpParseError(`bad FLhd length ${hdrLen}`);
  const header: FlpHeader = {
    hdrLen,
    format: dv.getUint16(8, true),
    nChannels: dv.getUint16(10, true),
    ppq: dv.getUint16(12, true),
    hdrExtra: buf.subarray(14, 8 + hdrLen),
  };
  let p = 8 + hdrLen;
  if (dv.getUint32(p, true) !== MAGIC_FLDT) throw new FlpParseError(`missing FLdt at ${p}`);
  const dtLen = dv.getUint32(p + 4, true);
  p += 8;
  let end = p + dtLen;
  if (end > buf.length) {
    warnings.push(`FLdt length ${dtLen} exceeds file (${buf.length - p} available)`);
    end = buf.length;
  }
  const events: FlpEvent[] = [];
  let slackStart = -1;
  while (p < end) {
    const off = p;
    let id = buf[p++];
    let ext = false;
    if (id === EXT_ESCAPE) {
      if (p + 4 > end) {
        slackStart = off;
        break;
      }
      id = dv.getUint32(p, true);
      p += 4;
      ext = true;
    }
    const cls = ext ? classOfExt(id) : id < WORD ? BYTE : id < DWORD ? WORD : id < TEXT ? DWORD : TEXT;
    let len: number;
    let lenEnc: Uint8Array | undefined;
    if (cls === NO_PAYLOAD) {
      len = 0;
      warnings.push(`extended id 0x${id.toString(16)} at ${off} has no known payload class (payload length 0, as FL)`);
    } else if (cls === BYTE) {
      len = 1;
    } else if (cls === WORD) {
      len = 2;
    } else if (cls === DWORD) {
      len = 4;
    } else {
      const ls = p;
      len = 0;
      let shift = 1;
      let ok = false;
      while (p < end) {
        const b = buf[p++];
        len += (b & 0x7f) * shift;
        shift *= 128;
        if (!(b & 0x80)) {
          ok = true;
          break;
        }
        if (shift > 2 ** 35) break;
      }
      if (!ok) {
        slackStart = off;
        break;
      }
      const raw = buf.subarray(ls, p);
      if (raw.length !== encodeVarint(len).length) lenEnc = raw;
    }
    if (p + len > end) {
      slackStart = off;
      break;
    }
    const ev: FlpEvent = { id, data: buf.subarray(p, p + len), off };
    if (ext) ev.ext = true;
    if (lenEnc) ev.lenEnc = lenEnc;
    events.push(ev);
    p += len;
  }
  let dtSlack: Uint8Array = new Uint8Array(0);
  if (slackStart >= 0) {
    dtSlack = buf.subarray(slackStart, end);
    warnings.push(`malformed event at ${slackStart}; ${end - slackStart}B kept as dtSlack`);
  }
  const trailer = buf.subarray(end);
  if (trailer.length) warnings.push(`${trailer.length}B after FLdt`);
  return { header, dtLen, events, dtSlack, trailer, warnings };
}

function eventSize(e: FlpEvent): number {
  const head = e.ext ? 5 : 1;
  const varlen = classOf(e) === TEXT ? (e.lenEnc ?? encodeVarint(e.data.length)).length : 0;
  return head + varlen + e.data.length;
}

export function writeFlp(f: FlpFile): Uint8Array {
  let body = 0;
  for (const e of f.events) body += eventSize(e);
  body += f.dtSlack.length;
  const hdrLen = 6 + f.header.hdrExtra.length;
  const total = 8 + hdrLen + 8 + body + f.trailer.length;
  const out = new Uint8Array(total);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, MAGIC_FLHD, true);
  dv.setUint32(4, hdrLen, true);
  dv.setUint16(8, f.header.format, true);
  dv.setUint16(10, f.header.nChannels, true);
  dv.setUint16(12, f.header.ppq, true);
  out.set(f.header.hdrExtra, 14);
  let p = 8 + hdrLen;
  dv.setUint32(p, MAGIC_FLDT, true);
  // a declared length larger than the data (truncated file) is preserved; otherwise it is recomputed.
  const declared = f.dtLen > body && f.trailer.length === 0 ? f.dtLen : body;
  dv.setUint32(p + 4, declared, true);
  p += 8;
  for (const e of f.events) {
    if (e.ext) {
      out[p++] = EXT_ESCAPE;
      dv.setUint32(p, e.id, true);
      p += 4;
    } else {
      out[p++] = e.id;
    }
    if (classOf(e) === TEXT) {
      const le = e.lenEnc ?? encodeVarint(e.data.length);
      out.set(le, p);
      p += le.length;
    }
    out.set(e.data, p);
    p += e.data.length;
  }
  out.set(f.dtSlack, p);
  p += f.dtSlack.length;
  out.set(f.trailer, p);
  return out;
}

export function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  return firstDiff(a, b) < 0;
}

/** index of first differing byte, or -1 when identical */
export function firstDiff(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) return i;
  return a.length === b.length ? -1 : n;
}

export function isFlpMagic(buf: Uint8Array): boolean {
  return buf.length >= 4 && buf[0] === 0x46 && buf[1] === 0x4c && buf[2] === 0x68 && buf[3] === 0x64;
}
