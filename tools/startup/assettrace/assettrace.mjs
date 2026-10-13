// assettrace.mjs — boot 中のファイル要求 trace (JSONL) から「起動必須 asset の最小集合」を作る (ST-T5 / #105)。
//
// trace 形式 v1 (1 行 1 JSON。shimx の CreateFile/FindFirstFile 系フックが出す想定):
//   {"op":"open"|"stat"|"enum","path":"<Win パス (UTF-8) または POSIX 絶対パス>","ok":true|false,"w":false}
//   enum の path は "dir\\*.ext" 形 (最終要素にワイルドカード可)。w=true は書込み open。
// 写像は pathreg JS ミラー (C の pathreg_map と 16 fixture で一致済み) をそのまま使う。
//
// 出力 (JSON):
//   files   : /fl (RO asset) 配下で ok に読まれた tree 相対パス (inventory に実在するもののみ)
//   unknown : 読めたと trace にあるが inventory に無い /fl パス (inventory 不足 or 生成物)
//   missing : /fl で探して ok=false だったパス (manifest に載せない)
//   dirs    : enum された /fl ディレクトリ (展開後の files 件数付き)
//   other   : /fl 以外の行き先ごとの件数 (persist / tmp / unmapped)
//   roWrites: /fl への書込み open (RO 違反。あれば異常)
import fs from 'node:fs';
import { createMapper } from '../../shimx/pathreg/js/pathmap.mjs';

const ROOT = '/fl';

export function parseTrace(text) {
  const out = [];
  text.split('\n').forEach((line, i) => {
    const s = line.trim();
    if (!s || s[0] !== '{') return;
    let o;
    try { o = JSON.parse(s); } catch { throw new Error(`trace line ${i + 1}: invalid JSON`); }
    if (!['open', 'stat', 'enum'].includes(o.op) || typeof o.path !== 'string') throw new Error(`trace line ${i + 1}: bad op/path`);
    out.push({ seq: out.length, op: o.op, path: o.path, ok: o.ok !== false, w: !!o.w });
  });
  return out;
}

function wildcardRx(pat) {
  const r = [...pat].map((c) => (c === '*' ? '.*' : c === '?' ? '.' : c.replace(/[.+^${}()|[\]\\]/g, '\\$&'))).join('');
  return new RegExp(`^${r}$`, 'i');
}

/** inv: [{p, size?, tier?}] (p = tree 相対 '/' 区切り)。大小無視で照合し元ケースを返す */
export function analyze(events, inv, { mapper = createMapper() } = {}) {
  const byLower = new Map(inv.map((e) => [e.p.toLowerCase(), e]));
  const childrenOf = new Map(), dirSet = new Set();
  for (const e of inv) {
    const k = e.p.includes('/') ? e.p.slice(0, e.p.lastIndexOf('/')).toLowerCase() : '';
    if (!childrenOf.has(k)) childrenOf.set(k, []);
    childrenOf.get(k).push(e);
    for (let i = e.p.indexOf('/'); i >= 0; i = e.p.indexOf('/', i + 1)) dirSet.add(e.p.slice(0, i).toLowerCase());
  }
  const files = new Map(), unknown = new Map(), missing = new Map(), dirs = new Map();
  const other = { persist: 0, tmp: 0, unmapped: 0 }, roWrites = [];
  const seen = (m, key, ev, extra = {}) => {
    const k = key.toLowerCase(), v = m.get(k);
    if (v) v.n++; else m.set(k, { path: key, first: ev.seq, n: 1, ...extra });
  };

  for (const ev of events) {
    const posix = ev.path.startsWith('/') ? ev.path.replaceAll('\\', '/') : mapper.map(ev.path);
    if (!posix) { other.unmapped++; continue; }
    if (posix !== ROOT && !posix.toLowerCase().startsWith(ROOT + '/')) {
      other[posix.toLowerCase().startsWith('/c/tmp') ? 'tmp' : 'persist']++;
      continue;
    }
    let rel = posix.slice(ROOT.length + 1);
    if (ev.w) { roWrites.push({ seq: ev.seq, path: rel }); continue; }
    if (ev.op === 'enum') {
      const slash = rel.lastIndexOf('/');
      const dir = slash < 0 ? '' : rel.slice(0, slash), pat = rel.slice(slash + 1);
      if (!ev.ok) { seen(missing, rel, ev); continue; }
      const hit = (childrenOf.get(dir.toLowerCase()) || []).filter((e) => wildcardRx(pat).test(e.p.slice(dir ? dir.length + 1 : 0)));
      seen(dirs, `${dir}/${pat}`, ev, { matched: hit.length });
      for (const e of hit) seen(files, e.p, ev, { via: 'enum' });
      continue;
    }
    if (!ev.ok) { seen(missing, rel, ev); continue; }
    const e = byLower.get(rel.toLowerCase());
    if (e) seen(files, e.p, ev, { via: ev.op });
    else if (!dirSet.has(rel.toLowerCase()) && rel !== '') seen(unknown, rel, ev);   // dir の stat/open は asset 扱いしない
  }
  const arr = (m) => [...m.values()].sort((a, b) => a.first - b.first);
  const f = arr(files).map((x) => ({ ...x, size: byLower.get(x.path.toLowerCase()).size ?? null, tier: byLower.get(x.path.toLowerCase()).tier ?? null }));
  return { files: f, unknown: arr(unknown), missing: arr(missing), dirs: arr(dirs), other, roWrites };
}

/** 観測済みファイルを T0 に固定した tiers (pack.ts --tiers 入力 = path→tier)。base に無いパスは T2 扱い */
export function observedTiers(result, baseTiers = {}) {
  const t = { ...baseTiers };
  for (const f of result.files) t[f.path] = 'T0';
  return t;
}

/** 静的推定 tier (bootset) との差分。promote = 実測で必要だったのに T0 でない / unseen = T0・T0p なのに未観測 */
export function diffTiers(result, inv) {
  const seen = new Set(result.files.map((f) => f.path.toLowerCase()));
  const promote = result.files.filter((f) => f.tier && f.tier !== 'T0').map((f) => ({ path: f.path, from: f.tier }));
  const unseen = inv.filter((e) => (e.tier === 'T0' || e.tier === 'T0p') && !seen.has(e.p.toLowerCase())).length;
  return { promote, unseenT0: unseen };
}

export function loadInventory(invPath, tiersPath) {
  const tiers = tiersPath && fs.existsSync(tiersPath) ? JSON.parse(fs.readFileSync(tiersPath, 'utf8')) : {};
  const inv = [];
  for (const l of fs.readFileSync(invPath, 'utf8').split('\n')) {
    if (!l) continue;
    const e = JSON.parse(l);
    if (e.cat === 'exec') continue;
    inv.push({ p: e.p, size: e.size, tier: tiers[e.p] ?? null });
  }
  return inv;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = Object.fromEntries(process.argv.slice(2).reduce((acc, v, i, arr) => (v.startsWith('--') ? [...acc, [v.slice(2), arr[i + 1]]] : acc), []));
  if (!a.trace || !a.inv) { console.error('usage: node assettrace.mjs --trace t.jsonl --inv work/inv_win.jsonl [--tiers work/tiers.json] [--out result.json] [--tiers-out tiers_observed.json]'); process.exit(2); }
  const inv = loadInventory(a.inv, a.tiers);
  const res = analyze(parseTrace(fs.readFileSync(a.trace, 'utf8')), inv);
  const out = { schema: 1, events: parseTrace(fs.readFileSync(a.trace, 'utf8')).length, ...res, tierDiff: diffTiers(res, inv) };
  if (a.out) fs.writeFileSync(a.out, JSON.stringify(out, null, 1)); else console.log(JSON.stringify(out, null, 1));
  if (a['tiers-out']) fs.writeFileSync(a['tiers-out'], JSON.stringify(observedTiers(res, a.tiers ? JSON.parse(fs.readFileSync(a.tiers, 'utf8')) : {})));
  console.error(`[assettrace] files=${res.files.length} unknown=${res.unknown.length} missing=${res.missing.length} roWrites=${res.roWrites.length}`);
  process.exit(res.roWrites.length ? 1 : 0);
}
