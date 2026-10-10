// 大物 (25MiB 超) を Static Assets に載せるためのクライアント側連結ローダ。
// deploy/scripts/05-stage.mjs が <key>.parts/index.json + NNNN.<sha12>.part に分割した資産を、
// 並列プリフェッチ (順序保証・背圧付き) で 1 本の ReadableStream に連結する。
//   const resp = await chunkedResponse('/wasm/ott.1a2b3c4d.wasm.parts/index.json');
//   const mod  = await WebAssembly.compileStreaming(resp);      // application/wasm の Response として渡る
// ブラウザ (main / Worker) と Node ≥ 20 の両方で動く (fetch / ReadableStream / crypto.subtle のみ使用)。
//
// 再試行: 429 / 5xx / ネットワークエラーは Retry-After もしくは指数バックオフ (250ms〜) で最大 `retries` 回。
// Access セッション失効 (redirect:'manual' の opaqueredirect / 401 / 403) は AccessExpiredError で別系統 (再ログイン誘導用)。
// Static Assets は Range 非対応 (200 全体) なので part 単位の丸ごと GET のみ使う。

export class AccessExpiredError extends Error {
  constructor(url, why) {
    super(`Access セッション失効の可能性: ${url} (${why})`);
    this.name = "AccessExpiredError";
    this.url = url;
  }
}
export class ChunkIntegrityError extends Error {
  constructor(url, want, got) {
    super(`part の sha256 不一致: ${url} want=${want} got=${got}`);
    this.name = "ChunkIntegrityError";
  }
}

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const sleep = (ms, signal) =>
  new Promise((res, rej) => {
    const t = setTimeout(res, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); rej(signal.reason); }, { once: true });
  });

async function fetchOk(url, { fetchImpl, retries, signal, baseDelay }) {
  let last;
  for (let attempt = 0; attempt <= retries; attempt++) {
    let res;
    try {
      res = await fetchImpl(url, { redirect: "manual", credentials: "same-origin", signal });
    } catch (e) {
      if (signal?.aborted) throw e;
      last = e;
    }
    if (res) {
      if (res.type === "opaqueredirect" || (res.status >= 300 && res.status < 400)) throw new AccessExpiredError(url, `redirect ${res.status || res.type}`);
      if (res.status === 401 || res.status === 403) throw new AccessExpiredError(url, `HTTP ${res.status}`);
      if (res.ok) return res;
      if (res.status !== 429 && res.status < 500) throw new Error(`HTTP ${res.status}: ${url}`);
      const ra = Number(res.headers.get("retry-after"));
      last = Object.assign(new Error(`HTTP ${res.status}: ${url}`), { retryAfterMs: Number.isFinite(ra) && ra > 0 ? ra * 1000 : 0 });
      await res.body?.cancel().catch(() => {});
    }
    if (attempt < retries) await sleep(last?.retryAfterMs || baseDelay * 2 ** attempt, signal);
  }
  throw last;
}

export async function loadDescriptor(descriptorUrl, opts = {}) {
  const o = { fetchImpl: opts.fetch ?? globalThis.fetch, retries: opts.retries ?? 3, signal: opts.signal, baseDelay: opts.baseDelay ?? 250 };
  const res = await fetchOk(descriptorUrl, o);
  const d = await res.json();
  if (d.v !== 1 || !Array.isArray(d.parts)) throw new Error(`descriptor 形式不正: ${descriptorUrl}`);
  return d;
}

// 元ファイルの URL (…/ott.1a2b3c4d.wasm) から descriptor URL (…/ott.1a2b3c4d.wasm.parts/index.json) を導く
export const descriptorUrlFor = (assetUrl) => `${assetUrl}.parts/index.json`;

export async function chunkedStream(descriptorUrl, opts = {}) {
  const {
    concurrency = 6, verify = true, retries = 3, baseDelay = 250, signal,
    fetch: fetchImpl = globalThis.fetch, onProgress,
  } = opts;
  const desc = await loadDescriptor(descriptorUrl, { fetch: fetchImpl, retries, signal, baseDelay });
  const base = new URL(descriptorUrl, globalThis.location?.href ?? "http://localhost/").href.replace(/[^/]*$/, "");
  const o = { fetchImpl, retries, signal, baseDelay };
  let next = 0; // 次に発行する part
  let emit = 0; // 次に enqueue する part
  let loaded = 0;
  const inflight = new Map();
  const start = (i) => {
    const p = desc.parts[i];
    const url = base + p.name;
    inflight.set(i, (async () => {
      const res = await fetchOk(url, o);
      const buf = new Uint8Array(await res.arrayBuffer());
      if (buf.length !== p.size) throw new Error(`part サイズ不一致: ${url} want=${p.size} got=${buf.length}`);
      if (verify) {
        const got = hex(await crypto.subtle.digest("SHA-256", buf));
        if (got !== p.sha256) throw new ChunkIntegrityError(url, p.sha256, got);
      }
      return buf;
    })());
    // 未 await のまま reject されても unhandledrejection にしない (pull 側で再 throw される)
    inflight.get(i).catch(() => {});
  };
  const fill = () => { while (next < desc.parts.length && next - emit < concurrency) start(next++); };
  const stream = new ReadableStream({
    start() { fill(); },
    async pull(ctl) {
      if (emit >= desc.parts.length) { ctl.close(); return; }
      const buf = await inflight.get(emit);
      inflight.delete(emit);
      emit++;
      loaded += buf.length;
      fill();
      onProgress?.({ loaded, total: desc.size, part: emit, parts: desc.parts.length });
      ctl.enqueue(buf);
      if (emit >= desc.parts.length) ctl.close();
    },
    cancel() { inflight.clear(); next = desc.parts.length; },
  }, { highWaterMark: 0 });
  return { stream, descriptor: desc };
}

export async function chunkedResponse(descriptorUrl, opts = {}) {
  const { stream, descriptor } = await chunkedStream(descriptorUrl, opts);
  return new Response(stream, { headers: { "content-type": descriptor.contentType ?? "application/octet-stream", "content-length": String(descriptor.size) } });
}

export const compileChunkedWasm = async (descriptorUrl, opts) => WebAssembly.compileStreaming(await chunkedResponse(descriptorUrl, opts));
export const instantiateChunkedWasm = async (descriptorUrl, imports, opts) => WebAssembly.instantiateStreaming(await chunkedResponse(descriptorUrl, opts), imports);

// 連結結果の全体 sha256 を検証したい場合 (全 part 検証済みなら通常は不要。デバッグ/E2E 用)
export async function chunkedArrayBuffer(descriptorUrl, opts = {}) {
  return new Response((await chunkedStream(descriptorUrl, opts)).stream).arrayBuffer();
}
