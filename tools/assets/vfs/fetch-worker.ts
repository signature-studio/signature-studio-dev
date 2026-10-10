// fetcher Worker エントリ (browser Worker / node worker_threads 兼用)。
//   init: { t:'init', sab, baseUrl, chunks, verify?, concurrency?, nodeDecoders? }
//   req : { t:'req', slot, idx }  (SabServer が処理)
//   stat: { t:'stat' } -> { t:'stat', requests, bytesFetched, maxInflight }
import { HttpChunkSource } from './http-source.ts';
import { SabServer } from './sab.ts';
import { loadNodeDecoders } from './codec.ts';

let server: SabServer | null = null;
let source: HttpChunkSource | null = null;
let reply: (m: unknown) => void = () => {};

async function onMsg(m: any): Promise<void> {
  if (m.t === 'init') {
    if (m.nodeDecoders) await loadNodeDecoders();
    source = new HttpChunkSource({ baseUrl: m.baseUrl, chunks: m.chunks, verify: !!m.verify, concurrency: m.concurrency ?? 8 });
    server = new SabServer(m.sab, source);
    reply({ t: 'ready' });
  } else if (m.t === 'req') {
    server!.handle(m);
  } else if (m.t === 'stat') {
    reply({ t: 'stat', requests: source?.requests ?? 0, bytesFetched: source?.bytesFetched ?? 0, maxInflight: server?.maxInflight ?? 0 });
  }
}

const isNode = typeof process !== 'undefined' && !!(process as any).versions?.node;
if (isNode) {
  const { parentPort } = await import('node:worker_threads');
  reply = (m) => parentPort!.postMessage(m);
  parentPort!.on('message', (m: unknown) => void onMsg(m));
} else {
  reply = (m) => (self as any).postMessage(m);
  (self as any).onmessage = (e: MessageEvent) => void onMsg(e.data);
}
