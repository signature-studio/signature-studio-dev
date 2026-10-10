// asset ローダの e2e Worker: manifest → chunk 取得 (二段キャッシュ) → 連結 → compileStreaming
// → キャッシュ検証 (全バイト再読み + sha256 照合) を 1 シナリオ実行して報告する。
// シナリオ (URL ?scenario=):
//   cold         キャッシュ空から network 取得 → 両 tier に保存
//   warm-netoff  network 遮断 (server /__net off) でキャッシュのみ
//   corrupt-opfs OPFS の 1 chunk を破損 → IDB から修復 (network 無し)
//   corrupt-both OPFS と IDB の同一 chunk を破損 → network から再取得して修復
import { fetchManifest, ManifestIndex, loadWasmAsset, openAssetStream, debugCorruptOpfsChunk, debugCorruptIdbChunk, debugAssetTiers, debugDropAssetCaches } from '../../vfs/index.ts';

const g = self as any;
const hex = (b: ArrayBuffer) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');

g.onmessage = async (e: MessageEvent) => {
  const t0 = Date.now();
  let stage = 'boot';
  const progress = (s: string) => {
    stage = s;
    g.postMessage({ ok: 'progress', stage, elapsedMs: Date.now() - t0 });
  };
  try {
    const res = await run(e.data, progress);
    g.postMessage({ ok: true, res });
  } catch (err) {
    g.postMessage({ ok: false, error: String((err as Error).stack ?? err), stage, elapsedMs: Date.now() - t0 });
  }
};

interface Cfg {
  base: string;
  scenario: string;
  path: string;
  expected: { path: string; size: number; sha256: string };
  chunk: number;
  isolated: boolean;
  sab: boolean;
}

async function run(cfg: Cfg, progress: (s: string) => void) {
  const r: Record<string, any> = { scenario: cfg.scenario, isolated: cfg.isolated, sab: cfg.sab };
  const nChunksOf = (size: number, cs: number) => Math.ceil(size / cs);

  progress('manifest');
  const manifest = await fetchManifest(cfg.base);
  const index = new ManifestIndex(manifest);
  const f = index.file(cfg.path);
  if (!f) throw new Error('asset not in manifest: ' + cfg.path);
  r.manifest = { chunks: manifest.chunks.n, chunkSize: manifest.chunkSize, assetChunks: nChunksOf(f.size, manifest.chunkSize), assetSize: f.size };
  r.sizeMatches = f.size === cfg.expected.size;

  if (cfg.scenario === 'cold') {
    progress('drop-caches');
    await debugDropAssetCaches(index, cfg.path);
  }
  if (cfg.scenario === 'corrupt-opfs' || cfg.scenario === 'corrupt-both') {
    progress('corrupt-inject');
    const ci = cfg.chunk;
    r.corruptChunk = ci;
    r.injectedOpfs = await debugCorruptOpfsChunk(index, cfg.path, ci);
    if (cfg.scenario === 'corrupt-both') r.injectedIdb = await debugCorruptIdbChunk(index, cfg.path, ci);
  }

  progress('pass1-compile');
  const t1 = performance.now();
  const { module, exports, imports, result } = await loadWasmAsset({
    index,
    path: cfg.path,
    baseUrl: cfg.base,
    concurrency: 6,
  });
  r.compileMs = +(performance.now() - t1).toFixed(0);
  r.exports = exports;
  r.imports = imports;
  r.pass1 = { ...result.stats };
  await result.done;
  result.close();

  progress('pass2-verify');
  // 全バイトをキャッシュ経由で再読みして sha256 照合 (byte-identity + キャッシュ読出経路の検証)
  const t2 = performance.now();
  const a2 = await openAssetStream({ index, path: cfg.path, baseUrl: cfg.base, concurrency: 6 });
  const all = new Uint8Array(a2.totalBytes);
  let off = 0;
  const reader = a2.stream.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    all.set(value, off);
    off += value.length;
  }
  if (off !== a2.totalBytes) throw new Error(`short assemble: ${off} != ${a2.totalBytes}`);
  const got = hex(await crypto.subtle.digest('SHA-256', all));
  r.pass2 = { ms: +(performance.now() - t2).toFixed(0), ...a2.stats };
  await a2.done;
  a2.close();
  r.shaOk = got === cfg.expected.sha256;
  r.sha256 = got.slice(0, 16) + '…';
  r.totalBytes = off;

  progress('tiers');
  r.tiers = await debugAssetTiers(index, cfg.path);
  r.wasmValid = exports > 0;
  return r;
}
