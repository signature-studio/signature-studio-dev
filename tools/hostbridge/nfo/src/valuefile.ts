// FL "value file" (.nfo / VerifiedIDs.nfo): a plain-text list of `key=value` lines (Delphi TStringList.Values style).
// Reader semantics are from FLEngine_x64.dll 26.1.7: FUN_0065de10 (line lookup), FUN_00913be0/00913d40 (typed getters),
// FUN_00913360 (setter = append "key=value"), FUN_00913720 (LoadFromFile), FUN_00913e30 (SaveToFile).
// Browser-safe: no Node APIs.

/** Delphi StrToIntDef-compatible integer parse (decimal, `$hex`, `0x`/`0X`/`x` hex, leading blanks, sign). Not 32-bit-checked here. */
export function strToIntDef(s: string | undefined, def: number): number {
  if (s === undefined) return def;
  const t = s.replace(/^[\s\u0000]+/, '');
  const m = /^([+-]?)(\$[0-9a-fA-F]+|0[xX][0-9a-fA-F]+|[xX][0-9a-fA-F]+|[0-9]+)$/.exec(t.replace(/\s+$/, ''));
  if (!m) return def;
  const body = m[2];
  let v: number;
  if (body[0] === '$') v = parseInt(body.slice(1), 16);
  else if (/^0[xX]/.test(body)) v = parseInt(body.slice(2), 16);
  else if (/^[xX]/.test(body)) v = parseInt(body.slice(1), 16);
  else v = parseInt(body, 10);
  if (m[1] === '-') v = -v;
  return Number.isSafeInteger(v) ? v : def;
}

export function strToInt64Def(s: string | undefined, def: bigint): bigint {
  if (s === undefined) return def;
  const t = s.trim();
  const m = /^([+-]?)(\$[0-9a-fA-F]+|0[xX][0-9a-fA-F]+|[0-9]+)$/.exec(t);
  if (!m) return def;
  const body = m[2];
  let v: bigint;
  try {
    v = body[0] === '$' ? BigInt('0x' + body.slice(1)) : BigInt(body);
  } catch {
    return def;
  }
  if (m[1] === '-') v = -v;
  if (v < -(1n << 63n) || v >= 1n << 63n) return def;
  return v;
}

export class ValueFile {
  /** raw lines without line terminators */
  lines: string[];
  /** terminator that followed each line in the source ('' = none, i.e. last line of a file without trailing EOL) */
  terms: string[];
  /** terminator used for newly added lines (Delphi default CRLF) */
  eol: string;
  /** BOM seen on parse (re-emitted by toString) */
  bom: string;

  constructor(lines: string[] = [], eol = '\r\n') {
    this.lines = lines;
    this.eol = eol;
    this.terms = lines.map(() => eol);
    this.bom = '';
  }

  static parse(text: string): ValueFile {
    const vf = new ValueFile();
    if (text.charCodeAt(0) === 0xfeff) {
      vf.bom = '\ufeff';
      text = text.slice(1);
    }
    const re = /([^\r\n]*)(\r\n|\n|\r|$)/g;
    let m: RegExpExecArray | null;
    let crlf = 0;
    while ((m = re.exec(text)) !== null) {
      if (m[1] === '' && m[2] === '' ) break;
      vf.lines.push(m[1]);
      vf.terms.push(m[2]);
      if (m[2] === '\r\n') crlf++;
      if (m[2] === '') break;
    }
    vf.eol = crlf > 0 || vf.terms.every((t) => t === '') ? '\r\n' : vf.terms.find((t) => t !== '') ?? '\r\n';
    return vf;
  }

  toString(): string {
    let s = this.bom;
    for (let i = 0; i < this.lines.length; i++) s += this.lines[i] + (this.terms[i] ?? this.eol);
    return s;
  }

  /** FL lookup (FUN_0065de10): first line `KEY=value` whose KEY equals `key` case-insensitively; lines starting with `'` are comments. */
  get(key: string): string | undefined {
    const k = key.toUpperCase();
    for (const line of this.lines) {
      if (line.charCodeAt(0) === 0x27) continue;
      const p = line.indexOf('=');
      if (p < 0) continue;
      if (line.slice(0, p).toUpperCase() === k) return line.slice(p + 1);
    }
    return undefined;
  }

  getString(key: string): string {
    return this.get(key) ?? '';
  }

  getInt(key: string, def: number): number {
    return strToIntDef(this.get(key), def);
  }

  getInt64(key: string, def: bigint): bigint {
    return strToInt64Def(this.get(key), def);
  }

  /** FL setter FUN_00913360 in `fresh file` mode: always appends */
  add(key: string, value: string): void {
    this.lines.push(`${key}=${value}`);
    this.terms.push(this.eol);
  }

  keys(): string[] {
    const out: string[] = [];
    for (const line of this.lines) {
      if (line.charCodeAt(0) === 0x27) continue;
      const p = line.indexOf('=');
      if (p >= 0) out.push(line.slice(0, p));
    }
    return out;
  }
}

/** Text decoding for file bytes: BOM-aware (UTF-8 / UTF-16LE / UTF-16BE), otherwise latin1 (stand-in for the Windows ANSI code page). */
export function decodeText(b: Uint8Array): string {
  if (b.length >= 3 && b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) return new TextDecoder('utf-8').decode(b.subarray(3));
  if (b.length >= 2 && b[0] === 0xff && b[1] === 0xfe) return new TextDecoder('utf-16le').decode(b.subarray(2));
  if (b.length >= 2 && b[0] === 0xfe && b[1] === 0xff) return new TextDecoder('utf-16be').decode(b.subarray(2));
  let ascii = true;
  for (const x of b) if (x > 0x7f) { ascii = false; break; }
  if (ascii) return new TextDecoder('latin1').decode(b);
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(b);
  } catch {
    return new TextDecoder('latin1').decode(b);
  }
}

/** Encode: ASCII as-is; anything else UTF-8 with BOM (Delphi TEncoding.GetBufferEncoding recognises the BOM; without it the ANSI code page would be assumed). */
export function encodeText(s: string): Uint8Array {
  let ascii = true;
  for (let i = 0; i < s.length; i++) if (s.charCodeAt(i) > 0x7f) { ascii = false; break; }
  const body = new TextEncoder().encode(s);
  if (ascii) return body;
  const out = new Uint8Array(body.length + 3);
  out.set([0xef, 0xbb, 0xbf], 0);
  out.set(body, 3);
  return out;
}
