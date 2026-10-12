// e2e 用の 1 ファイル asset パッケージを作る: 314MB 級 wasm (tools/perf/work/huge/k100.wasm) を
// 本物の pack.ts で chunk 化し (Engine/FLEngine.wasm として)、期待値 (size/sha256) を出す。
//   node test/make-asset-pkg.ts [--src <path>] [--quality 3]
// 出力: work/pkg-asset/{c/,m/,latest.json} + work/asset-expected.json
// 冪等: 既に pkg-asset があれば再構築しない (--force で再構築)。
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { REPO_ROOT } from '../../shared/paths.mjs';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..');
const SRC = path.resolve(root, A.src ?? `${REPO_ROOT}/tools/perf/work/huge/k100.wasm`);
const OUT = path.resolve(root, 'work/pkg-asset');
const FORCE = process.argv.includes('--force');

if (!fs.existsSync(SRC)) {
  console.error(`source wasm not found: ${SRC} (tools/perf の huge wasm を参照。無ければ --src で指定)`);
  process.exit(2);
}

const expectedPath = path.join(root, 'work/asset-expected.json');
if (fs.existsSync(OUT) && fs.existsSync(expectedPath) && !FORCE) {
  console.log('pkg-asset exists (skip build):', OUT);
  process.exit(0);
}

// hardlink で実体コピーを避ける (work/ は gitignore)
const localBin = path.join(root, 'work/k100.wasm');
fs.mkdirSync(path.dirname(localBin), { recursive: true });
fs.rmSync(localBin, { force: true });
try {
  fs.linkSync(SRC, localBin);
} catch {
  fs.copyFileSync(SRC, localBin);
}
const size = fs.statSync(localBin).size;
const sha = await new Promise<string>((res, rej) => {
  const h = crypto.createHash('sha256');
  fs.createReadStream(localBin)
    .on('data', (d) => h.update(d))
    .on('end', () => res(h.digest('hex')))
    .on('error', rej);
});

const invPath = path.join(root, 'work/inv_asset.jsonl');
const tiersPath = path.join(root, 'work/tiers_asset.json');
fs.writeFileSync(invPath, JSON.stringify({ p: 'Engine/FLEngine.wasm', size, disk: localBin, sha, cat: 'data', cls: 'data' }) + '\n');
fs.writeFileSync(tiersPath, JSON.stringify({ 'Engine/FLEngine.wasm': 'T1' }));

console.log(`packing ${localBin} (${(size / 1e6).toFixed(1)} MB, sha256 ${sha.slice(0, 16)}…)`);
execFileSync(process.execPath, [path.join(root, 'pack/pack.ts'), '--inv', 'work/inv_asset.jsonl', '--tiers', work_rel(tiersPath), '--out', 'work/pkg-asset', '--codec', 'br', '--quality', A.quality ?? '3', '--name', 'asset-e2e'], { cwd: root, stdio: 'inherit' });

fs.writeFileSync(expectedPath, JSON.stringify({ path: 'Engine/FLEngine.wasm', size, sha256: sha, pkg: 'work/pkg-asset', src: SRC }, null, 1));
console.log('expected:', expectedPath);

function work_rel(p: string): string {
  return path.relative(root, p);
}
