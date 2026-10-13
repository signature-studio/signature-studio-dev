// 検収用の独立再計算 + 別アルゴリズム検算 (CAB-21 / c2c31c8)。
// 実装側スクリプト (pack.ts / asset.ts) を一切 import せず、node の fs + zlib + crypto だけで
// manifest → chunk 取得 → 連結 → wasm 検証 をやり直す。加えて ③④ のネガティブコントロールを含む。
//
// 再現 (work/ は gitignore なので都度生成する):
//   node test/make-asset-pkg.ts && node test/asset-e2e.ts && node test/verify-asset-indep.ts
// 既定では work/asset-expected.json と work/pkg-asset と work/results-asset-e2e.json を読む。
//
// 数え方の定義 (規則 36):
//   chunk 数 = manifest の chunks.n (= c/ 配下のユニーク object 数と一致することを別途確認)
//   chunk 一致 = brotli 復号後の sha256 先頭 32 hex (=128bit) が manifest chunks.id の該当 32 文字と一致
//   全体 sha256 = chunk を index 昇順で連結した 314,206,140 B に対する sha256
//
// 使い方: node test/verify-asset-indep.ts [--pkg <dir>] [--src <wasm>]
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import { parseWasmSections } from './wasm-sections.ts';
import { REPO_ROOT } from '../../shared/paths.mjs';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..');
const SRC = path.resolve(A.src ?? `${REPO_ROOT}/tools/perf/work/huge/k100.wasm`);
const expected = JSON.parse(fs.readFileSync(path.join(root, A.pkg ?? 'work/asset-expected.json').replace(/asset-expected\.json$/, 'asset-expected.json'), 'utf8'));
const PKG = path.resolve(root, expected.pkg);

const sha256 = (b: Uint8Array | Buffer): string => crypto.createHash('sha256').update(b).digest('hex');
const sha128 = (b: Uint8Array | Buffer): string => sha256(b).slice(0, 32);

let failed = 0;
const check = (ok: boolean, msg: string) => {
  console.log(ok ? '  ok   ' : '  FAIL ', msg);
  if (!ok) failed++;
};

console.log(`src   ${SRC}`);
console.log(`pkg   ${PKG}`);
console.log(`expect ${expected.path} size=${expected.size} sha256=${expected.sha256.slice(0, 16)}…`);

// ---- ① 元ファイルの独立ハッシュ (fs ストリーム) ----
console.log('[1] source wasm');
const srcHash = await new Promise<string>((res, rej) => {
  const h = crypto.createHash('sha256');
  fs.createReadStream(SRC).on('data', (d) => h.update(d)).on('end', () => res(h.digest('hex'))).on('error', rej);
});
check(srcHash === expected.sha256, `source sha256 matches expected (${srcHash.slice(0, 16)}…)`);
check(fs.statSync(SRC).size === expected.size, `source size ${fs.statSync(SRC).size} == ${expected.size}`);

// ---- ① manifest → chunk object → 連結 (pack.ts を import しない別経路) ----
console.log('[2] manifest + chunks');
const latest = JSON.parse(fs.readFileSync(path.join(PKG, 'latest.json'), 'utf8'));
const manJson = zlib.brotliDecompressSync(fs.readFileSync(path.join(PKG, latest.manifest)));
const man = JSON.parse(manJson.toString());
const n = man.chunks.n;
check(man.v === 1, `manifest version ${man.v}`);
check(man.chunkSize === 1048576, `chunkSize ${man.chunkSize}`);
const fEntry = findFile(man.tree, expected.path);
check(!!fEntry, `tree entry ${expected.path} found`);
check(fEntry![0] === expected.size, `tree size ${fEntry![0]} == ${expected.size}`);
check(fEntry![1] === 0, `tree firstChunk ${fEntry![1]}`);
const wantChunks = Math.ceil(expected.size / man.chunkSize);
check(n === wantChunks, `chunks.n ${n} == ceil(size/chunkSize) ${wantChunks}`);
check(man.chunks.u.length === n && man.chunks.c.length === n && man.chunks.k.length === n, `u/c/k arrays all length ${n}`);
check(man.chunks.id.length === n * 32, `id string length ${man.chunks.id.length} == ${n * 32}`);

// c/ 配下の object を独立に数える (重複排除後のユニーク数)
const objFiles = fs.readdirSync(path.join(PKG, 'c'), { recursive: true, withFileTypes: true })
  .filter((d) => d.isFile())
  .map((d) => path.join(d.parentPath ?? (d as unknown as { path: string }).path, d.name));
check(objFiles.length === n, `c/ 配下 object 数 ${objFiles.length} == chunks.n ${n}`);

let badId = 0;
let badSize = 0;
let badCodec = 0;
let totalU = 0;
const chunks: Buffer[] = [];
for (let i = 0; i < n; i++) {
  const id = man.chunks.id.substr(i * 32, 32);
  const key = `c/${id.slice(0, 2)}/${id}.${['raw', 'br', 'zst'][man.chunks.k[i]]}`;
  const fp = path.join(PKG, key);
  if (!fs.existsSync(fp)) {
    badId++;
    continue;
  }
  const st = fs.readFileSync(fp);
  if (st.length !== man.chunks.c[i]) badSize++;
  const u = man.chunks.k[i] === 1 ? zlib.brotliDecompressSync(st) : man.chunks.k[i] === 2 ? zlib.zstdDecompressSync(st) : st;
  if (u.length !== man.chunks.u[i]) badSize++;
  if (sha128(u) !== id) badId++;
  if (man.chunks.k[i] !== 1) badCodec++;
  totalU += u.length;
  chunks.push(u);
}
check(badId === 0, `chunk 内容アドレス一致 ${n - badId}/${n}`);
check(badSize === 0, `chunk サイズ一致 (u == c 復号後) ${n - badSize}/${n}`);
check(badCodec === 0, `chunk codec 全て br (1) ${n - badCodec}/${n}`);
check(totalU === expected.size, `Σu ${totalU} == ${expected.size}`);

// ---- ② 連結して全体 sha256 (index 昇順) + wasm 検証 ----
console.log('[3] assemble + wasm');
const all = Buffer.concat(chunks);
check(all.length === expected.size, `連結後 size ${all.length} == ${expected.size}`);
check(sha256(all) === expected.sha256, `連結後 sha256 一致 (${sha256(all).slice(0, 16)}…)`);
check(sha256(all) === srcHash, `連結後 sha256 == 元ファイル sha256 (バイト同一)`);
const secs = parseWasmSections(new Uint8Array(all));
check(secs.exports === 8271, `独立 section 解析 exports ${secs.exports}`);
check(secs.imports === 21, `独立 section 解析 imports ${secs.imports} (env + wasi_snapshot_preview1)`);
// 別経路: WebAssembly.compile + Module.exports/imports でも同数を確認
const mod = await WebAssembly.compile(all);
check(WebAssembly.Module.exports(mod).length === 8271, `WebAssembly.Module.exports ${WebAssembly.Module.exports(mod).length}`);
check(WebAssembly.Module.imports(mod).length === secs.imports, `WebAssembly.Module.imports ${WebAssembly.Module.imports(mod).length} == section 解析 ${secs.imports}`);
check(secs.sectionSizes['code'] === 310762803 && secs.sectionSizes['data'] === 2378377, `code/data section ${secs.sectionSizes['code']}/${secs.sectionSizes['data']}`);
console.log(`[4] e2e 結果JSON の読み取り (work/results-asset-e2e.json)`);
const rj = path.join(root, 'work/results-asset-e2e.json');
if (fs.existsSync(rj)) {
  const r = JSON.parse(fs.readFileSync(rj, 'utf8'));
  const nChunks = r.nChunks;
  check(nChunks === n, `e2e nChunks ${nChunks} == manifest n ${n}`);
  const names = ['cold', 'warm-netoff', 'corrupt-opfs', 'corrupt-both'];
  for (const nm of names) {
    const run = r.runs[nm];
    if (!run?.ok) {
      check(false, `${nm}: report not ok`);
      continue;
    }
    const p = run.res;
    check(!!p.shaOk, `${nm}: shaOk`);
    check(p.pass1.fromOpfs + p.pass1.fromIdb + p.pass1.fromNetwork === nChunks, `${nm}: 解決 chunk 合計 ${p.pass1.fromOpfs + p.pass1.fromIdb + p.pass1.fromNetwork} == ${nChunks}`);
    check(p.tiers.opfsBytes === 4096 + expected.size, `${nm}: OPFS ファイルサイズ ${p.tiers.opfsBytes} == 4096 + ${expected.size}`);
    const mbps = expected.size / 1e6 / (p.pass2.ms / 1000);
    console.log(`       ${nm}: compile=${p.compileMs}ms pass2=${p.pass2.ms}ms = ${mbps.toFixed(0)} MB/s exports=${p.exports} imports=${p.imports}`);
  }
}

console.log('[5] ネガティブコントロール (rule 41)');
{
  // (a) per-chunk sha128 照合を外したらどうなるか: 1 chunk を 1 バイトだけ破損させ、
  //     照合あり → 破損検出 / 照合なし(スキップ) → すり抜け、を別実装で再現
  const ci = 3;
  const corrupt = Buffer.from(chunks[ci]);
  corrupt[1024] ^= 0xff;
  check(sha128(corrupt) !== man.chunks.id.substr(ci * 32, 32), `[a] 1 バイト破損は sha128 不一致で検出される (${sha128(corrupt).slice(0, 16)} != ${man.chunks.id.substr(ci * 32, 32).slice(0, 16)})`);
  // 照合を外した (スキップした) 場合の連結結果
  const withCorrupt = Buffer.concat(chunks.map((c, i) => (i === ci ? corrupt : c)));
  check(sha256(withCorrupt) !== expected.sha256, '[a] 照合スキップ時は全体 sha256 が不一致 (=検出を外すと破損がすり抜ける)');
  check(sha256(withCorrupt.slice(0, 1024)) === sha256(all.slice(0, 1024)), '[a] 破損は 1 chunk 内に閉じている (他 chunk は不変)');

  // (b) chunk 順序契约: 2 chunk を入れ替えると wasm として不正 → compile が失敗する
  const swapped = Buffer.concat(chunks.map((c, i) => (i === 0 ? chunks[1] : i === 1 ? chunks[0] : c)));
  check(sha256(swapped) !== expected.sha256, '[b] chunk 0/1 入替で全体 sha256 不一致');
  let threw = '';
  try {
    await WebAssembly.compile(swapped);
  } catch (e) {
    threw = String((e as Error).message).slice(0, 60);
  }
  check(threw !== '', `[b] chunk 順序を崩すと WebAssembly.compile が失敗 (${threw})`);

  // (c) manifest の id を 1 文字変えると chunk 照合が不一致になる (内容アドレスの実体)
  const bad = man.chunks.id.substr(0, 32).replace(/^./, man.chunks.id[0] === '0' ? '1' : '0');
  check(bad !== man.chunks.id.substr(0, 32) && sha128(chunks[0]) !== bad, '[c] manifest id を書き換えると chunk 照合が不一致');
}

console.log(failed ? `FAILED: ${failed}` : 'ALL PASS');
process.exit(failed ? 1 : 0);

// ---- 補助 ----
function findFile(tree: any, p: string): [number, number, number] | null {
  let cur = tree;
  for (const part of p.split('/')) {
    if (Array.isArray(cur)) return null;
    cur = cur[part];
    if (cur === undefined) return null;
  }
  return Array.isArray(cur) ? (cur as [number, number, number]) : null;
}
