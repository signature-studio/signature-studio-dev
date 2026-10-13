// Native Fruity plugin state (FLP event 213) decoders — L-3 (#104).
// Layouts are transcribed from each plugin DLL's SaveRestoreState (vtable slot 3): the order of Stream->Write
// calls in the Save branch and the `version >= N` gates in the Load branch (see REPORT_APPENDIX.md §12).
// Lossless: encodePluginState(decodePluginState(x)) == x for every input; anything not described by the layout
// (unknown version, short/long payload) is kept in `tail` and `ok` is false when the layout did not fit exactly.
// Browser-safe: no node: imports.

export type FieldKind = 'u32' | 'i32' | 'u8' | 'i32[]';

export interface FieldSpec {
  name: string;
  kind: FieldKind;
  /** element count for 'i32[]' */
  count?: number;
  /** field present when version >= minVer (default: always) */
  minVer?: number;
  /** field present when version <= maxVer (default: always) */
  maxVer?: number;
  /** plugin object offset the DLL reads/writes (documentation only) */
  at?: number;
}

export interface PluginLayout {
  /** FP internal name (event 201) */
  plugin: string;
  /** maps the leading u32 to a comparable version number (Maximus keeps it in the high word) */
  version: (raw: number) => number;
  /** versions the Load branch accepts (others are reported ok=false) */
  accepts: (v: number) => boolean;
  fields: FieldSpec[];
}

const i32s = (name: string, count: number, at?: number, o: Partial<FieldSpec> = {}): FieldSpec => ({ name, kind: 'i32[]', count, at, ...o });
const i32 = (name: string, at?: number, o: Partial<FieldSpec> = {}): FieldSpec => ({ name, kind: 'i32', at, ...o });
const u32 = (name: string, at?: number, o: Partial<FieldSpec> = {}): FieldSpec => ({ name, kind: 'u32', at, ...o });
const u8 = (name: string, at?: number, o: Partial<FieldSpec> = {}): FieldSpec => ({ name, kind: 'u8', at, ...o });
const ident = (r: number) => r;

export const LAYOUTS: Record<string, PluginLayout> = {
  // 6e8da0: Write(version=1), Write(this+0x180, 0x68); Load accepts version <= 1
  'Fruity Delay 3': {
    plugin: 'Fruity Delay 3', version: ident, accepts: (v) => v <= 1,
    fields: [i32s('params', 26, 0x180)],
  },
  // 6d4920: version 0x2711 = 10001. body 0x120..0x153 (13 x i32), 0x154/0x158 only at 10001 (default 0x2ac / 0 otherwise), flags 0x15c/0x15d
  'Fruity Reeverb 2': {
    plugin: 'Fruity Reeverb 2', version: ident, accepts: (v) => v === 10000 || v === 10001,
    fields: [
      i32s('params', 13, 0x120),
      u32('param13', 0x154, { minVer: 10001 }),
      u32('param14', 0x158, { minVer: 10001 }),
      u8('flag15c', 0x15c), u8('flag15d', 0x15d),
    ],
  },
  // 6d3760: Write(version=7), Write(this+0x120, 0xa4), Write(flags: bit0 = [this+0x277]); v<6 body is 7 bytes shorter, v<7 has no flags byte
  'Fruity Limiter': {
    plugin: 'Fruity Limiter', version: ident, accepts: (v) => v >= 6 && v <= 7,
    fields: [i32s('params', 41, 0x120), u8('flags', 0x277, { minVer: 7 })],
  },
  // 6ec340: Write order of the Save branch; gates are the `cmp [version], N` of the Load branch (6ec741..6ec972)
  'Fruity Parametric EQ 2': {
    plugin: 'Fruity Parametric EQ 2', version: ident, accepts: (v) => v >= 3 && v <= 8,
    fields: [
      i32s('params', 72, 0x120),
      u32('bits360', 0x360),
      u32('v364', 0x364),
      u8('v368', 0x368),
      i32('hostValue'),
      u32('v2078', 0x2078),
      u32('v36c', 0x36c, { minVer: 4 }),
      u32('v374', 0x374, { minVer: 4 }),
      u8('flagsA', undefined, { minVer: 4 }),
      u32('bitsB', undefined, { minVer: 4 }),
      u32('v212c', 0x212c, { minVer: 4 }),
      u32('v20ec', 0x20ec, { minVer: 5 }),
      u32('v2100', 0x2100, { minVer: 6 }),
      u32('v2104', 0x2104, { minVer: 6 }),
      u32('v2108', 0x2108, { minVer: 6 }),
      u32('v20fc', 0x20fc, { minVer: 6 }),
      u32('v2110', 0x2110, { minVer: 6 }),
      u32('v380', 0x380, { minVer: 7 }),
    ],
  },
  // 83f8f0 (Maximus): leading u32 = version<<16 | 3; version = high word (Load: `and 0xffff0000; shr 16`).
  // Body 0x12c..0x325 = 126 x i32 + 2 bytes (506 B at v>=7), then 0x328/0x330/flags/0x810.. (v>=14; 33 B), then 4 x 2 band
  // sub-streams (each saved by the sub-object's own vtable+0x10; length grows by 24 B per version step seen) -> raw tail.
  Maximus: {
    plugin: 'Maximus', version: (r) => (r >= 0x10000 ? r >>> 16 : r), accepts: (v) => v >= 7 && v <= 15,
    fields: [
      i32s('params', 126, 0x12c),
      u8('flag324', 0x324), u8('flag325', 0x325),
      u32('v328', 0x328, { minVer: 14 }), u32('v330', 0x330, { minVer: 14 }), u8('flags', undefined, { minVer: 14 }),
      u32('v810', 0x810, { minVer: 14 }), u32('v814', 0x814, { minVer: 14 }), u32('v818', 0x818, { minVer: 14 }),
      u32('v80c', 0x80c, { minVer: 14 }), u32('v820', 0x820, { minVer: 14 }), u32('v858', 0x858, { minVer: 14 }),
    ],
  },
};

export type FieldValue = number | number[];
export interface DecodedField { name: string; kind: FieldKind; off: number; size: number; at?: number; value: FieldValue }
export interface DecodedPluginState {
  plugin: string;
  /** payload shorter than 4 bytes: no version word was stored; all bytes are in `tail` and encode writes no header */
  headerless: boolean;
  /** raw leading u32 as stored (0 when headerless) */
  versionRaw: number;
  version: number;
  fields: DecodedField[];
  /** bytes after the described fields (Maximus band sub-streams; anything unknown) */
  tail: Uint8Array;
  /** true iff the version is accepted and every applicable field fit inside the payload */
  ok: boolean;
  /** payload length the layout predicts for this version (fields only); tail excluded */
  fieldsBytes: number;
}

const sizeOf = (f: FieldSpec): number => (f.kind === 'u8' ? 1 : f.kind === 'i32[]' ? 4 * (f.count ?? 0) : 4);
const applies = (f: FieldSpec, v: number): boolean => (f.minVer === undefined || v >= f.minVer) && (f.maxVer === undefined || v <= f.maxVer);

/** true iff the layout in this file covers the stored version (otherwise the payload is a legacy format kept raw). */
export function versionSupported(plugin: string, versionRaw: number): boolean {
  if (!hasLayout(plugin)) return false;
  const L = LAYOUTS[plugin];
  return L.accepts(L.version(versionRaw));
}

export function hasLayout(plugin: string): boolean {
  return Object.prototype.hasOwnProperty.call(LAYOUTS, plugin);
}

export function decodePluginState(plugin: string, data: Uint8Array): DecodedPluginState | undefined {
  if (!hasLayout(plugin)) return undefined;
  const L = LAYOUTS[plugin];
  const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
  if (data.length < 4) return { plugin, headerless: true, versionRaw: 0, version: 0, fields: [], tail: data.slice(), ok: false, fieldsBytes: 0 };
  const versionRaw = dv.getUint32(0, true);
  const version = L.version(versionRaw);
  const fields: DecodedField[] = [];
  let off = 4;
  let fit = L.accepts(version);
  for (const f of L.fields) {
    if (!applies(f, version)) continue;
    const size = sizeOf(f);
    if (off + size > data.length) { fit = false; break; }
    let value: FieldValue;
    if (f.kind === 'u8') value = data[off];
    else if (f.kind === 'u32') value = dv.getUint32(off, true);
    else if (f.kind === 'i32') value = dv.getInt32(off, true);
    else { const a: number[] = []; for (let i = 0; i < (f.count ?? 0); i++) a.push(dv.getInt32(off + 4 * i, true)); value = a; }
    fields.push({ name: f.name, kind: f.kind, off, size, at: f.at, value });
    off += size;
  }
  const fieldsBytes = off;
  const tail = data.slice(off);
  // fixed-size plugins must have no tail; Maximus is the only one with a variable sub-stream tail
  if (plugin !== 'Maximus' && tail.length !== 0) fit = false;
  return { plugin, headerless: false, versionRaw, version, fields, tail, ok: fit, fieldsBytes };
}

export function encodePluginState(s: DecodedPluginState): Uint8Array {
  if (s.headerless) return s.tail.slice();
  const total = 4 + s.fields.reduce((a, f) => a + f.size, 0) + s.tail.length;
  const out = new Uint8Array(total);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, s.versionRaw, true);
  for (const f of s.fields) {
    if (f.kind === 'u8') out[f.off] = f.value as number;
    else if (f.kind === 'u32') dv.setUint32(f.off, (f.value as number) >>> 0, true);
    else if (f.kind === 'i32') dv.setInt32(f.off, f.value as number, true);
    else (f.value as number[]).forEach((x, i) => dv.setInt32(f.off + 4 * i, x, true));
  }
  out.set(s.tail, total - s.tail.length);
  return out;
}

/** Predicted payload length for fixed-size plugins (undefined for Maximus: variable tail, or unknown version). */
export function predictedLength(plugin: string, versionRaw: number): number | undefined {
  if (!hasLayout(plugin) || plugin === 'Maximus') return undefined;
  const L = LAYOUTS[plugin];
  const v = L.version(versionRaw);
  if (!L.accepts(v)) return undefined;
  return 4 + L.fields.filter((f) => applies(f, v)).reduce((a, f) => a + sizeOf(f), 0);
}
