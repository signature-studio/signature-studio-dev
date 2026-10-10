// Constants / small codecs shared by the Plugin-database readers and writers.
// Every table below is read from FLEngine_x64.dll 26.1.7 (win64 block00031); sources are given as `fle:0xADDR`.

/** ps_file_plugclass. fx/gen pairs are (0,4) (1,5) (2,3) (7,8) (9,10) (11,12); 6 is unused. `fle:0x8ef860`, `0x8f0ab0`, `0x8f0bc0`. */
export const PlugClass = {
  VstFx: 0,
  DxFx: 1,
  FlFx: 2,
  FlGen: 3,
  VstGen: 4,
  DxGen: 5,
  Vst3Fx: 7,
  Vst3Gen: 8,
  AuFx: 9,
  AuGen: 10,
  ClapFx: 11,
  ClapGen: 12,
} as const;

export type Family = 'fruity' | 'vst' | 'vst3' | 'au' | 'clap' | 'dx';

/** class → plugin format family (`fle:0x8f0300` masks 0x0c/0x11/0x0180/0x06<<8/0x18<<8; DX has no folder) */
export function familyOf(plugclass: number): Family | undefined {
  switch (plugclass) {
    case 2: case 3: return 'fruity';
    case 0: case 4: return 'vst';
    case 7: case 8: return 'vst3';
    case 9: case 10: return 'au';
    case 11: case 12: return 'clap';
    case 1: case 5: return 'dx';
    default: return undefined;
  }
}

/** sub-folder under Installed\{Effects|Generators}\ (`fle:0x8f0300`) */
export const FAMILY_DIR: Record<Family, string> = { fruity: 'Fruity', vst: 'VST', vst3: 'VST3', au: 'AudioUnit', clap: 'CLAP', dx: '' };

/** fx variant of a class (`fle:0x8f0bc0`, used by writer-side `|%d|…` keys) */
export function fxClassOf(c: number): number {
  switch (c) { case 8: return 7; case 3: return 2; case 4: return 0; case 5: return 1; case 10: return 9; case 12: return 11; default: return c; }
}

/** `fle:0x8f0ab0(isFx, c)`: map a class to its fx (isFx) or gen variant */
export function classVariant(isFx: boolean, c: number): number {
  const pairs: Array<[number, number]> = [[0, 4], [1, 5], [2, 3], [7, 8], [9, 10], [11, 12]];
  for (const [fx, gen] of pairs) if (c === fx || c === gen) return isFx ? fx : gen;
  return c;
}

export function isGenClass(c: number): boolean {
  return c === 3 || c === 4 || c === 5 || c === 8 || c === 10 || c === 12;
}

/** bits as stored in memory: 2 = 32-bit, 3 = 64-bit (ps_file_bitsize 32/64; `fle:0x913960`, `0x913e60`) */
export const Bits = { B32: 2, B64: 3 } as const;

/** ps_file_arch strings (`fle:0x63b830` against table 0x13e4fe8; index 0 = empty). mac only. */
export const ARCH_NAMES = ['', 'Intel', 'Apple', 'Apple + Intel'] as const;

/** Slot an entry file lands in (`fle:0x8f6990`): -1 = rejected (DX, class 6, > 12) */
export function slotOf(plugclass: number, bits: number): number {
  const b64 = bits === 3;
  if (plugclass === 2 || plugclass === 3) return b64 ? 1 : 0;
  if (plugclass === 0 || plugclass === 4) return b64 ? 3 : 2;
  if (plugclass === 7 || plugclass === 8) return b64 ? 5 : 4;
  if ((plugclass === 9 || plugclass === 10) && b64) return 6;
  if ((plugclass === 11 || plugclass === 12) && b64) return 7;
  return -1;
}

/** on-disk ps_file_scanflags → in-memory bits (`fle:0x910590`) and back (`fle:0x910530`). In-memory 0x08 is runtime-only ("new plugin"). */
export function scanFlagsFromDisk(v: number): number {
  let r = 0;
  if (v & 1) r |= 1;
  if (v & 2) r |= 2;
  if (v & 0x10) r |= 4;
  if (v & 0x20) r |= 0x10;
  return r;
}
export function scanFlagsToDisk(m: number): number {
  let r = m & 1 ? 1 : 0;
  if (m & 2) r |= 2;
  if (m & 4) r |= 0x10;
  if (m & 0x10) r |= 0x20;
  return r;
}

// ---------------------------------------------------------------- GUID text <-> 16 bytes (`fle:0x439300` / `0x4391c0`)
// Text is `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}` (38 chars, upper-case hex written; both cases read). The byte↔char mapping equals
// the Windows GUID memory layout (Data1/2/3 little-endian), i.e. Delphi GUIDToString.
const GUID_POS = [7, 5, 3, 1, 12, 10, 17, 15, 20, 22, 25, 27, 29, 31, 33, 35];

export function guidToString(b: Uint8Array): string {
  if (b.length !== 16) throw new Error('GUID needs 16 bytes');
  const c: string[] = '{00000000-0000-0000-0000-000000000000}'.split('');
  for (let i = 0; i < 16; i++) {
    const h = b[i].toString(16).toUpperCase().padStart(2, '0');
    c[GUID_POS[i]] = h[0];
    c[GUID_POS[i] + 1] = h[1];
  }
  return c.join('');
}

/** returns undefined for malformed text (FL raises an exception there; callers treat as invalid file) */
export function guidFromString(s: string): Uint8Array | undefined {
  if (s.length !== 38 || s[0] !== '{' || s[9] !== '-' || s[14] !== '-' || s[19] !== '-' || s[24] !== '-' || s[37] !== '}') return undefined;
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) {
    const h = s.slice(GUID_POS[i], GUID_POS[i] + 2);
    if (!/^[0-9a-fA-F]{2}$/.test(h)) return undefined;
    out[i] = parseInt(h, 16);
  }
  return out;
}

/** VST3 class id text (32 hex chars — moduleinfo.json "CID" / `ps_file_guid` 表記 / VerifiedIDs key) → 16 bytes.
 *  The hex IS the GUID-text hex FL writes (`{hex8-hex4-hex4-hex4-hex12}`), so the bytes are the Windows GUID memory
 *  layout of that text — which is exactly what the .fst record 52 holds. Real-machine cross-check (CAB-215/219):
 *  Serum 2 text {56534558-6673-5073-6572-756D20320000} ⇔ OTT record-52 raw `XTSVTfoTtt…`. */
export function tuidFromHex(hex: string): Uint8Array {
  if (!/^[0-9a-fA-F]{32}$/.test(hex)) throw new Error('TUID hex must be 32 chars');
  return guidFromString(`{${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}}`)!;
}

export const NULL_GUID = new Uint8Array(16);
export function isNullGuid(b: Uint8Array): boolean {
  return b.every((x) => x === 0);
}

/** VST2 pseudo-GUID (`fle:0x8f0d30` builds the hex text: "VST" (param_4=0) / "VSE" (≠0) + `%.8x` magic + first 9
 *  name bytes as `%.2x`, grouped 8-4-4-4-12). Real machine (CAB-219 .Plugins.ini, 64/64): the scanner calls it with
 *  the **lower-cased** plugin name and the "VST" prefix — `ps_file_guid` of every VST2 file = ASCII
 *  `"VST" + <magic 4 chars BE> + lower(name)` truncated / NUL-padded to 16 bytes. The "VSE" variant exists in FL but
 *  was never observed in real files. */
export function vst2PseudoGuid(name: string, magic: number, vseVariant = false): Uint8Array {
  let h = (vseVariant ? 0x565345 : 0x565354).toString(16).padStart(6, '0') + (magic >>> 0).toString(16).padStart(8, '0');
  const lower = name.toLowerCase();
  for (let i = 0; i < 9; i++) h += (i < lower.length ? lower.charCodeAt(i) & 0xff : 0).toString(16).padStart(2, '0');
  const g = `{${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}}`;
  return guidFromString(g.toUpperCase())!;
}

// ---------------------------------------------------------------- path tokens (`fle:0x8f19b0` read, `0x8f1820` write)
/** reader: replace the token by `root` without its trailing backslash */
export function expandToken(text: string, root: string, token: string): string {
  const r = root.endsWith('\\') ? root.slice(0, -1) : root;
  return text.split(token).join(r);
}
/** writer: if `text` starts with `root` (case-insensitive) → token + remainder (remainder keeps its leading backslash) */
export function compressToken(text: string, root: string | undefined, token: string): string {
  if (!text || !root) return text;
  const r = root.endsWith('\\') ? root.slice(0, -1) : root;
  if (r && text.toUpperCase().startsWith(r.toUpperCase())) return token + text.slice(r.length);
  return text;
}

/** file-name sanitiser for DB entry names (`fle:0x8f0740`): `\ / | ? * " < > :` → `-`, leading `.` → `-` */
export function sanitizeName(name: string): string {
  let s = name.replace(/[\\/|?*"<>:]/g, '-');
  if (s.startsWith('.')) s = '-' + s.slice(1);
  return s;
}

// ---------------------------------------------------------------- TStrings.DelimitedText (ps_compatibility), Delimiter=',' QuoteChar='"', StrictDelimiter=false
export function delimitedParse(s: string): string[] {
  const out: string[] = [];
  let i = 0;
  const n = s.length;
  while (i < n) {
    while (i < n && s.charCodeAt(i) > 0 && s.charCodeAt(i) <= 32) i++;
    if (i >= n) break;
    let item = '';
    if (s[i] === '"') {
      i++;
      for (;;) {
        const j = s.indexOf('"', i);
        if (j < 0) { item += s.slice(i); i = n; break; }
        item += s.slice(i, j);
        i = j + 1;
        if (s[i] === '"') { item += '"'; i++; } else break;
      }
      while (i < n && s[i] !== ',' && s.charCodeAt(i) > 32) item += s[i++];
    } else {
      while (i < n && s[i] !== ',' && s.charCodeAt(i) > 32) item += s[i++];
    }
    out.push(item);
    while (i < n && s.charCodeAt(i) > 0 && s.charCodeAt(i) <= 32) i++;
    if (i < n && s[i] === ',') {
      i++;
      if (i >= n) out.push('');
    }
  }
  return out;
}

export function delimitedFormat(items: string[]): string {
  if (items.length === 1 && items[0] === '') return '""';
  return items.map((x) => (x === '' || /[\u0000-\u0020,"]/.test(x) ? '"' + x.replace(/"/g, '""') + '"' : x)).join(',');
}
