// One pass over the whole corpus -> manifest.json, fst_manifest.json, plugins.json, event_census.json, unknown_events.json
// usage: node cli/corpus.ts [outDir=corpus]
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { readdirSync, lstatSync } from 'node:fs';
import { parseFlp, classOf } from '../src/flp.ts';
import { decodeEvent, flVersionOf, typedRoundTrip, type FlVersion } from '../src/decode.ts';
import { summarize, type FlpSummary, type PluginUse } from '../src/summary.ts';
import { defOf, docStatus, isEngineWritten, isUpstreamKnown } from '../src/events.ts';
import { ENGINE_WRITTEN_IDS, UPSTREAM_IDS } from '../src/id_sets.ts';
import { listFlhdFiles, flRoot } from './_corpus.ts';

const outDir = process.argv[2] ?? 'corpus';
mkdirSync(outDir, { recursive: true });

const vkey = (v: FlVersion): number[] => [v.major, v.minor, v.patch, v.build];
const vcmp = (a: number[], b: number[]): number => {
  for (let i = 0; i < 4; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
};

interface Census {
  id: number;
  count: number;
  files: number;
  groups: Record<string, number>;
  sizes: Map<number, number>;
  first: { ver: number[]; file: string };
  last: { ver: number[]; file: string };
  sample: string;
}
const census = new Map<number, Census>();

interface PluginAgg {
  key: string;
  internalName: string;
  kind: string;
  instancesChannel: number;
  instancesSlot: number;
  projects: Set<string>;
  groups: Record<string, number>;
  presetFiles: number;
  presetBytes: number;
  vstVendors: Set<string>;
  names: Map<string, number>;
}
const plugins = new Map<string, PluginAgg>();
function aggPlugin(p: PluginUse, file: string, group: string, isPreset: boolean, bytes: number): void {
  if (p.key === '(none)') return;
  const nk = p.key.toLowerCase();
  let a = plugins.get(nk);
  if (!a) {
    a = { key: p.key, internalName: p.internalName, kind: p.kind, instancesChannel: 0, instancesSlot: 0, projects: new Set(), groups: {}, presetFiles: 0, presetBytes: 0, vstVendors: new Set(), names: new Map() };
    plugins.set(nk, a);
  }
  if (isPreset) {
    a.presetFiles++;
    a.presetBytes += bytes;
  } else {
    if (p.where === 'channel') a.instancesChannel++;
    else if (p.where === 'slot') a.instancesSlot++;
    a.projects.add(file);
    a.groups[group] = (a.groups[group] ?? 0) + 1;
  }
  if (p.vst?.vendor) a.vstVendors.add(p.vst.vendor);
  if (p.name) a.names.set(p.name, (a.names.get(p.name) ?? 0) + 1);
}

// case-insensitive index of the FL tree, used to resolve %FLStudioFactoryData% sample references
const tree = new Map<string, string>();
(function walkTree(dir: string, rel: string): void {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = lstatSync(p);
    const r = rel ? `${rel}/${name}` : name;
    if (st.isDirectory()) walkTree(p, r);
    else if (st.isFile()) tree.set(r.toLowerCase(), r);
  }
})(flRoot(), '');
function sampleRefs(p: ReturnType<typeof parseFlp>, ver: FlVersion): { total: number; factory: number; resolved: number; missing: string[] } {
  const out = { total: 0, factory: 0, resolved: 0, missing: [] as string[] };
  for (const e of p.events) {
    if (e.id !== 196 || e.ext) continue;
    const t = decodeEvent(e, ver);
    if (t.value.k !== 'text') continue;
    const path = t.value.v.text;
    out.total++;
    if (!path.toLowerCase().startsWith('%flstudiofactorydata%')) continue;
    out.factory++;
    const rel = path.slice('%FLStudioFactoryData%'.length).replace(/\\/g, '/').replace(/^\//, '').toLowerCase();
    if (tree.has(rel)) out.resolved++;
    else out.missing.push(path);
  }
  return out;
}

const projects: unknown[] = [];
const presets: unknown[] = [];
const files = listFlhdFiles();
let n = 0;
for (const f of files) {
  const buf = readFileSync(f.abs);
  const p = parseFlp(buf);
  const ver = flVersionOf(p);
  const sum = summarize(p);
  const sha = createHash('sha256').update(buf).digest('hex');
  const ids = new Set<number>();
  for (const e of p.events) {
    ids.add(e.id);
    let c = census.get(e.id);
    if (!c) {
      c = { id: e.id, count: 0, files: 0, groups: {}, sizes: new Map(), first: { ver: vkey(ver), file: f.rel }, last: { ver: vkey(ver), file: f.rel }, sample: Buffer.from(e.data.subarray(0, 24)).toString('hex') };
      census.set(e.id, c);
    }
    c.count++;
    c.sizes.set(e.data.length, (c.sizes.get(e.data.length) ?? 0) + 1);
  }
  for (const id of ids) {
    const c = census.get(id)!;
    c.files++;
    c.groups[f.group] = (c.groups[f.group] ?? 0) + 1;
    const vk = vkey(ver);
    if (vcmp(vk, c.first.ver) < 0) c.first = { ver: vk, file: f.rel };
    if (vcmp(vk, c.last.ver) > 0) c.last = { ver: vk, file: f.rel };
  }
  const t1 = typedRoundTrip(p);
  const undocumentedEvents = p.events.filter((e) => docStatus(e.id) === 'undocumented').length;
  const common = { rel: f.rel, group: f.group, size: buf.length, sha256: sha, events: p.events.length, distinctIds: ids.size, version: sum.version, format: sum.formatName, ppq: sum.ppq, typedRoundTripOk: t1.mismatches.length === 0, undocumentedEvents };
  if (f.ext === 'flp') {
    const usage: Record<string, number> = {};
    for (const pl of sum.plugins) if (pl.key !== '(none)') usage[pl.key] = (usage[pl.key] ?? 0) + 1;
    for (const pl of sum.plugins) aggPlugin(pl, f.rel, f.group, false, 0);
    projects.push({ ...common, ...pick(sum), pluginUsage: usage, sampleRefs: sampleRefs(p, ver) });
  } else {
    const pl = sum.plugins[0];
    if (pl) aggPlugin(pl, f.rel, f.group, true, buf.length);
    const topdir = f.rel.split('/').slice(0, 3).join('/');
    const { sha256: _s, ...c2 } = common;
    void _s;
    presets.push({ ...c2, dir: topdir, plugin: pl?.key ?? null, internalName: pl?.internalName ?? null, pluginDataLen: pl?.dataLen ?? 0, channels: sum.channels, inserts: sum.inserts });
  }
  if (++n % 2000 === 0) console.error(`${n}/${files.length}`);
}

/** expected offline-render length: song length when a playlist exists, else the longest pattern (rounded up to whole bars) */
function renderSeconds(s: FlpSummary): number | undefined {
  if (!s.tempo) return undefined;
  const barSec = (s.timeSig[0] * (4 / Math.max(s.timeSig[1], 1)) * 60) / s.tempo;
  if (s.songBars !== undefined) return +(s.songBars * barSec).toFixed(2);
  if (s.maxPatternBars !== undefined) return +(Math.ceil(s.maxPatternBars) * barSec).toFixed(2);
  return undefined;
}

function pick(s: FlpSummary): Record<string, unknown> {
  return {
    tempo: s.tempo,
    timeSig: s.timeSig,
    title: s.title,
    channels: s.channels,
    channelTypes: s.channelTypes,
    patterns: s.patterns,
    notes: s.notes,
    arrangements: s.arrangements,
    playlistItems: s.playlistItems,
    songTicks: s.songTicks,
    songBars: s.songBars !== undefined ? +s.songBars.toFixed(2) : undefined,
    songSeconds: s.songSeconds !== undefined ? +s.songSeconds.toFixed(1) : undefined,
    maxPatternBars: s.maxPatternBars !== undefined ? +s.maxPatternBars.toFixed(2) : undefined,
    renderSeconds: renderSeconds(s),
    inserts: s.inserts,
    samples: s.samples,
    pluginInstances: s.plugins.filter((x) => x.key !== '(none)').length,
  };
}

const verStr = (v: number[]): string => v.join('.');
const J = (o: unknown): string => JSON.stringify(o, null, 1);
const JC = (o: unknown): string => JSON.stringify(o);

writeFileSync(join(outDir, 'manifest.json'), J({ root: flRoot(), generated: 'cli/corpus.ts', count: projects.length, projects }));
writeFileSync(join(outDir, 'fst_manifest.json'), JC({ root: flRoot(), count: presets.length, presets }));

// plugins
const ranked = [...plugins.values()]
  .map((a) => ({
    key: a.key,
    internalName: a.internalName,
    kind: a.kind,
    projects: a.projects.size,
    instancesChannel: a.instancesChannel,
    instancesSlot: a.instancesSlot,
    instances: a.instancesChannel + a.instancesSlot,
    presetFiles: a.presetFiles,
    presetBytes: a.presetBytes,
    groups: a.groups,
    vendors: [...a.vstVendors],
    topNames: [...a.names.entries()].sort((x, y) => y[1] - x[1]).slice(0, 3).map((x) => x[0]),
  }))
  .sort((x, y) => y.projects - x.projects || y.instances - x.instances || y.presetFiles - x.presetFiles);
writeFileSync(join(outDir, 'plugins.json'), J({ note: 'projects = distinct .flp files (Demo/Template/Render-test/system) using the plugin; instances = channel+mixer-slot instances; presetFiles = .fst/.fsc files whose root plugin is it', total: ranked.length, ranked }));

// census
const rows = [...census.values()].sort((a, b) => a.id - b.id);
const censusOut = rows.map((c) => {
  const sizes = [...c.sizes.entries()].sort((a, b) => b[1] - a[1]);
  return {
    id: c.id,
    idHex: '0x' + c.id.toString(16),
    name: defOf(c.id)?.name ?? null,
    cls: ['byte', 'word', 'dword', 'text'][classOf({ id: c.id, ext: c.id > 255 }) / 64] ?? 'none',
    count: c.count,
    files: c.files,
    groups: c.groups,
    distinctSizes: sizes.length,
    topSizes: sizes.slice(0, 6).map(([s, k]) => `${s}x${k}`),
    firstSeen: verStr(c.first.ver),
    firstFile: c.first.file,
    lastSeen: verStr(c.last.ver),
    status: docStatus(c.id),
    upstreamKnown: isUpstreamKnown(c.id),
    engineWritten: isEngineWritten(c.id),
    sample: c.sample,
  };
});
writeFileSync(join(outDir, 'event_census.json'), J({ distinctIds: rows.length, events: rows.reduce((a, b) => a + b.count, 0), ids: censusOut }));

const FL21 = [20, 99, 0, 0];
const notUpstream = censusOut.filter((c) => !c.upstreamKnown);
const newPost21 = notUpstream.filter((c) => vcmp(c.firstSeen.split('.').map(Number), FL21) >= 0);
const newIn25 = notUpstream.filter((c) => vcmp(c.firstSeen.split('.').map(Number), [25, 2, 0, 0]) >= 0);
const censusIds = new Set(rows.map((r) => r.id));
const engineOnly = [...ENGINE_WRITTEN_IDS].filter((i) => !censusIds.has(i)).sort((a, b) => a - b);
const slim = (c: (typeof censusOut)[number]) => ({ id: c.id, idHex: c.idHex, name: c.name, count: c.count, files: c.files, topSizes: c.topSizes, firstSeen: c.firstSeen, lastSeen: c.lastSeen, status: c.status, engineWritten: c.engineWritten, sample: c.sample });
writeFileSync(
  join(outDir, 'unknown_events.json'),
  J({
    definition: {
      undocumented: 'in corpus, but the dictionary label is low-confidence/observed-only (semantics unverified)',
      notInUpstream: 'in corpus, id not modelled by PyFLP 2.2.1 (public upstream baseline, FL <= 21)',
      newSinceFl21: 'notInUpstream AND first seen in a file with FL >= 20.99 (i.e. introduced after the public baseline)',
      newSince25_2: 'notInUpstream AND first seen in FL >= 25.2',
      engineOnly: 'written by FLEngine_x64.dll 26.1.7 (direct call sites) but absent from the corpus',
    },
    counts: { distinctIdsInCorpus: rows.length, undocumented: censusOut.filter((c) => c.status === 'undocumented').length, notInUpstream: notUpstream.length, newSinceFl21: newPost21.length, newSince25_2: newIn25.length, engineOnly: engineOnly.length, upstreamIdsTotal: UPSTREAM_IDS.size },
    undocumented: censusOut.filter((c) => c.status === 'undocumented').map(slim),
    notInUpstream: notUpstream.map(slim),
    newSinceFl21: newPost21.map(slim),
    newSince25_2: newIn25.map(slim),
    engineOnly: engineOnly.map((i) => ({ id: i, idHex: '0x' + i.toString(16) })),
  }),
);
console.log(JSON.stringify({ files: files.length, flp: projects.length, presets: presets.length, plugins: ranked.length, distinctIds: rows.length, notInUpstream: notUpstream.length, newSinceFl21: newPost21.length, newSince25_2: newIn25.length, engineOnly: engineOnly.length }));
