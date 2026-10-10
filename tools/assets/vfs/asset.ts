// 大物 asset (314MB 級 wasm) の chunk 連結ストリーム + 二段キャッシュ。
//
//   manifest → chunk 取得 (L2 OPFS / L1 IDB / network の順で解決) → 連結 ReadableStream
//   → new Response(stream, {content-type: application/wasm}) → WebAssembly.compileStreaming
//
// - 整合性: manifest の chunk id = 非圧縮 chunk の sha256 先頭 128bit (内容アドレス)。
//   キャッシュから読んだ chunk も毎回照合し、不一致は「破損」として他 tier / network から
//   当該 chunk だけ再取得して修復する (chunk 単位の部分修復。全体 sha256 は e2e で別途検証)。
// - L2 OPFS (永続, SyncAccessHandle): 1 asset = 1 ファイル。4KiB header + chunk i を
//   4096 + i*chunkSize に固定配置。header に「書き込み済み chunk」の bitmap を持ち
//   (bit は payload 書込後に立てる → torn write で bit だけ立っても per-chunk sha で検出できる)、
//   未書込 chunk は読まずに次 tier へ落ちる。部分充填のまま再起動しても再開できる。
// - L1 IndexedDB (永続): store 'parts' に chunk 単位 (key `${keyHash}/${i}`)、store 'meta' に寸法。
//   保存は bytes のみ (WebAssembly.Module は保存しない)。
// - 連結ストリームの契約 (並列先読み + 順序保証 + 背圧) は deploy/client/chunked.mjs と同じ形に寄せた。
//   違いは E 側 manifest (c/<id>.<ext> 内容アドレス) をソースにし、二段キャッシュと部分修復を持つ点。
import type { ManifestIndex } from './manifest.ts';
import { HttpChunkSource } from './http-source.ts';
import { openOpfsSyncFile } from './opfs.ts';
import { openIdb } from './idb.ts';
import type { IdbHandle } from './idb.ts';
import type { SyncFile } from './types.ts';

const HDR = 4096;
const MAGIC = 0x31574c46; // 'FLW1'
const VER = 1;
const BITMAP_AT = 64; // header 内 bitmap 先頭 (64..4095 → 最大 32256 chunk = 32GiB @1MiB)
const IDB_NAME = 'fl-assets-v1';
const IDB_PARTS = 'parts';
const IDB_META = 'meta';

async function sha128hex(b: Uint8Array): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest('SHA-256', b as BufferSource));
  let s = '';
  for (let i = 0; i < 16; i++) s += d[i].toString(16).padStart(2, '0');
  return s;
}

const hexBytes = (h: string): Uint8Array => Uint8Array.from((h.match(/../g) ?? []).map((x) => parseInt(x, 16)));
const bytesHex = (b: Uint8Array): string => [...b].map((x) => x.toString(16).padStart(2, '0')).join('');

/** asset のキャッシュキー (manifest 内容から導出: 内容・layout が変われば自然に別キー) */
export async function assetKeyHash(index: ManifestIndex, path: string): Promise<string> {
  const f = index.file(path);
  if (!f) throw new Error(`asset not in manifest: ${path}`);
  const first = f.size > 0 ? index.chunkId(f.first) : '';
  const nChunks = Math.ceil(f.size / index.chunkSize);
  const seed = `${index.m.name}/${path}/${f.size}/${nChunks}x${index.chunkSize}/${first}`;
  return sha128hex(new TextEncoder().encode(seed));
}

export interface AssetStats {
  /** 全体の初回解決元 (最初に requirement を満たした tier) */
  source: 'opfs' | 'idb' | 'network';
  /** chunk 取得元の内訳 */
  fromOpfs: number;
  fromIdb: number;
  fromNetwork: number;
  /** sha 不一致で検出した破損 chunk 数 (再取得で修復) */
  corruptChunks: number;
  /** OPFS 書き戻し / IDB 書き戻し chunk 数 (修復を含む) */
  opfsWrites: number;
  idbWrites: number;
  netBytes: number;
  opfsPresent: boolean;
  idbPresent: boolean;
}

export interface OpenAssetOptions {
  index: ManifestIndex;
  /** manifest 内の asset path (例: Engine/FLEngine.wasm) */
  path: string;
  baseUrl: string;
  /** 先読み窓 (chunk 数)。既定 6 */
  concurrency?: number;
  /** network fetch の chunk 検証 (既定 true: sha128 照合) */
  verify?: boolean;
  opfs?: boolean;
  idb?: boolean;
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
  onProgress?: (p: { chunk: number; chunks: number; bytes: number; source: 'opfs' | 'idb' | 'network' }) => void;
}

export interface OpenAssetResult {
  /** chunk 順に連結した非圧縮バイト列の ReadableStream (pull 駆動, 背圧あり) */
  stream: ReadableStream<Uint8Array>;
  /** compileStreaming にそのまま渡せる Response (content-type: application/wasm) */
  response(): Response;
  path: string;
  keyHash: string;
  totalBytes: number;
  nChunks: number;
  chunkSize: number;
  stats: AssetStats;
  /** ストリームの消費が完了し、キャッシュへの保存 (IDB put 等) が全て終わってから解決する */
  done: Promise<void>;
  close(): void;
}

interface OpfsTier {
  file: SyncFile;
  hdr: Uint8Array;
  hv: DataView;
  nChunks: number;
  chunkSize: number;
}

function opfsBitmapGet(t: OpfsTier, i: number): boolean {
  return (t.hdr[BITMAP_AT + (i >> 3)] & (1 << (i & 7))) !== 0;
}
function opfsBitmapSet(t: OpfsTier, i: number): void {
  t.hdr[BITMAP_AT + (i >> 3)] |= 1 << (i & 7);
  t.file.write(t.hdr, 0);
}

async function openOpfsTier(keyHash: string, nChunks: number, chunkSize: number, totalBytes: number): Promise<OpfsTier | null> {
  const file = await openOpfsSyncFile(`${keyHash}.bin`, 'fl-assets');
  if (!file) return null;
  const hdr = new Uint8Array(HDR);
  const hv = new DataView(hdr.buffer);
  let ok = file.getSize() === HDR + totalBytes;
  if (ok) {
    file.read(hdr, 0);
    ok =
      hv.getUint32(0, true) === MAGIC &&
      hv.getUint32(4, true) === VER &&
      hv.getUint32(8, true) === nChunks &&
      hv.getUint32(12, true) === chunkSize &&
      bytesHex(hdr.subarray(24, 40)) === keyHash;
  }
  if (!ok) {
    // 未完 / 破損 / キー不一致 → 作り直し。bitmap 0 = 未書込 (未充填領域は読まず次 tier へ)
    file.truncate(HDR + totalBytes);
    hdr.fill(0);
    hv.setUint32(0, MAGIC, true);
    hv.setUint32(4, VER, true);
    hv.setUint32(8, nChunks, true);
    hv.setUint32(12, chunkSize, true);
    hv.setBigUint64(16, BigInt(totalBytes), true);
    hdr.set(hexBytes(keyHash), 24);
    hv.setBigUint64(48, BigInt(Date.now()), true);
    file.write(hdr, 0);
    file.flush();
  }
  return { file, hdr, hv, nChunks, chunkSize };
}

function opfsReadChunk(t: OpfsTier, i: number, usize: number): Uint8Array | null {
  if (!opfsBitmapGet(t, i)) return null;
  const buf = new Uint8Array(usize);
  const n = t.file.read(buf, HDR + i * t.chunkSize);
  return n === usize ? buf : null;
}

/**
 * asset を chunk 連結ストリームとして開く。
 * キャッシュ (OPFS → IDB) に無い chunk だけ network から取得し、両 tier に書き戻す。
 */
export async function openAssetStream(o: OpenAssetOptions): Promise<OpenAssetResult> {
  const index = o.index;
  const f = index.file(o.path);
  if (!f || f.stub) throw new Error(`asset not servable: ${o.path} (stub=${f?.stub})`);
  const nChunks = index.fileChunks(f).length;
  const chunkSize = index.chunkSize;
  const totalBytes = f.size;
  const keyHash = await assetKeyHash(index, o.path);
  const conc = o.concurrency ?? 6;

  const stats: AssetStats = { source: 'network', fromOpfs: 0, fromIdb: 0, fromNetwork: 0, corruptChunks: 0, opfsWrites: 0, idbWrites: 0, netBytes: 0, opfsPresent: false, idbPresent: false };
  const src = new HttpChunkSource({ baseUrl: o.baseUrl, chunks: index.m.chunks, verify: o.verify ?? true, fetchImpl: o.fetchImpl });

  // ---- tier を開く ----
  let opfs: OpfsTier | null = null;
  if (o.opfs !== false) {
    try {
      opfs = await openOpfsTier(keyHash, nChunks, chunkSize, totalBytes);
    } catch {
      opfs = null;
    }
  }
  stats.opfsPresent = !!opfs;
  let idb: IdbHandle | null = null;
  let idbMeta: { nChunks?: number } | undefined;
  if (o.idb !== false) {
    try {
      idb = await openIdb(IDB_NAME, [IDB_PARTS, IDB_META]);
      idbMeta = idb ? await idb.get<{ nChunks?: number }>(IDB_META, keyHash) : undefined;
      if (idbMeta && idbMeta.nChunks !== nChunks) idbMeta = undefined; // 異なる layout: 作り直し
    } catch {
      idb = null;
    }
  }
  stats.idbPresent = !!idbMeta;
  const saves = new Set<Promise<unknown>>();
  const track = (p: Promise<unknown>) => {
    const q = p.catch(() => {});
    saves.add(q);
    void q.finally(() => saves.delete(q));
  };

  // ---- 1 chunk の解決: OPFS → IDB → network (+ 検証, 部分修復, 書き戻し) ----
  const getChunk = async (i: number): Promise<Uint8Array> => {
    const id = index.chunkId(i);
    const usize = index.chunkUsize(i);
    if (opfs) {
      const d = opfsReadChunk(opfs, i, usize);
      if (d && (await sha128hex(d)) === id) {
        stats.fromOpfs++;
        if (stats.source === 'network' && stats.fromNetwork === 0 && stats.fromIdb === 0) stats.source = 'opfs';
        o.onProgress?.({ chunk: i, chunks: nChunks, bytes: usize, source: 'opfs' });
        return d;
      }
      if (d) stats.corruptChunks++;
    }
    if (idb) {
      const part = await idb.get<Uint8Array>(IDB_PARTS, `${keyHash}/${i}`).catch(() => undefined);
      if (part && part.length === usize && (await sha128hex(part)) === id) {
        stats.fromIdb++;
        if (stats.source === 'network' && stats.fromNetwork === 0) stats.source = 'idb';
        if (opfs) {
          opfsWriteChunk(opfs, i, part);
          stats.opfsWrites++;
        }
        o.onProgress?.({ chunk: i, chunks: nChunks, bytes: usize, source: 'idb' });
        return part;
      }
      if (part) {
        stats.corruptChunks++;
        track(idb.del(IDB_PARTS, `${keyHash}/${i}`));
      }
    }
    // network (HttpChunkSource が fetch + 復号 + sha128 検証)
    const d = await src.fetchChunk(i);
    stats.fromNetwork++;
    stats.netBytes += d.length;
    if (stats.source !== 'opfs' && stats.source !== 'idb') stats.source = 'network';
    if (opfs) {
      opfsWriteChunk(opfs, i, d);
      stats.opfsWrites++;
    }
    if (idb) {
      stats.idbWrites++;
      track(idb.put(IDB_PARTS, `${keyHash}/${i}`, d.slice()));
    }
    o.onProgress?.({ chunk: i, chunks: nChunks, bytes: usize, source: 'network' });
    return d;
  };

  function opfsWriteChunk(t: OpfsTier, i: number, data: Uint8Array): void {
    t.file.write(data, HDR + i * t.chunkSize);
    opfsBitmapSet(t, i);
  }

  // ---- 連結 ReadableStream (順序保証 + 並列先読み + 背圧)。chunked.mjs と同じ fill/pull 構造 ----
  let next = 0;
  let emit = 0;
  let streamFinished!: () => void;
  const finished = new Promise<void>((r) => (streamFinished = r));
  const inflight = new Map<number, Promise<Uint8Array>>();
  const start = (i: number) => inflight.set(i, getChunk(i));
  const fill = () => {
    while (next < nChunks && next - emit < conc) start(next++);
  };
  fill();
  const stream = new ReadableStream<Uint8Array>(
    {
      async pull(ctl) {
        if (emit >= nChunks) {
          ctl.close();
          return;
        }
        const buf = await inflight.get(emit)!;
        inflight.delete(emit);
        emit++;
        fill();
        ctl.enqueue(buf);
        if (emit >= nChunks) {
          ctl.close();
          streamFinished();
        }
      },
      cancel() {
        inflight.clear();
        next = nChunks;
        streamFinished();
      },
    },
    { highWaterMark: 0 }
  );

  const done = finished.then(async () => {
    await Promise.allSettled([...saves]);
    if (idb && stats.idbWrites > 0) {
      // meta は「IDB に部分充填が存在する」印。破損 part は getChunk が削除するので冪等
      await idb.put(IDB_META, keyHash, { nChunks, chunkSize, totalBytes, path: o.path, created: new Date().toISOString() }).catch(() => {});
    }
    try {
      opfs?.file.flush();
    } catch {}
  });

  const close = () => {
    try {
      opfs?.file.close();
    } catch {}
    idb?.close();
  };

  return {
    stream,
    response: () =>
      new Response(stream, {
        headers: { 'content-type': 'application/wasm', 'content-length': String(totalBytes) },
      }),
    path: o.path,
    keyHash,
    totalBytes,
    nChunks,
    chunkSize,
    stats,
    done,
    close,
  };
}

/** compileStreaming まで通す (契約: content-type application/wasm の Response を渡す) */
export async function loadWasmAsset(
  o: OpenAssetOptions
): Promise<{ module: WebAssembly.Module; exports: number; imports: number; result: OpenAssetResult }> {
  const a = await openAssetStream(o);
  try {
    const module = await WebAssembly.compileStreaming(a.response());
    await a.done;
    return { module, exports: WebAssembly.Module.exports(module).length, imports: WebAssembly.Module.imports(module).length, result: a };
  } catch (e) {
    a.close();
    throw e;
  }
}

// ---- デバッグ / e2e 用: 破損注入と tier 状態取得 ----

/** OPFS の chunk i の payload を garbage で上書き (破損検出・修復経路のテスト) */
export async function debugCorruptOpfsChunk(index: ManifestIndex, path: string, i: number): Promise<boolean> {
  const keyHash = await assetKeyHash(index, path);
  const file = await openOpfsSyncFile(`${keyHash}.bin`, 'fl-assets');
  if (!file) return false;
  const usize = index.chunkUsize(i);
  const off = HDR + i * index.chunkSize + 1024;
  if (off + 64 > HDR + i * index.chunkSize + usize) return false;
  // header の bitmap は触らない (書込済み chunk の「内容破損」を注入する)
  file.write(new Uint8Array(64).fill(0xaa), off);
  file.flush();
  file.close();
  return true;
}

/** IDB の chunk i を garbage で置換 */
export async function debugCorruptIdbChunk(index: ManifestIndex, path: string, i: number): Promise<boolean> {
  const keyHash = await assetKeyHash(index, path);
  const idb = await openIdb(IDB_NAME, [IDB_PARTS, IDB_META]);
  if (!idb) return false;
  await idb.put(IDB_PARTS, `${keyHash}/${i}`, new Uint8Array(index.chunkUsize(i)).fill(0x55));
  idb.close();
  return true;
}

/** tier の存在確認 (e2e 用)。OPFS ファイルサイズと IDB meta を見る */
export async function debugAssetTiers(index: ManifestIndex, path: string): Promise<{ opfs: boolean; opfsBytes: number; idb: boolean }> {
  const keyHash = await assetKeyHash(index, path);
  const file = await openOpfsSyncFile(`${keyHash}.bin`, 'fl-assets');
  const opfsBytes = file?.getSize() ?? 0;
  file?.close();
  const idb = await openIdb(IDB_NAME, [IDB_PARTS, IDB_META]);
  const meta = idb ? await idb.get(IDB_META, keyHash) : undefined;
  idb?.close();
  return { opfs: opfsBytes > 0, opfsBytes, idb: !!meta };
}

/** この asset のキャッシュ全消し (e2e の cold 再現用)。OPFS ファイルと IDB parts/meta を削除 */
export async function debugDropAssetCaches(index: ManifestIndex, path: string): Promise<void> {
  const keyHash = await assetKeyHash(index, path);
  const { removeOpfsFile } = await import('./opfs.ts');
  await removeOpfsFile(`${keyHash}.bin`, 'fl-assets');
  const idb = await openIdb(IDB_NAME, [IDB_PARTS, IDB_META]);
  if (idb) {
    const keys = await idb.keys(IDB_PARTS).catch(() => [] as IDBValidKey[]);
    await Promise.all(keys.filter((k) => String(k).startsWith(`${keyHash}/`)).map((k) => idb.del(IDB_PARTS, k).catch(() => {})));
    await idb.del(IDB_META, keyHash).catch(() => {});
    idb.close();
  }
}
