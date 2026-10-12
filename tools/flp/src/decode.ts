// Typed (semantic) layer on top of the lossless container: decode every event to a typed value and encode it back.
// Typed round-trip (decode -> encode == original payload) is verified corpus-wide by cli/roundtrip.ts (level 1).
import { classOf, BYTE, WORD, DWORD, TEXT, type FlpEvent, type FlpFile } from './flp.ts';
import { defOf, eventName, type EventDef } from './events.ts';

export interface FlVersion {
  str: string;
  major: number;
  minor: number;
  patch: number;
  build: number;
  }

export function parseVersionString(s: string): FlVersion {
  const p = s.split('.').map((x) => parseInt(x, 10) || 0);
  return { str: s, major: p[0] ?? 0, minor: p[1] ?? 0, patch: p[2] ?? 0, build: p[3] ?? 0 };
}

function latin1(d: Uint8Array): string {
  let s = '';
  for (let i = 0; i < d.length; i++) s += String.fromCharCode(d[i]);
  return s;
}

export function flVersionOf(f: FlpFile): FlVersion {
  const e = f.events.find((x) => x.id === 199 && !x.ext);
  if (!e) return parseVersionString('');
  const s = latin1(e.data);
  return parseVersionString(s.replace(/\0[\s\S]*$/, ''));
}

/** UTF-16 text is used from FL 11.5; FlVersion/RTF stay ASCII; these ids were introduced after the switch and are always UTF-16 */
const ALWAYS_UTF16 = new Set([231, 239, 241, 253, 0xc0000100, 0xc0000101, 0xc0000102]);
export function textIsUtf16(def: EventDef | undefined, id: number, ver: FlVersion): boolean {
  if (def?.type === 'astr') return false;
  if (ALWAYS_UTF16.has(id)) return true;
  return ver.major > 11 || (ver.major === 11 && ver.minor >= 5);
}

export interface TextValue {
  text: string;
  /** hex of bytes after the first NUL terminator (normally empty) */
  tail?: string;
}

function hex(d: Uint8Array): string {
  let s = '';
  for (let i = 0; i < d.length; i++) s += d[i].toString(16).padStart(2, '0');
  return s;
}
function unhex(s: string): Uint8Array {
  const o = new Uint8Array(s.length >> 1);
  for (let i = 0; i < o.length; i++) o[i] = parseInt(s.substr(i * 2, 2), 16);
  return o;
}

export function decodeText(d: Uint8Array, utf16: boolean): TextValue {
  if (utf16 && d.length % 2 === 0) {
    let s = '';
    let i = 0;
    for (; i < d.length; i += 2) {
      const c = d[i] | (d[i + 1] << 8);
      if (c === 0) break;
      s += String.fromCharCode(c);
    }
    const tail = d.subarray(i);
    return tail.length ? { text: s, tail: hex(tail) } : { text: s };
  }
  const z = d.indexOf(0);
  const body = z < 0 ? d : d.subarray(0, z);
  const tail = z < 0 ? new Uint8Array(0) : d.subarray(z);
  const t: TextValue = { text: latin1(body) };
  if (tail.length) t.tail = hex(tail);
  return t;
}

export function encodeText(v: TextValue, utf16: boolean): Uint8Array {
  const tail = v.tail ? unhex(v.tail) : new Uint8Array(0);
  if (utf16) {
    const o = new Uint8Array(v.text.length * 2 + tail.length);
    for (let i = 0; i < v.text.length; i++) {
      const c = v.text.charCodeAt(i);
      o[2 * i] = c & 0xff;
      o[2 * i + 1] = c >> 8;
    }
    o.set(tail, v.text.length * 2);
    return o;
  }
  const o = new Uint8Array(v.text.length + tail.length);
  for (let i = 0; i < v.text.length; i++) o[i] = v.text.charCodeAt(i) & 0xff;
  o.set(tail, v.text.length);
  return o;
}

// ---- struct layouts ----
export type FT = 'u8' | 'i8' | 'u16' | 'i16' | 'u32' | 'i32' | 'f32' | 'f64';
const FW: Record<FT, number> = { u8: 1, i8: 1, u16: 2, i16: 2, u32: 4, i32: 4, f32: 4, f64: 8 };
export interface Layout {
  /** accepted payload sizes (record stride for rec events) */
  sizes: number[];
  fields: [name: string, off: number, type: FT][];
}
function words(n: number, prefix = 'w'): Layout['fields'] {
  return Array.from({ length: n }, (_, i) => [`${prefix}${i}`, i * 4, 'u32' as FT]);
}

const PLAYLIST_BASE: Layout['fields'] = [['position', 0, 'u32'], ['patternBase', 4, 'u16'], ['itemIndex', 6, 'u16'], ['length', 8, 'u32'], ['trackRvIdx', 12, 'u16'], ['group', 14, 'u16'], ['u1', 16, 'u16'], ['itemFlags', 18, 'u16'], ['u2', 20, 'u32'], ['startOffset', 24, 'f32'], ['endOffset', 28, 'f32']];

/**
 * Playlist item stride (PlaylistItems, id 233) grew with FL: 32B (<= FL 20.8) -> 60B (build 3031 .. FL 24.1) -> 80B (FL 24.2.99.4720+).
 * Measured on the corpus (cli/pl_stride in REPORT.md); the version rule is validated by divisibility and falls back to a field-sanity vote.
 */
export function playlistStride(d: Uint8Array, ver: FlVersion): number {
  // Engine rule (FlpLoad helper 0xf558e0): version < 20.99.1 -> 32B; else by event 169 flags: bit1 clear -> 60B, bit1 set & bit3 clear -> 80B.
  // Corpus: 169 = 0x5 (60B side) up to build 4701, 0x7 (80B side) from build 4720; builds 4702-4719 are unobserved, so 4720 is the first build
  // known to be 80B (the old 4700 guess is contradicted by 4701 = 0x5). The data vote below is authoritative when a payload is present.
  const pref = ver.build >= 4720 || ver.major >= 25 ? 80 : ver.build >= 3000 || ver.major >= 21 ? 60 : 32;
  if (d.length === 0) return pref;
  const dv = new DataView(d.buffer, d.byteOffset, d.byteLength);
  const score = (st: number): number => {
    if (d.length % st) return -1;
    const n = d.length / st;
    let ok = 0;
    for (let r = 0; r < n; r++) {
      const o = r * st;
      if (dv.getUint16(o + 4, true) <= 0x5000 && dv.getUint16(o + 12, true) <= 500) ok++;
    }
    return ok / n;
  };
  if (score(pref) >= 0.99) return pref;
  let best = pref;
  let bs = score(pref);
  for (const st of [32, 60, 80]) {
    const sc = score(st);
    if (sc > bs) {
      bs = sc;
      best = st;
    }
  }
  return best;
}

export function recordLayout(id: number, stride: number): Layout {
  if (id === 233 && stride !== 32) {
    const extra: Layout['fields'] = [];
    for (let o = 32; o + 4 <= stride; o += 4) extra.push([`x${o}`, o, 'u32']);
    return { sizes: [stride], fields: [...PLAYLIST_BASE, ...extra] };
  }
  return LAYOUTS[id];
}

export const LAYOUTS: Record<number, Layout> = {
  224: {
    sizes: [24],
    fields: [['position', 0, 'u32'], ['flags', 4, 'u16'], ['rackChannel', 6, 'u16'], ['length', 8, 'u32'], ['key', 12, 'u16'], ['group', 14, 'u16'], ['finePitch', 16, 'i8'], ['u1', 17, 'u8'], ['release', 18, 'u8'], ['midiChannel', 19, 'u8'], ['pan', 20, 'u8'], ['velocity', 21, 'u8'], ['modX', 22, 'u8'], ['modY', 23, 'u8']],
  },
  233: { sizes: [32], fields: PLAYLIST_BASE },
  225: { sizes: [12], fields: [['a', 0, 'u8'], ['paramId', 1, 'u8'], ['b', 2, 'u16'], ['target', 4, 'u16'], ['c', 6, 'u16'], ['value', 8, 'i32']] },
  223: { sizes: [12], fields: words(3) },
  237: { sizes: [16], fields: [['created', 0, 'f64'], ['daysSpent', 8, 'f64']] },
  238: {
    sizes: [47, 49, 61, 62, 66, 70],
    fields: [['index', 0, 'u32'], ['color', 4, 'u32'], ['icon', 8, 'u32'], ['enabled', 12, 'u8'], ['height', 13, 'f32'], ['lockedHeight', 17, 'f32'], ['contentLocked', 21, 'u8'], ['motion', 22, 'u32'], ['press', 26, 'u32'], ['triggerSync', 30, 'u32'], ['queued', 34, 'u32'], ['tolerant', 38, 'u32'], ['positionSync', 42, 'u32'], ['grouped', 46, 'u8']],
  },
  212: { sizes: [52], fields: [['flags', 16, 'u16'], ['page', 20, 'u8'], ['width', 44, 'u32'], ['height', 48, 'u32']] },
  236: { sizes: [12], fields: [['a', 0, 'u32'], ['flags', 4, 'u32'], ['b', 8, 'u32']] },
  209: { sizes: [20], fields: words(5) },
  219: { sizes: [24], fields: [['pan', 0, 'u32'], ['volume', 4, 'u32'], ['pitchShift', 8, 'i32'], ['filterModX', 12, 'u32'], ['filterModY', 16, 'u32'], ['u1', 20, 'u32']] },
  221: { sizes: [9], fields: [['maxVoices', 0, 'u32'], ['slideLength', 4, 'u32'], ['flags', 8, 'u8']] },
  228: { sizes: [16], fields: words(4) },
  229: { sizes: [20], fields: words(5) },
  226: { sizes: [20], fields: words(5) },
  227: { sizes: [20], fields: words(5) },
  217: { sizes: [8], fields: words(2) },
  242: { sizes: [28], fields: words(7) },
  243: { sizes: [8], fields: words(2) },
};

export interface StructValue {
  len: number;
  fields: Record<string, number>;
  /** hex of the payload with the named fields zeroed (omitted when all-zero) */
  rest?: string;
}

function readField(dv: DataView, off: number, t: FT): number {
  switch (t) {
    case 'u8':
      return dv.getUint8(off);
    case 'i8':
      return dv.getInt8(off);
    case 'u16':
      return dv.getUint16(off, true);
    case 'i16':
      return dv.getInt16(off, true);
    case 'u32':
      return dv.getUint32(off, true);
    case 'i32':
      return dv.getInt32(off, true);
    case 'f32':
      return dv.getFloat32(off, true);
    case 'f64':
      return dv.getFloat64(off, true);
  }
}
function writeField(dv: DataView, off: number, t: FT, v: number): void {
  switch (t) {
    case 'u8':
      return dv.setUint8(off, v);
    case 'i8':
      return dv.setInt8(off, v);
    case 'u16':
      return dv.setUint16(off, v, true);
    case 'i16':
      return dv.setInt16(off, v, true);
    case 'u32':
      return dv.setUint32(off, v, true);
    case 'i32':
      return dv.setInt32(off, v, true);
    case 'f32':
      return dv.setFloat32(off, v, true);
    case 'f64':
      return dv.setFloat64(off, v, true);
  }
}

export function decodeStruct(d: Uint8Array, lay: Layout): StructValue {
  const dv = new DataView(d.buffer, d.byteOffset, d.byteLength);
  const fields: Record<string, number> = {};
  const rest = new Uint8Array(d);
  for (const [name, off, t] of lay.fields) {
    if (off + FW[t] > d.length) continue;
    fields[name] = readField(dv, off, t);
    rest.fill(0, off, off + FW[t]);
  }
  const v: StructValue = { len: d.length, fields };
  if (rest.some((x) => x)) v.rest = hex(rest);
  return v;
}
export function encodeStruct(v: StructValue, lay: Layout): Uint8Array {
  const out = v.rest ? unhex(v.rest) : new Uint8Array(v.len);
  const dv = new DataView(out.buffer);
  for (const [name, off, t] of lay.fields) {
    if (off + FW[t] > out.length || !(name in v.fields)) continue;
    writeField(dv, off, t, v.fields[name]);
  }
  return out;
}

// ---- typed events ----
export type TypedValue =
  | { k: 'int'; v: number }
  | { k: 'text'; v: TextValue; utf16: boolean }
  | { k: 'struct'; v: StructValue }
  | { k: 'records'; v: StructValue[]; stride: number }
  | { k: 'blob'; v: string };

export interface TypedEvent {
  id: number;
  ext?: boolean;
  name: string;
  value: TypedValue;
}

function intSigned(def: EventDef | undefined): boolean {
  return def?.type === 'i8' || def?.type === 'i16' || def?.type === 'i32';
}

export function decodeEvent(e: FlpEvent, ver: FlVersion): TypedEvent {
  const def = defOf(e.id);
  const base = { id: e.id, ...(e.ext ? { ext: true } : {}), name: eventName(e.id) };
  const cls = classOf(e);
  const d = e.data;
  if (cls === BYTE || cls === WORD || cls === DWORD) {
    const dv = new DataView(d.buffer, d.byteOffset, d.byteLength);
    const sg = intSigned(def);
    const v = cls === BYTE ? (sg ? dv.getInt8(0) : dv.getUint8(0)) : cls === WORD ? (sg ? dv.getInt16(0, true) : dv.getUint16(0, true)) : sg ? dv.getInt32(0, true) : dv.getUint32(0, true);
    return { ...base, value: { k: 'int', v } };
  }
  if (cls === TEXT) {
    if (def && (def.type === 'wstr' || def.type === 'astr')) {
      const u16 = textIsUtf16(def, e.id, ver);
      return { ...base, value: { k: 'text', v: decodeText(d, u16), utf16: u16 && d.length % 2 === 0 } };
    }
    const lay = LAYOUTS[e.id];
    if (lay) {
      if (def?.type === 'rec' && !e.ext) {
        const stride = e.id === 233 ? playlistStride(d, ver) : lay.sizes[0];
        if (stride > 0 && d.length % stride === 0) {
          const rl = recordLayout(e.id, stride);
          const recs: StructValue[] = [];
          for (let o = 0; o < d.length; o += stride) recs.push(decodeStruct(d.subarray(o, o + stride), rl));
          return { ...base, value: { k: 'records', v: recs, stride } };
        }
      }
      if (lay.sizes.includes(d.length)) return { ...base, value: { k: 'struct', v: decodeStruct(d, lay) } };
    }
  }
  return { ...base, value: { k: 'blob', v: hex(d) } };
}

export function encodeEventData(t: TypedEvent): Uint8Array {
  const val = t.value;
  switch (val.k) {
    case 'int': {
      const cls = classOf(t);
      const n = cls === BYTE ? 1 : cls === WORD ? 2 : 4;
      const o = new Uint8Array(n);
      const dv = new DataView(o.buffer);
      if (n === 1) dv.setUint8(0, val.v & 0xff);
      else if (n === 2) dv.setUint16(0, val.v & 0xffff, true);
      else dv.setUint32(0, val.v >>> 0, true);
      return o;
    }
    case 'text':
      return encodeText(val.v, val.utf16);
    case 'struct':
      return encodeStruct(val.v, LAYOUTS[t.id]);
    case 'records': {
      const rl = recordLayout(t.id, val.stride);
      const parts = val.v.map((r) => encodeStruct(r, rl));
      const o = new Uint8Array(parts.reduce((a, b) => a + b.length, 0));
      let p = 0;
      for (const b of parts) {
        o.set(b, p);
        p += b.length;
      }
      return o;
    }
    case 'blob':
      return unhex(val.v);
  }
}

export interface TypedMismatch {
  index: number;
  id: number;
  name: string;
}

/** Level-1 round trip: every event -> typed -> bytes must equal the original payload. */
export function typedRoundTrip(f: FlpFile): { events: number; mismatches: TypedMismatch[]; typed: Record<string, number> } {
  const ver = flVersionOf(f);
  const mismatches: TypedMismatch[] = [];
  const typed: Record<string, number> = {};
  f.events.forEach((e, i) => {
    const t = decodeEvent(e, ver);
    typed[t.value.k] = (typed[t.value.k] ?? 0) + 1;
    const back = encodeEventData(t);
    let ok = back.length === e.data.length;
    if (ok) for (let k = 0; k < back.length; k++) if (back[k] !== e.data[k]) { ok = false; break; }
    if (!ok) mismatches.push({ index: i, id: e.id, name: t.name });
  });
  return { events: f.events.length, mismatches, typed };
}

export { hex, unhex, latin1 };
