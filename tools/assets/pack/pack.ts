// FL 資産ツリー -> manifest + content-addressed chunk 群 (R2 アップロード用レイアウト)。実アップロードは行わない。
//
//   node pack/pack.ts --inv work/inv_win.jsonl --tiers work/tiers.json --out work/pkg-full [--chunk 1048576]
//        [--small 131072] [--codec br|zstd|raw] [--quality 11] [--only <regex>] [--max-files N] [--concurrency 16]
//
// 出力 (out/):
//   c/<id[0:2]>/<id>.<raw|br|zst>   chunk (内容アドレス; Cache-Control: immutable)
//   m/<sha16>.json                  manifest (JSON, 配信時は br)  /  latest.json (短 TTL の pointer)
//   upload-plan.json                key / file / Content-Type / Content-Encoding / Cache-Control
//   stats.json                      寸法・圧縮実測
process.env.UV_THREADPOOL_SIZE ??= '16';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { promisify } from 'node:util';
import type { DirEntry, FileEntry, Manifest } from '../vfs/types.ts';

const brotli = promisify(zlib.brotliCompress);
const zstd = promisify(zlib.zstdCompress);
const c = zlib.constants;

const args: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i++) {
  const a = process.argv[i];
  if (a.startsWith('--')) {
    const [k, v] = a.slice(2).split('=');
    args[k] = v ?? process.argv[++i];
  }
}
const here = path.dirname(new URL(import.meta.url).pathname);
const root = path.join(here, '..');
const INV = path.resolve(root, args.inv ?? 'work/inv_win.jsonl');
const TIERS = path.resolve(root, args.tiers ?? 'work/tiers.json');
const OUT = path.resolve(root, args.out ?? 'work/pkg-full');
const CHUNK = Number(args.chunk ?? 1 << 20);
const SMALL = Number(args.small ?? 128 * 1024);
const CODEC = (args.codec ?? 'br') as 'br' | 'zstd' | 'raw';
const QUALITY = Number(args.quality ?? 11);
const ONLY = args.only ? new RegExp(args.only, 'i') : null;
const MAX_FILES = args['max-files'] ? Number(args['max-files']) : Infinity;
const CONC = Number(args.concurrency ?? 16);
const NAME = args.name ?? 'fl-studio-26.1.7.5653-win64';

interface Ent {
  p: string;
  size: number;
  disk: string;
  sha: string;
  cat: string;
  cls: string;
  tier: string;
}
const TIER_RANK: Record<string, number> = { T0: 0, T0p: 1, T1: 2, T2: 3 };
const INCOMPRESSIBLE = /\.(wv|flac|ogg|mp3|png|jpe?g|zip|gz|br|mp4|webp)$/i;

function loadInventory(): Ent[] {
  const tiers: Record<string, string> = JSON.parse(fs.readFileSync(TIERS, 'utf8'));
  const out: Ent[] = [];
  for (const line of fs.readFileSync(INV, 'utf8').split('\n')) {
    if (!line) continue;
    const e = JSON.parse(line);
    if (e.cls === 'skip' || e.cls === 'symlink') continue;
    if (ONLY && !ONLY.test(e.p)) continue;
    out.push({ p: e.tp ?? e.p, size: e.size, disk: e.disk, sha: e.sha, cat: e.cat, cls: e.cls, tier: tiers[e.p] ?? 'T2' });
    if (out.length >= MAX_FILES) break;
  }
  return out;
}

interface Placement {
  first: number;
  off: number; // -1 = 専用 chunk 連続
}
interface PlanChunk {
  members: { ent: Ent; off: number; len: number; srcOff: number }[]; // pack: 複数、 file: 1
  usize: number;
  group: string;
  hint: 'text' | 'binary' | 'incompressible';
}

function main() {
  const t0 = Date.now();
  const ents = loadInventory();
  // path 大小無視の衝突検査
  const seenPath = new Map<string, string>();
  for (const e of ents) {
    const k = e.p.toLowerCase();
    if (seenPath.has(k) && seenPath.get(k) !== e.p) throw new Error('case collision: ' + e.p + ' vs ' + seenPath.get(k));
    seenPath.set(k, e.p);
  }
  // 内容 (sha) 単位の正準化。stub は別扱い
  const stubs = ents.filter((e) => e.cat === 'exec');
  const data = ents.filter((e) => e.cat !== 'exec');
  const byContent = new Map<string, Ent[]>();
  for (const e of data) {
    if (e.size === 0) continue;
    if (!byContent.has(e.sha)) byContent.set(e.sha, []);
    byContent.get(e.sha)!.push(e);
  }
  const canon: { ent: Ent; tier: string }[] = [];
  for (const [, list] of byContent) {
    list.sort((a, b) => TIER_RANK[a.tier] - TIER_RANK[b.tier] || (a.p < b.p ? -1 : 1));
    canon.push({ ent: list[0], tier: list[0].tier });
  }
  const rankKey = (x: { ent: Ent; tier: string }) => [TIER_RANK[x.tier], x.ent.size > SMALL ? 1 : 0, x.ent.p.toLowerCase()] as const;
  canon.sort((a, b) => {
    const ka = rankKey(a);
    const kb = rankKey(b);
    return ka[0] - kb[0] || ka[1] - kb[1] || (ka[2] < kb[2] ? -1 : ka[2] > kb[2] ? 1 : 0);
  });

  // ---- chunk 計画 ----
  const plan: PlanChunk[] = [];
  const place = new Map<string, Placement>(); // sha -> placement
  const hintOf = (p: string): PlanChunk['hint'] =>
    INCOMPRESSIBLE.test(p) ? 'incompressible' : /\.(txt|ini|xml|nfo|html?|css|js|json|rtf|py|svg|scr|flstheme|tbio)$/i.test(p) ? 'text' : 'binary';
  let pack: PlanChunk | null = null;
  let packTier = '';
  const flush = () => {
    if (pack && pack.members.length) plan.push(pack);
    pack = null;
  };
  for (const x of canon) {
    const e = x.ent;
    if (e.size <= SMALL) {
      if (pack && (pack.usize + e.size > CHUNK || packTier !== x.tier)) flush();
      if (!pack) {
        pack = { members: [], usize: 0, group: x.tier, hint: 'binary' };
        packTier = x.tier;
      }
      const hint = hintOf(e.p);
      if (pack.members.length === 0) pack.hint = hint;
      else if (pack.hint !== hint) pack.hint = 'binary';
      place.set(e.sha, { first: plan.length, off: pack.usize });
      pack.members.push({ ent: e, off: pack.usize, len: e.size, srcOff: 0 });
      pack.usize += e.size;
    } else {
      flush();
      const n = Math.ceil(e.size / CHUNK);
      place.set(e.sha, { first: plan.length, off: -1 });
      for (let i = 0; i < n; i++) {
        const len = Math.min(CHUNK, e.size - i * CHUNK);
        plan.push({ members: [{ ent: e, off: 0, len, srcOff: i * CHUNK }], usize: len, group: x.tier, hint: hintOf(e.p) });
      }
    }
  }
  flush();
  console.log(`inventory: ${ents.length} entries (data ${data.length}, stub ${stubs.length}); unique contents ${canon.length}; chunks planned ${plan.length}`);

  return { ents, stubs, data, canon, plan, place, t0 };
}

type Ctx = ReturnType<typeof main>;

async function readMember(m: PlanChunk['members'][number]): Promise<Buffer> {
  const fh = await fsp.open(m.ent.disk, 'r');
  try {
    const buf = Buffer.allocUnsafe(m.len);
    const { bytesRead } = await fh.read(buf, 0, m.len, m.srcOff);
    if (bytesRead !== m.len) throw new Error('short read ' + m.ent.disk);
    return buf;
  } finally {
    await fh.close();
  }
}

async function compress(buf: Buffer, hint: PlanChunk['hint']): Promise<{ codec: number; data: Buffer }> {
  if (CODEC === 'raw' || hint === 'incompressible') return { codec: 0, data: buf };
  const pick = async (b: Buffer, q: number) =>
    CODEC === 'zstd'
      ? zstd(b, { params: { [c.ZSTD_c_compressionLevel]: q === 11 ? 19 : q } })
      : brotli(b, {
          params: {
            [c.BROTLI_PARAM_QUALITY]: q,
            [c.BROTLI_PARAM_LGWIN]: 22,
            [c.BROTLI_PARAM_SIZE_HINT]: b.length,
            [c.BROTLI_PARAM_MODE]: hint === 'text' ? c.BROTLI_MODE_TEXT : c.BROTLI_MODE_GENERIC,
          },
        });
  // 圧縮不能の早期判定 (先頭 64KiB を低品質で試す)
  if (buf.length > 256 * 1024) {
    const probe = await pick(buf.subarray(0, 64 * 1024), 3);
    if (probe.length > 0.985 * 64 * 1024) return { codec: 0, data: buf };
  }
  const out = await pick(buf, QUALITY);
  if (out.length > 0.97 * buf.length) return { codec: 0, data: buf };
  return { codec: CODEC === 'zstd' ? 2 : 1, data: out };
}

async function run(ctx: Ctx) {
  const { plan, canon, place, stubs, ents } = ctx;
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(path.join(OUT, 'c'), { recursive: true });
  fs.mkdirSync(path.join(OUT, 'm'), { recursive: true });
  const ids: string[] = new Array(plan.length);
  const U: number[] = new Array(plan.length);
  const C: number[] = new Array(plan.length);
  const K: number[] = new Array(plan.length);
  const written = new Map<string, { codec: number; csize: number }>();
  const objects: { key: string; file: string; size: number; ce: string | null }[] = [];
  let next = 0;
  let done = 0;
  let storedBytes = 0;
  let dedupeSaved = 0;
  const tCompress0 = Date.now();
  const worker = async () => {
    for (;;) {
      const i = next++;
      if (i >= plan.length) return;
      const pc = plan[i];
      let buf: Buffer;
      if (pc.members.length === 1) buf = await readMember(pc.members[0]);
      else {
        buf = Buffer.allocUnsafe(pc.usize);
        const parts = await Promise.all(pc.members.map(readMember));
        parts.forEach((p, j) => p.copy(buf, pc.members[j].off));
      }
      const id = crypto.createHash('sha256').update(buf).digest('hex').slice(0, 32);
      ids[i] = id;
      U[i] = buf.length;
      const prev = written.get(id);
      if (prev) {
        C[i] = prev.csize;
        K[i] = prev.codec;
        dedupeSaved += buf.length;
      } else {
        const marker = { codec: -1, csize: 0 };
        written.set(id, marker);
        const { codec, data } = await compress(buf, pc.hint);
        marker.codec = codec;
        marker.csize = data.length;
        const ext = ['raw', 'br', 'zst'][codec];
        const key = `c/${id.slice(0, 2)}/${id}.${ext}`;
        const file = path.join(OUT, key);
        fs.mkdirSync(path.dirname(file), { recursive: true });
        await fsp.writeFile(file, data);
        C[i] = data.length;
        K[i] = codec;
        storedBytes += data.length;
        objects.push({ key, file, size: data.length, ce: codec === 1 ? 'br' : codec === 2 ? 'zstd' : null });
      }
      done++;
      if (done % 500 === 0) console.log(`  chunks ${done}/${plan.length}  ${((Date.now() - tCompress0) / 1000).toFixed(0)}s`);
    }
  };
  await Promise.all(Array.from({ length: CONC }, worker));
  const compressSec = (Date.now() - tCompress0) / 1000;

  // ---- tree ----
  const tree: DirEntry = {};
  const put = (p: string, entry: FileEntry) => {
    const parts = p.split('/');
    let d = tree;
    for (let i = 0; i < parts.length - 1; i++) {
      let n = d[parts[i]];
      if (!n) n = d[parts[i]] = {};
      if (Array.isArray(n)) throw new Error('file/dir conflict ' + p);
      d = n as DirEntry;
    }
    d[parts[parts.length - 1]] = entry;
  };
  for (const e of ents) {
    if (e.cat === 'exec') put(e.p, [e.size, -1, -1, 1]);
    else if (e.size === 0) put(e.p, [0]);
    else {
      const pl = place.get(e.sha)!;
      put(e.p, [e.size, pl.first, pl.off]);
    }
  }
  // groups: tier ごとの連続 chunk 範囲
  const groups: Record<string, [number, number][]> = {};
  plan.forEach((pc, i) => {
    const g = (groups[pc.group] ??= []);
    const last = g[g.length - 1];
    if (last && last[0] + last[1] === i) last[1]++;
    else g.push([i, 1]);
  });
  const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
  const man: Manifest = {
    v: 1,
    name: NAME,
    created: new Date().toISOString(),
    chunkSize: CHUNK,
    smallMax: SMALL,
    layout: 'objects',
    chunks: { n: plan.length, id: ids.join(''), u: U, c: C, k: K },
    groups,
    tree,
    stats: {
      files: ents.length,
      stubs: stubs.length,
      uniqueContents: canon.length,
      chunks: plan.length,
      uniqueChunks: written.size,
      usizeTotal: sum(U),
      csizeTotalDedupedObjects: storedBytes,
      codec: CODEC,
      quality: QUALITY,
    },
  };
  const mjson = Buffer.from(JSON.stringify(man));
  const mbr = await brotli(mjson, { params: { [c.BROTLI_PARAM_QUALITY]: 11, [c.BROTLI_PARAM_LGWIN]: 24 } });
  const mid = crypto.createHash('sha256').update(mjson).digest('hex').slice(0, 16);
  const mkey = `m/${mid}.json`;
  fs.writeFileSync(path.join(OUT, mkey), mbr);
  const latest = Buffer.from(JSON.stringify({ manifest: mkey, usize: mjson.length, size: mbr.length, name: NAME, chunkSize: CHUNK, created: man.created }));
  fs.writeFileSync(path.join(OUT, 'latest.json'), latest);

  const CC_IMM = 'public, max-age=31536000, immutable';
  const plan2 = [
    ...objects.map((o) => ({ key: o.key, size: o.size, contentType: 'application/octet-stream', contentEncoding: o.ce, cacheControl: CC_IMM })),
    { key: mkey, size: mbr.length, contentType: 'application/json', contentEncoding: 'br', cacheControl: CC_IMM },
    { key: 'latest.json', size: latest.length, contentType: 'application/json', contentEncoding: null, cacheControl: 'public, max-age=60, stale-while-revalidate=600' },
  ];
  fs.writeFileSync(path.join(OUT, 'upload-plan.json'), JSON.stringify(plan2));

  // 集計
  const groupStats: Record<string, { chunks: number; usize: number; csize: number }> = {};
  plan.forEach((pc, i) => {
    const g = (groupStats[pc.group] ??= { chunks: 0, usize: 0, csize: 0 });
    g.chunks++;
    g.usize += U[i];
    g.csize += C[i];
  });
  const codecCount = [0, 0, 0];
  const codecBytes = [0, 0, 0];
  const seen = new Set<string>();
  plan.forEach((_, i) => {
    if (seen.has(ids[i])) return;
    seen.add(ids[i]);
    codecCount[K[i]]++;
    codecBytes[K[i]] += C[i];
  });
  const uniqObjs = objects.length;
  const smallObjs = plan.filter((p) => p.members.length > 1).length;
  const stats = {
    name: NAME,
    chunkSize: CHUNK,
    smallMax: SMALL,
    codec: CODEC,
    quality: QUALITY,
    inventoryEntries: ents.length,
    stubEntries: stubs.length,
    dataEntries: ctx.data.length,
    uniqueContents: canon.length,
    contentBytesUnique: canon.reduce((a, x) => a + x.ent.size, 0),
    chunksPlanned: plan.length,
    packChunks: smallObjs,
    objects: uniqObjs,
    usizeSumPlanned: sum(U),
    storedBytes,
    ratio: storedBytes / sum(U),
    dedupeSavedUsize: dedupeSaved,
    codecObjects: { raw: codecCount[0], br: codecCount[1], zst: codecCount[2] },
    codecStoredBytes: { raw: codecBytes[0], br: codecBytes[1], zst: codecBytes[2] },
    groups: groupStats,
    manifest: { key: mkey, jsonBytes: mjson.length, brBytes: mbr.length },
    compressSec,
    totalSec: (Date.now() - ctx.t0) / 1000,
  };
  fs.writeFileSync(path.join(OUT, 'stats.json'), JSON.stringify(stats, null, 1));
  console.log(JSON.stringify(stats, null, 1));
}

run(main()).catch((e) => {
  console.error(e);
  process.exit(1);
});
