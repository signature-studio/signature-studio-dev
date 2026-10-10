#!/usr/bin/env node
// headers-from-policy.mjs — deploy/config/edge-policy.json (配信ポリシー正本, 読取専用) から Workers Static Assets / Pages 用 `_headers` を生成する。
//   node tools/hosting/headers-from-policy.mjs [--policy <json>] [--out <dist>/_headers] [--check]
//
// 変換規則 (Transform Rules との差分は REPORT.md §手順書 を参照):
//   match {}            -> /*
//   match.path[]        -> 完全一致。"/" は Static Assets が /index.html を 307 -> / にするので "/" と "/index.html" の両方に付ける
//   match.pathPrefix[]  -> <prefix>*
//   match.ext[]         -> /*.<ext>
//   match.status        -> 表現不可 (無視。警告)。`_headers` は 200/206/304/404 の全応答に付く
//   `_headers` のセマンティクス (実エッジで実測, probe/pol-test.sh):
//     - 同名ヘッダは上書きでなく追加される (Cache-Control が二重になる)
//     - 完全一致と splat が重なる場合の連結順は一定でない (実測: "/" では no-cache が先、"/wasm/manifest.json" では immutable が先)。
//       `! H` は splat 同士 (ファイル順) でのみ先行 splat の H を除去できた。完全一致ブロックの `! H` では /* の値を消せなかった
//   => Transform Rules の「後勝ち」は再現できない。そこで:
//     * 全パス対象の Cache-Control (cache-default) は出力しない (Static Assets 既定 `public, max-age=0, must-revalidate`+ETag が同等以上に厳格)
//     * immutable prefix は splat のみ。document 用の完全一致 `no-cache` は immutable と連結される (`no-cache, ..., immutable`) が no-cache が支配するので意図通り
//     * `! H` は splat -> splat の上書きにのみ使う
// 制約検査: ブロック数 <= 100, 1 行 <= 2000 文字, `*` は 1 パターンに 1 個。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const policyPath = opt('policy', path.resolve(here, '../../deploy/config/edge-policy.json'));
const out = opt('out');
const policy = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
const warn = [];

function patternsOf(match) {
  const ps = [];
  if (match.path) for (const p of match.path) { ps.push(p); if (p === '/') ps.push('/index.html'); }
  if (match.pathPrefix) for (const x of match.pathPrefix) ps.push(`${x}*`);
  if (match.ext) for (const e of match.ext) ps.push(`/*.${e}`);
  if (match.pathSuffix) warn.push(`pathSuffix ${match.pathSuffix} は _headers で表現不可`);
  if (!match.path && !match.pathPrefix && !match.ext && !match.pathSuffix) ps.push('/*');
  return [...new Set(ps)];
}

const blocks = [];
const seenSplat = new Set(); // 先行 splat ブロックが設定済みのヘッダ名
for (const r of policy.responseHeaders) {
  if (r.match.status) warn.push(`rule ${r.id}: status 条件 ${JSON.stringify(r.match.status)} は無視 (全応答に付与)`);
  const blanket = !r.match.path && !r.match.pathPrefix && !r.match.ext && !r.match.pathSuffix;
  const set = { ...r.set };
  if (blanket && 'Cache-Control' in set) {
    warn.push(`rule ${r.id}: 全パスの Cache-Control は出力しない (Static Assets 既定 "public, max-age=0, must-revalidate" を使う。元: ${set['Cache-Control']})`);
    delete set['Cache-Control'];
    if (Object.keys(set).length === 0) continue;
  }
  for (const p of patternsOf(r.match)) {
    const isSplat = p.includes('*');
    const lines = [];
    for (const [k, v] of Object.entries(set)) {
      if (isSplat && seenSplat.has(k.toLowerCase())) lines.push(`  ! ${k}`);
      lines.push(`  ${k}: ${v}`);
    }
    blocks.push({ id: r.id, pattern: p, lines, isSplat });
  }
  if (patternsOf(r.match).some((p) => p.includes('*'))) for (const k of Object.keys(set)) seenSplat.add(k.toLowerCase());
}

// 同一パターンのブロックは 1 つに統合する (Pages は同一パターンの重複ブロックを後勝ちで上書きする: 実測)
const merged = new Map();
for (const b of blocks) {
  const m = merged.get(b.pattern);
  if (m) { m.lines.push(...b.lines); m.id += `+${b.id}`; } else merged.set(b.pattern, { ...b, lines: [...b.lines] });
}
blocks.length = 0;
blocks.push(...merged.values());

const text =
  `# 自動生成: tools/hosting/headers-from-policy.mjs (正本 ${path.relative(process.cwd(), policyPath)})\n` +
  blocks.map((b) => `# ${b.id}\n${b.pattern}\n${b.lines.join('\n')}\n`).join('\n');

const errs = [];
if (blocks.length > 100) errs.push(`ブロック数 ${blocks.length} > 100`);
for (const l of text.split('\n')) if (l.length > 2000) errs.push(`行が 2000 文字超: ${l.slice(0, 40)}`);
for (const b of blocks) if ((b.pattern.match(/\*/g) ?? []).length > 1) errs.push(`splat が複数: ${b.pattern}`);

// --check: `_headers` の累積/除去セマンティクス (実測: 同名は追加、"! H" で除去) を模擬し、policy の「後勝ち」評価と突合
const toRe = (pattern) => new RegExp('^' + pattern.split('*').map((s) => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*') + '$');
function simulateHeadersFile(p) {
  const h = new Map();
  for (const b of [...blocks.filter((x) => !x.isSplat), ...blocks.filter((x) => x.isSplat)]) {
    if (!toRe(b.pattern).test(p)) continue;
    for (const l of b.lines) {
      const t = l.trim();
      if (t.startsWith('! ')) h.delete(t.slice(2).toLowerCase());
      else {
        const i = t.indexOf(': ');
        const k = t.slice(0, i), v = t.slice(i + 2);
        const e = h.get(k.toLowerCase()) ?? [k, []];
        e[1].push(v);
        h.set(k.toLowerCase(), e);
      }
    }
  }
  return Object.fromEntries([...h.values()].map(([k, v]) => [k.toLowerCase(), v.join(', ')]));
}
// Cache-Control は意図的差異を許容: 既定(max-age=0, must-revalidate)は max-age=300 より厳格 / no-cache は連結されても支配的
export function equivalent(k, got, want) {
  if (got === want) return true;
  if (k !== 'cache-control') return false;
  if (want === 'no-cache') return /(^|,\s*)no-cache/.test(got ?? '');
  if (want === 'public, max-age=300, must-revalidate') return got === undefined || got === 'public, max-age=0, must-revalidate';
  return false;
}
const mismatches = [];
if (args.includes('--check')) {
  const { matches } = await import(path.resolve(here, '../../deploy/lib/policy.mjs'));
  const samples = new Set(['/', '/index.html', '/release.json', '/wasm/manifest.json', '/favicon.ico', '/worklets/fl-audio-worklet.js']);
  for (const r of policy.responseHeaders) {
    for (const p of r.match.path ?? []) samples.add(p);
    for (const x of r.match.pathPrefix ?? []) { samples.add(`${x}a.bin`); samples.add(`${x}c/ab/abcdef.raw`); samples.add(`${x}app.js`); }
    for (const e of r.match.ext ?? []) samples.add(`/x/y.${e}`);
  }
  for (const s of samples) {
    const a = simulateHeadersFile(s);
    const b = {};
    for (const r of policy.responseHeaders) {
      if (matches({ ...r.match, status: undefined }, { path: s, status: 200 })) for (const [k, v] of Object.entries(r.set)) b[k.toLowerCase()] = v;
    }
    const eq = (k) => equivalent(k, a[k], b[k]);
    if (![...new Set([...Object.keys(a), ...Object.keys(b)])].every(eq)) mismatches.push({ path: s, headersFile: a, policy: b });
  }
}

if (out) fs.writeFileSync(out, text); else process.stdout.write(text);
process.stderr.write(JSON.stringify({ blocks: blocks.length, bytes: text.length, warnings: warn, errors: errs, checked: args.includes('--check'), mismatches }, null, 1) + '\n');
process.exit(errs.length || mismatches.length ? 1 : 0);
