// Synthetic plugin-state .fst for a Fruity-Wrapper hosted plugin (VST2 / VST3 / CLAP / AU), byte layout as FL's own
// "Store preset" path writes it: fle:0xaac300 (FLhd/FLdt + 199 + 28), 0xaac1e0 (201/212/203/213), 0xab8ae0 + 0xa9eff0 (wrapper chunk).
// Browser-safe (Uint8Array only).
import { PlugClass, isGenClass } from './format.ts';

export interface WrapperFstSpec {
  /** ps_file_plugclass of the hosted file: 0/4 VST2, 7/8 VST3, 9/10 AU, 11/12 CLAP */
  plugclass: number;
  /** event 203 (shown plugin name) */
  displayName: string;
  /** chunk record 55 — plugin file path (omit with '' e.g. for multi-file entries) */
  filename: string;
  /** chunk record 54 — default: basename of `filename` without extension (non-CLAP), displayName for CLAP */
  nameRecord?: string;
  /** chunk record 56 */
  vendor?: string;
  /** chunk record 51 — VST2 uniqueID */
  magic?: number;
  /** chunk record 52 — VST3 class id (16 bytes, same bytes as ps_file_guid) */
  guid?: Uint8Array;
  /** chunk record 58 — CLAP plugin id */
  idstring?: string;
  /** which bit-widths exist in the DB entry (drives record-2 flag bits 0x400 / 0x100000) */
  has32?: boolean;
  has64?: boolean;
  /** chunk record 53 — plugin state blob, omitted when empty */
  state?: Uint8Array;
}

const te = new TextEncoder();

class Buf {
  parts: Uint8Array[] = [];
  len = 0;
  push(b: Uint8Array): void {
    this.parts.push(b);
    this.len += b.length;
  }
  u8(v: number): void { this.push(Uint8Array.of(v & 255)); }
  u16(v: number): void { this.push(Uint8Array.of(v & 255, (v >> 8) & 255)); }
  u32(v: number): void { this.push(Uint8Array.of(v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255)); }
  u64(v: bigint): void { const b = new Uint8Array(8); new DataView(b.buffer).setBigUint64(0, v, true); this.push(b); }
  bytes(): Uint8Array {
    const out = new Uint8Array(this.len);
    let o = 0;
    for (const p of this.parts) { out.set(p, o); o += p.length; }
    return out;
  }
}

function varint(n: number): Uint8Array {
  const o: number[] = [];
  do {
    let b = n & 0x7f;
    n = Math.floor(n / 128);
    if (n > 0) b |= 0x80;
    o.push(b);
  } while (n > 0);
  return Uint8Array.from(o);
}

function utf16z(s: string): Uint8Array {
  const b = new Uint8Array((s.length + 1) * 2);
  for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); b[i * 2] = c & 255; b[i * 2 + 1] = c >> 8; }
  return b;
}

/** ANSI/UTF-8 bytes for wrapper-chunk strings (FL writes the ANSI code page; identical to UTF-8 for ASCII names) */
function ansi(s: string): Uint8Array {
  return te.encode(s);
}

function baseNameNoExt(p: string): string {
  const b = p.slice(Math.max(p.lastIndexOf('\\'), p.lastIndexOf('/')) + 1);
  const d = b.lastIndexOf('.');
  return d > 0 ? b.slice(0, d) : b;
}

/** the 213 payload: u32 8, then { u32 id, u64 size, payload }* (fle:0xa9eff0; records 2, 50, 51|52|58|51+52, 54, 55, 56, 53) */
export function buildWrapperChunk(s: WrapperFstSpec): Uint8Array {
  const b = new Buf();
  b.u32(8);
  const rec = (id: number, payload: Uint8Array): void => {
    b.u32(id);
    b.u64(BigInt(payload.length));
    b.push(payload);
  };
  const has32 = s.has32 ?? false;
  const has64 = s.has64 ?? true;
  let flags = 0x407908;
  if (has64 && !has32) flags |= 0x400;
  if (!(has32 && has64)) flags |= 0x100000;
  const r2 = new Uint8Array(25);
  const dv2 = new DataView(r2.buffer);
  dv2.setInt32(1, -1, true);
  dv2.setInt32(5, -1, true);
  dv2.setUint32(9, flags >>> 0, true);
  r2[17] = 1;
  rec(2, r2);

  const r50 = new Uint8Array(16);
  new DataView(r50.buffer).setUint32(0, s.plugclass, true);
  rec(50, r50);

  const magic4 = (): Uint8Array => { const m = new Uint8Array(4); new DataView(m.buffer).setUint32(0, (s.magic ?? 0) >>> 0, true); return m; };
  const guid16 = (): Uint8Array => { const g = new Uint8Array(16); if (s.guid) g.set(s.guid.subarray(0, 16)); return g; };
  const c = s.plugclass;
  if (c === 0 || c === 4) rec(51, magic4());
  else if (c === 7 || c === 8) rec(52, guid16());
  else if (c === 11 || c === 12) rec(58, ansi(s.idstring ?? ''));
  else { rec(51, magic4()); rec(52, guid16()); }

  const clap = c === 11 || c === 12;
  const nameRec = s.nameRecord ?? (clap || !s.filename ? s.displayName : baseNameNoExt(s.filename));
  if (nameRec) rec(54, ansi(nameRec));
  if (s.filename) rec(55, ansi(s.filename));
  if (s.vendor) rec(56, ansi(s.vendor));
  if (s.state && s.state.length > 0) rec(53, s.state);
  return b.bytes();
}

/** 52-byte event 212 body: zero except u32@8 = 2 and flags u16@16 (0x10 = generator) — fle:0xaac1e0 with kind 2/3 */
export function buildWrapperHeader(isGen: boolean): Uint8Array {
  const w = new Uint8Array(52);
  const dv = new DataView(w.buffer);
  dv.setUint32(8, 2, true);
  dv.setUint16(16, isGen ? 0x10 : 0, true);
  return w;
}

/** FLhd{format 0x30, nChannels 2, ppq 48} + FLdt{events}: the container FL writes for plugin-state files (fle:0xaac300). Only TEXT/DATA events (id >= 192) and BYTE events (id < 64) are needed. */
export function assembleFst(events: Array<{ id: number; data: Uint8Array }>, hdr = { format: 0x30, nChannels: 2, ppq: 48 }): Uint8Array {
  const ev = new Buf();
  for (const e of events) {
    ev.u8(e.id);
    if (e.id >= 192) ev.push(varint(e.data.length));
    else if (e.id < 64 && e.data.length !== 1) throw new Error(`event ${e.id}: BYTE events carry 1 byte`);
    ev.push(e.data);
  }
  const body = ev.bytes();
  const out = new Buf();
  out.push(te.encode('FLhd'));
  out.u32(6);
  out.u16(hdr.format);
  out.u16(hdr.nChannels);
  out.u16(hdr.ppq);
  out.push(te.encode('FLdt'));
  out.u32(body.length);
  out.push(body);
  return out.bytes();
}

/** Complete .fst: FLhd{format 0x30, nChannels 2, ppq 48} FLdt{ 199 "11.5.5", 28=1, 201 "Fruity Wrapper", 212, 203 name, 213 chunk } */
export function buildWrapperFst(s: WrapperFstSpec): Uint8Array {
  const isGen = isGenClass(s.plugclass);
  const events: Array<{ id: number; data: Uint8Array }> = [
    { id: 199, data: Uint8Array.of(...te.encode('11.5.5'), 0) },
    { id: 28, data: Uint8Array.of(1) },
    { id: 201, data: utf16z('Fruity Wrapper') },
    { id: 212, data: buildWrapperHeader(isGen) },
  ];
  if (s.displayName !== 'Fruity Wrapper') events.push({ id: 203, data: utf16z(s.displayName) });
  events.push({ id: 213, data: buildWrapperChunk(s) });
  return assembleFst(events);
}

export { PlugClass };
