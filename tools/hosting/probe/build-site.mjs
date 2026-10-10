// build-site.mjs — work/data (gen-data.mjs の出力) から配備用ディレクトリを組み立てる
//   work/dist-s : Workers Static Assets / Pages 共通 (pages: /s /b-cl /b-rc /plain, data: /d, _headers)
//   work/r2     : R2 へ置くキー群 + work/r2/upload.json (key,file,contentType,cacheControl)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const WORK = path.resolve(here, '../work');
const DATA = path.join(WORK, 'data');
const LIB = path.join(here, 'site/lib');
const cp = (from, to) => { fs.mkdirSync(path.dirname(to), { recursive: true }); fs.copyFileSync(from, to); };
const rm = (p) => fs.rmSync(p, { recursive: true, force: true });

const INDEX = '<!doctype html><meta charset="utf-8"><title>probe</title><pre id="o">running (see window.__probe)</pre><script type="module" src="./probe.js"></script>\n';
const LIBFILES = ['probe.js', 'probe-worker.js', 'probe-worklet.js'];

// ---- dist-s (static assets / pages)
const S = path.join(WORK, 'dist-s');
rm(S);
for (const v of ['s', 'b-cl', 'b-rc', 'plain', 'nohdr']) {
  fs.mkdirSync(path.join(S, v), { recursive: true });
  fs.writeFileSync(path.join(S, v, 'index.html'), INDEX);
  for (const f of LIBFILES) cp(path.join(LIB, f), path.join(S, v, f));
}
fs.writeFileSync(path.join(S, 'index.html'), '<!doctype html><title>signature-studio hosting probe</title><ul><li><a href="/s/">/s/</a></li><li><a href="/b-cl/">/b-cl/</a></li><li><a href="/b-rc/">/b-rc/</a></li></ul>\n');
// 静的 assets/pages には ≤25MiB のものだけ (big-100m.bin / over-26m.bin は置かない)
const man = JSON.parse(fs.readFileSync(path.join(DATA, 'probe-manifest.json'), 'utf8'));
const dFiles = [...man.wasmParts.parts.map((x) => x.path), 'part-24m.bin', 'probe-manifest.json', 'x.raw', 'x.br', 'x.zst', 'probe.wasm', 'pixel.png', ...man.chunks.map((c) => c.path)];
for (const f of dFiles) cp(path.join(DATA, f), path.join(S, 'd', f));
const iso = (coep) => `  Cross-Origin-Opener-Policy: same-origin\n  Cross-Origin-Embedder-Policy: ${coep}\n  Cross-Origin-Resource-Policy: same-origin\n`;
fs.writeFileSync(
  path.join(S, '_headers'),
  `/nohdr/\n${iso('require-corp')}\n/nohdr/index.html\n${iso('require-corp')}\n/s/*\n${iso('require-corp')}  X-Probe-Dup: more\n\n/b-cl/*\n${iso('credentialless')}\n/b-rc/*\n${iso('require-corp')}\n/d/c/*\n  Cache-Control: public, max-age=31536000, immutable\n\n# _headers の重複ヘッダ挙動の検証 (カンマ連結 / ! で除去後の再設定)\n/*\n  X-Probe-Dup: base\n/b-cl/*\n  ! X-Probe-Dup\n  X-Probe-Dup: replaced\n`,
);

// ---- r2 (案 A の HTML 含む。案 B/C の cross-origin data は同じ d/ を r2.dev から読む)
const R = path.join(WORK, 'r2');
rm(R);
const up = [];
const put = (key, file, contentType, cacheControl) => { cp(file, path.join(R, key)); up.push({ key, contentType, cacheControl: cacheControl ?? null }); };
const CT = { html: 'text/html; charset=utf-8', js: 'text/javascript; charset=utf-8', json: 'application/json', wasm: 'application/wasm', png: 'image/png' };
const ct = (n) => CT[n.split('.').pop()] ?? 'application/octet-stream';
put('a/index.html', path.join(S, 's/index.html'), CT.html);
for (const f of LIBFILES) put(`a/${f}`, path.join(LIB, f), CT.js);
for (const f of ['big-100m.bin', ...dFiles]) {
  put(`d/${f}`, path.join(DATA, f), ct(f), f.startsWith('c/') ? 'public, max-age=31536000, immutable' : null);
}
fs.writeFileSync(path.join(R, 'upload.json'), JSON.stringify(up));
const sz = (d) => { let n = 0, c = 0; (function w(p) { for (const e of fs.readdirSync(p, { withFileTypes: true })) { const q = path.join(p, e.name); if (e.isDirectory()) w(q); else { n += fs.statSync(q).size; c++; } } })(d); return { files: c, bytes: n }; };
console.log(JSON.stringify({ distS: sz(S), r2: sz(R), r2Objects: up.length }));
