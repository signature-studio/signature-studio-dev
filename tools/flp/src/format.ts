// Human-readable / JSON formatting of typed events (used by cli/dump.ts).
import type { FlpFile } from './flp.ts';
import { decodeEvent, flVersionOf, type TypedEvent, type TypedValue } from './decode.ts';
import { summarize, type FlpSummary } from './summary.ts';

function fmtStruct(v: { fields: Record<string, number>; rest?: string }): string {
  return Object.entries(v.fields)
    .map(([k, x]) => `${k}=${Number.isInteger(x) ? x : +x.toFixed(6)}`)
    .join(' ') + (v.rest ? ` rest=${v.rest}` : '');
}

function wordsView(hexs: string): string {
  if (hexs.length % 8 !== 0 || hexs.length === 0 || hexs.length > 256) return '';
  const w: string[] = [];
  for (let i = 0; i < hexs.length; i += 8) {
    const b = hexs.substr(i, 8);
    w.push(b.substr(6, 2) + b.substr(4, 2) + b.substr(2, 2) + b.substr(0, 2));
  }
  return ` u32[${w.join(' ')}]`;
}

export function formatValue(t: TypedEvent, maxHex = 48): string {
  const v: TypedValue = t.value;
  switch (v.k) {
    case 'int':
      return t.name.endsWith('Color') ? `0x${(v.v >>> 0).toString(16).padStart(8, '0')}` : String(v.v);
    case 'text':
      return JSON.stringify(v.v.text.length > 120 ? v.v.text.slice(0, 117) + '...' : v.v.text) + (v.v.tail ? ` +tail:${v.v.tail}` : '') + (v.utf16 ? '' : ' (ascii)');
    case 'struct':
      return fmtStruct(v.v);
    case 'records':
      return `${v.v.length} x ${v.stride}B` + (v.v.length ? `; [0] ${fmtStruct(v.v[0])}` : '');
    case 'blob': {
      const b = v.v.length / 2;
      return `${b}B ${v.v.slice(0, maxHex * 2)}${b > maxHex ? '...' : ''}${b <= 40 ? wordsView(v.v) : ''}`;
    }
  }
}

export function idLabel(t: TypedEvent): string {
  return t.ext ? `0x${t.id.toString(16)}*` : String(t.id);
}

export function dumpText(f: FlpFile, opts: { limit?: number; ids?: Set<number>; offsets?: boolean } = {}): string {
  const ver = flVersionOf(f);
  const lines: string[] = [];
  lines.push(`# FLhd format=${f.header.format} nChannels=${f.header.nChannels} ppq=${f.header.ppq} FL=${ver.str} events=${f.events.length} dtLen=${f.dtLen}`);
  let n = 0;
  f.events.forEach((e, i) => {
    if (opts.ids && !opts.ids.has(e.id)) return;
    if (opts.limit !== undefined && n++ >= opts.limit) return;
    const t = decodeEvent(e, ver);
    const off = opts.offsets ? `@${e.off.toString(16).padStart(6, '0')} ` : '';
    lines.push(`${String(i).padStart(6)} ${off}${idLabel(t).padStart(5)} ${t.name.padEnd(22)} ${String(e.data.length).padStart(6)}  ${formatValue(t)}`);
  });
  return lines.join('\n');
}

export function dumpJson(f: FlpFile, opts: { limit?: number; ids?: Set<number> } = {}): { header: Record<string, number>; summary: FlpSummary; events: unknown[] } {
  const ver = flVersionOf(f);
  const evs: unknown[] = [];
  let n = 0;
  f.events.forEach((e, i) => {
    if (opts.ids && !opts.ids.has(e.id)) return;
    if (opts.limit !== undefined && n++ >= opts.limit) return;
    const t = decodeEvent(e, ver);
    evs.push({ i, off: e.off, id: t.id, ext: t.ext, name: t.name, size: e.data.length, value: t.value.k === 'blob' ? { k: 'blob', hex: t.value.v.slice(0, 512), truncated: t.value.v.length > 512 } : t.value });
  });
  const header = { hdrLen: f.header.hdrLen, format: f.header.format, nChannels: f.header.nChannels, ppq: f.header.ppq, dtLen: f.dtLen };
  return { header, summary: summarize(f), events: evs };
}
