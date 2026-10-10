// bundle.mjs — CAB-216: h4 e2e のブラウザバンドル (esbuild)。
//   node h4/bundle.mjs <outDir>
// esbuild は tools/assets/node_modules にのみあるため絶対パス指定で import する。
// (tools/assets・tools/shimx は読取専用。bundle は nfo/h4/work/ に出力する。)
import { build } from '../../assets/node_modules/esbuild/lib/main.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..'); // tools/hostbridge/nfo
const out = path.resolve(process.argv[2] ?? path.join(ROOT, 'work', 'app-h4'));

await build({
  entryPoints: { 'seed-page': 'h4/seed_page.ts', 'seed-worker': 'h4/seed_worker.ts' },
  outdir: out,
  bundle: true,
  format: 'esm',
  target: 'es2022',
  platform: 'browser',
  external: ['node:*'],
  logLevel: 'warning',
  absWorkingDir: ROOT,
});
console.log(`bundled -> ${out}`);
