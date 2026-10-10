// Project / preset summary: tempo, length, channels, patterns, mixer inserts, plugin usage.
// Scope tracking is event-order based (see REPORT.md section 2): 64 opens a channel, 98 opens an effect slot, 236 opens a mixer insert.
import { type FlpFile, type FlpEvent } from './flp.ts';
import { decodeText, flVersionOf, textIsUtf16, playlistStride, type FlVersion, hex } from './decode.ts';
import { defOf } from './events.ts';

export const FORMAT_NAMES: Record<number, string> = {
  0: 'project',
  0x10: 'score',
  0x18: 'automation',
  0x20: 'channel-state',
  0x30: 'plugin-state',
  0x31: 'generator-state',
  0x32: 'fx-state',
  0x40: 'insert-state',
  0x50: 'patcher',
};

export interface VstInfo {
  kind: number;
  name?: string;
  vendor?: string;
  fourcc?: string;
  guid?: string;
  path?: string;
}

export interface PluginUse {
  where: 'channel' | 'slot' | 'root';
  /** channel iid or mixer insert index */
  owner: number;
  slot?: number;
  internalName: string;
  name: string;
  vst?: VstInfo;
  dataLen: number;
  /** 'native' | 'wrapper' | 'none' */
  kind: string;
  /** stable aggregation key (internal name, or vendor/name for wrapped third-party plugins) */
  key: string;
}

export interface ChannelInfo {
  iid: number;
  type?: number;
  routedTo?: number;
  plugin?: PluginUse;
  samplePath?: string;
  name?: string;
}

export interface FlpSummary {
  format: number;
  formatName: string;
  ppq: number;
  version: string;
  build: number;
  events: number;
  tempo?: number;
  timeSig: [number, number];
  title?: string;
  genre?: string;
  artists?: string;
  channels: number;
  channelTypes: Record<string, number>;
  patterns: number;
  notes: number;
  arrangements: number;
  playlistItems: number;
  /** end of the last playlist item / pattern in ticks */
  songTicks: number;
  songBars?: number;
  songSeconds?: number;
  maxPatternBars?: number;
  inserts: number;
  automationClips: number;
  plugins: PluginUse[];
  samples: number;
}

function readU16Text(d: Uint8Array, ver: FlVersion, id: number): string {
  return decodeText(d, textIsUtf16(defOf(id), id, ver)).text;
}

/** Wrapped third-party plugin state: u32 kind (8 = VST2, 10 = VST3) followed by { u32 id, u64 size, payload } records. */
export function parseWrapperData(d: Uint8Array): VstInfo | undefined {
  if (d.length < 12) return undefined;
  const dv = new DataView(d.buffer, d.byteOffset, d.byteLength);
  const kind = dv.getUint32(0, true);
  if (kind !== 8 && kind !== 10) return undefined;
  const info: VstInfo = { kind };
  let p = 4;
  let ok = false;
  while (p + 12 <= d.length) {
    const id = dv.getUint32(p, true);
    const size = Number(dv.getBigUint64(p + 4, true));
    p += 12;
    if (p + size > d.length || size > d.length) return ok ? info : undefined;
    const body = d.subarray(p, p + size);
    const s = () => new TextDecoder('utf-8').decode(body);
    if (id === 50) ok = true;
    if (id === 51) info.fourcc = s();
    else if (id === 52) info.guid = hex(body);
    else if (id === 54) info.name = s();
    else if (id === 55) info.path = s();
    else if (id === 56) info.vendor = s();
    p += size;
  }
  return ok && p === d.length ? info : ok ? info : undefined;
}

interface Cur {
  internalName: string;
  name: string;
  dataLen: number;
  data?: Uint8Array;
  has: boolean;
}

export function summarize(f: FlpFile): FlpSummary {
  const ver = flVersionOf(f);
  const s: FlpSummary = {
    format: f.header.format,
    formatName: FORMAT_NAMES[f.header.format] ?? `0x${f.header.format.toString(16)}`,
    ppq: f.header.ppq,
    version: ver.str,
    build: ver.build,
    events: f.events.length,
    timeSig: [4, 4],
    channels: 0,
    channelTypes: {},
    patterns: 0,
    notes: 0,
    arrangements: 0,
    playlistItems: 0,
    songTicks: 0,
    inserts: 0,
    automationClips: 0,
    plugins: [],
    samples: 0,
  };
  let owner: { where: 'channel' | 'slot' | 'root'; id: number; slot?: number } = { where: 'root', id: 0 };
  let cur: Cur = { internalName: '', name: '', dataLen: 0, has: false };
  let ch: ChannelInfo | undefined;
  let insertIdx = -1;
  let tempo: number | undefined;
  let tempoLegacy: number | undefined;
  let maxPatTicks = 0;
  let sigN = 4;
  let sigD = 4;

  const flush = (): void => {
    if (!cur.has) return;
    const pu = makePlugin(owner, cur);
    s.plugins.push(pu);
    if (owner.where === 'channel' && ch) ch.plugin = pu;
    cur = { internalName: '', name: '', dataLen: 0, has: false };
  };

  for (const e of f.events as FlpEvent[]) {
    if (e.ext) continue;
    const id = e.id;
    const dv = new DataView(e.data.buffer, e.data.byteOffset, e.data.byteLength);
    switch (id) {
      case 64:
        flush();
        owner = { where: 'channel', id: dv.getUint16(0, true) };
        ch = { iid: owner.id };
        s.channels++;
        break;
      case 65:
        flush();
        owner = { where: 'root', id: 0 };
        s.patterns++;
        break;
      case 99:
        flush();
        owner = { where: 'root', id: 0 };
        s.arrangements++;
        break;
      case 98:
        flush();
        owner = { where: 'slot', id: Math.max(insertIdx, 0), slot: dv.getUint16(0, true) };
        break;
      case 236:
        flush();
        insertIdx++;
        s.inserts++;
        owner = { where: 'root', id: 0 };
        break;
      case 201:
        flush();
        cur.internalName = readU16Text(e.data, ver, id);
        cur.has = true;
        break;
      case 203:
        cur.name = readU16Text(e.data, ver, id);
        cur.has = true;
        break;
      case 212:
        cur.has = true;
        break;
      case 213:
        cur.dataLen = e.data.length;
        cur.data = e.data;
        cur.has = true;
        break;
      case 21: {
        const t = e.data[0];
        if (ch) ch.type = t;
        s.channelTypes[t] = (s.channelTypes[t] ?? 0) + 1;
        if (t === 5 || t === 7) s.automationClips += t === 7 ? 1 : 0;
        break;
      }
      case 22:
        if (ch) ch.routedTo = dv.getInt8(0);
        break;
      case 196:
        s.samples++;
        if (ch) ch.samplePath = readU16Text(e.data, ver, id);
        break;
      case 156:
        tempo = dv.getUint32(0, true) / 1000;
        break;
      case 66:
        tempoLegacy = dv.getUint16(0, true);
        break;
      case 17:
        sigN = e.data[0];
        break;
      case 18:
        sigD = e.data[0];
        break;
      case 194:
        s.title = readU16Text(e.data, ver, id);
        break;
      case 206:
        s.genre = readU16Text(e.data, ver, id);
        break;
      case 207:
        s.artists = readU16Text(e.data, ver, id);
        break;
      case 224: {
        const n = e.data.length / 24;
        s.notes += n;
        for (let o = 0; o + 24 <= e.data.length; o += 24) {
          const end = dv.getUint32(o, true) + dv.getUint32(o + 8, true);
          if (end > maxPatTicks) maxPatTicks = end;
        }
        break;
      }
      case 233: {
        const st = playlistStride(e.data, ver);
        s.playlistItems += e.data.length / st;
        for (let o = 0; o + st <= e.data.length; o += st) {
          const end = dv.getUint32(o, true) + dv.getUint32(o + 8, true);
          if (end > s.songTicks) s.songTicks = end;
        }
        break;
      }
      default:
        break;
    }
  }
  flush();
  s.timeSig = [sigN, sigD];
  s.tempo = tempo ?? (tempoLegacy !== undefined ? tempoLegacy : undefined);
  const barTicks = (f.header.ppq * 4 * sigN) / Math.max(sigD, 1);
  if (s.songTicks > 0 && barTicks > 0) {
    s.songBars = s.songTicks / barTicks;
    if (s.tempo) s.songSeconds = (s.songBars * sigN * (4 / Math.max(sigD, 1)) * 60) / s.tempo;
  }
  if (maxPatTicks > 0 && barTicks > 0) s.maxPatternBars = maxPatTicks / barTicks;
  return s;
}

function makePlugin(o: { where: 'channel' | 'slot' | 'root'; id: number; slot?: number }, c: Cur): PluginUse {
  const vst = c.data ? parseWrapperData(c.data) : undefined;
  const internal = c.internalName;
  let key = internal || '(none)';
  let kind = c.data ? 'native' : 'none';
  if (vst) {
    kind = 'wrapper';
    // FL's "Fruity Wrapper" hosts legacy Fruity DLLs and third-party VSTs; identify by the hosted plugin name
    key = vst.name ?? c.name ?? internal;
  }
  const pu: PluginUse = { where: o.where, owner: o.id, internalName: internal, name: c.name, dataLen: c.dataLen, kind, key };
  if (o.slot !== undefined) pu.slot = o.slot;
  if (vst) pu.vst = vst;
  return pu;
}

