// probe-worker.js — dedicated module worker。E (tools/assets/vfs/fetch-worker.ts) と同じ「Worker 内 fetch -> OPFS SyncAccessHandle」経路を再現する。
const MiB = 1 << 20;
const hex = (u8) => Array.from(u8, (b) => b.toString(16).padStart(2, '0')).join('');
const sha256hex = async (buf) => hex(new Uint8Array(await crypto.subtle.digest('SHA-256', buf)));
const now = () => performance.now();
const HDRS = ['content-type', 'content-length', 'content-range', 'accept-ranges', 'etag', 'cache-control', 'content-encoding', 'cf-cache-status', 'cross-origin-resource-policy', 'cross-origin-embedder-policy', 'access-control-allow-origin', 'last-modified', 'age'];
const pickHeaders = (r) => Object.fromEntries(HDRS.filter((h) => r.headers.has(h)).map((h) => [h, r.headers.get(h)]));

async function opfsOpen(name) {
  const root = await navigator.storage.getDirectory();
  const dir = await root.getDirectoryHandle('probe', { create: true });
  const fh = await dir.getFileHandle(name, { create: true });
  const h = await fh.createSyncAccessHandle();
  h.truncate(0);
  return h;
}

async function guard(out, key, fn) {
  const t0 = now();
  try {
    out[key] = await fn();
    if (out[key] && typeof out[key] === 'object' && !Array.isArray(out[key])) out[key].ms = Math.round(now() - t0);
  } catch (e) {
    out[key] = { error: `${e?.name}: ${e?.message}`, ms: Math.round(now() - t0) };
  }
}

async function run({ data, bigName, mf, sab, tag }) {
  const out = { tag, worker: { crossOriginIsolated: self.crossOriginIsolated, sab: typeof SharedArrayBuffer, origin: self.origin } };
  const U = (p) => data + p;
  const bigInfo = mf.files[bigName];

  // SAB: main からの SAB を Worker 側で書き、main 側で読む
  await guard(out, 'sabWrite', async () => {
    const a = new Int32Array(sab);
    Atomics.store(a, 0, 0x5a5a);
    Atomics.add(a, 1, 1);
    return { ok: Atomics.load(a, 0) === 0x5a5a };
  });

  // 1. HEAD / 1 リクエスト目のヘッダ (見えるもののみ)
  await guard(out, 'headBig', async () => {
    const r = await fetch(U(bigName), { method: 'HEAD' });
    return { status: r.status, headers: pickHeaders(r) };
  });

  // 2. 全体 GET (stream) -> piece hash 検証 -> OPFS 書込
  let opfsBig = null;
  await guard(out, 'fullGet', async () => {
    const h = await opfsOpen('big.bin');
    opfsBig = h;
    const r = await fetch(U(bigName));
    const hdr = pickHeaders(r);
    const reader = r.body.getReader();
    let piece = new Uint8Array(MiB), pl = 0, idx = 0, off = 0, bad = 0, total = 0, tFirst = 0;
    const t0 = now();
    const flush = async (len) => {
      const view = piece.subarray(0, len);
      if ((await sha256hex(view)) !== bigInfo.pieces[idx]) bad++;
      h.write(view, { at: off });
      off += len;
      idx++;
      pl = 0;
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!tFirst) tFirst = now() - t0;
      total += value.length;
      let p = 0;
      while (p < value.length) {
        const n = Math.min(MiB - pl, value.length - p);
        piece.set(value.subarray(p, p + n), pl);
        pl += n;
        p += n;
        if (pl === MiB) await flush(MiB);
      }
    }
    if (pl > 0) await flush(pl);
    h.flush();
    const dt = (now() - t0) / 1000;
    return { status: r.status, headers: hdr, bytes: total, expected: bigInfo.size, badPieces: bad, ttfbMs: Math.round(tFirst), sec: +dt.toFixed(2), MBps: +(total / MiB / dt).toFixed(1), opfsSize: h.getSize() };
  });

  // 3. Range 取得 (OPFS に書いた全体コピーと突合)
  await guard(out, 'range', async () => {
    const size = bigInfo.size;
    const mid = Math.floor(size / 2) + 123;
    const cases = [
      ['head1k', 'bytes=0-1023', 0, 1024],
      ['mid1k', `bytes=${mid}-${mid + 999}`, mid, 1000],
      ['openEnd', `bytes=${size - 5000}-`, size - 5000, 5000],
      ['suffix', 'bytes=-1024', size - 1024, 1024],
    ];
    const res = {};
    for (const [name, hv, at, len] of cases) {
      try {
        const r = await fetch(U(bigName), { headers: { Range: hv } });
        const b = new Uint8Array(await r.arrayBuffer());
        const exp = new Uint8Array(len);
        opfsBig.read(exp, { at });
        let same = b.length === len;
        for (let i = 0; same && i < len; i++) if (b[i] !== exp[i]) same = false;
        res[name] = { status: r.status, len: b.length, same, contentRange: r.headers.get('content-range'), contentLength: r.headers.get('content-length') };
      } catch (e) {
        res[name] = { error: `${e?.name}: ${e?.message}` };
      }
    }
    return res;
  });

  // 4. 4MiB 刻み Range x 並列 4 -> 別 OPFS ファイルに書き、piece hash を検証 (Range+OPFS キャッシュ)
  await guard(out, 'rangeParallel', async () => {
    const h = await opfsOpen('big-ranged.bin');
    const size = bigInfo.size, STEP = 4 * MiB;
    const parts = Array.from({ length: Math.ceil(size / STEP) }, (_, i) => i);
    let bad = 0, non206 = 0, statuses = {};
    const t0 = now();
    const worker = async () => {
      for (let i = parts.shift(); i !== undefined; i = parts.shift()) {
        const s = i * STEP, e = Math.min(size, s + STEP) - 1;
        const r = await fetch(U(bigName), { headers: { Range: `bytes=${s}-${e}` } });
        statuses[r.status] = (statuses[r.status] ?? 0) + 1;
        if (r.status !== 206) non206++;
        const b = new Uint8Array(await r.arrayBuffer());
        h.write(b, { at: s });
      }
    };
    await Promise.all([worker(), worker(), worker(), worker()]);
    h.flush();
    for (let i = 0; i < Math.ceil(size / MiB); i++) {
      const b = new Uint8Array(Math.min(MiB, size - i * MiB));
      h.read(b, { at: i * MiB });
      if ((await sha256hex(b)) !== bigInfo.pieces[i]) bad++;
    }
    const dt = (now() - t0) / 1000;
    h.close();
    return { statuses, non206, badPieces: bad, sec: +dt.toFixed(2), MBps: +(size / MiB / dt).toFixed(1) };
  });
  try { opfsBig?.close(); } catch {}

  // 5. E 方式 chunk 取得: c/xx/<id>.raw 1MiB x N, 並列 8, id=sha256 先頭128bit 検証, OPFS slot 書込, Cache Storage put/match
  await guard(out, 'chunks', async () => {
    const h = await opfsOpen('slots.bin');
    const list = mf.chunks.map((c, i) => ({ ...c, i }));
    const st = {}, lat = [], errMsgs = new Set();
    let bad = 0, errors = 0, bytes = 0;
    const t0 = now();
    const cache = await caches.open('probe');
    const worker = async () => {
      for (let c = list.shift(); c; c = list.shift()) {
        const t1 = now();
        let stage = 'fetch';
        try {
          const r = await fetch(U(c.path));
          stage = 'body';
          st[r.status] = (st[r.status] ?? 0) + 1;
          if (!r.ok) { errors++; continue; }
          const b = new Uint8Array(await r.arrayBuffer());
          lat.push(now() - t1);
          bytes += b.length;
          stage = 'sha';
          if ((await sha256hex(b)).slice(0, 32) !== c.id) bad++;
          stage = 'opfsWrite';
          h.write(b, { at: c.i * MiB });
          if (c.i === 0) {
            stage = 'cachePut';
            await cache.put(new Request(U(c.path)), new Response(b.slice(), { headers: { 'content-type': 'application/octet-stream' } }));
          }
        } catch (e) {
          errors++;
          st[`ERR ${e?.name}`] = (st[`ERR ${e?.name}`] ?? 0) + 1;
          if (errMsgs.size < 3) errMsgs.add(`${stage}: ${e?.name}: ${String(e?.message).slice(0, 160)}`);
        }
      }
    };
    await Promise.all(Array.from({ length: 8 }, worker));
    h.flush(); h.close();
    const dt = (now() - t0) / 1000;
    lat.sort((a, b) => a - b);
    const cm = await cache.match(new Request(U(mf.chunks[0].path)));
    return { n: mf.chunks.length, statuses: st, errors, badIds: bad, bytes, sec: +dt.toFixed(2), MBps: +(bytes / MiB / dt).toFixed(1), reqPerSec: +(mf.chunks.length / dt).toFixed(1), p50ms: Math.round(lat[lat.length >> 1] ?? 0), p95ms: Math.round(lat[Math.floor(lat.length * 0.95)] ?? 0), cacheStorageHit: !!cm, errMsgs: [...errMsgs] };
  });

  // 6. 拡張子別 (raw / br / zst) の Content-Type / Content-Encoding / バイト一致
  await guard(out, 'ext', async () => {
    const res = {};
    for (const n of ['x.raw', 'x.br', 'x.zst']) {
      try {
        const r = await fetch(U(n));
        const b = await r.arrayBuffer();
        res[n] = { status: r.status, bytes: b.byteLength, expected: mf.files[n].size, ct: r.headers.get('content-type'), ce: r.headers.get('content-encoding') };
      } catch (e) { res[n] = { error: `${e?.name}: ${e?.message}` }; }
    }
    return res;
  });

  // 7. 条件付き GET (ETag / If-None-Match -> 304) と 404 の形
  await guard(out, 'conditional', async () => {
    const r1 = await fetch(U('x.raw'), { cache: 'no-store' });
    const etag = r1.headers.get('etag');
    await r1.arrayBuffer();
    if (!etag) return { etag: null };
    const r2 = await fetch(U('x.raw'), { cache: 'no-store', headers: { 'If-None-Match': etag } });
    await r2.arrayBuffer();
    const r3 = await fetch(U('nonexistent-' + Math.random().toString(36).slice(2)), { cache: 'no-store' });
    await r3.arrayBuffer();
    return { etag, ifNoneMatchStatus: r2.status, status404: r3.status };
  });

  // 8. wasm: compileStreaming (Content-Type: application/wasm 必須。cross-origin は CORS 必須)
  await guard(out, 'wasmStreaming', async () => {
    const r = await fetch(U('probe.wasm'));
    const m = await WebAssembly.compileStreaming(r);
    return { ok: m instanceof WebAssembly.Module, ct: r.headers.get('content-type') };
  });

  // 8b. 25MiB 超の単一 wasm を分割配信 -> 連結ストリームを Response (application/wasm) に包んで compileStreaming
  await guard(out, 'wasmParts', async () => {
    const wp = mf.wasmParts;
    const t0 = now();
    let i = 0, reader = null, got = 0;
    const stream = new ReadableStream({
      async pull(ctl) {
        for (;;) {
          if (!reader) {
            if (i >= wp.parts.length) return ctl.close();
            const r = await fetch(U(wp.parts[i++].path));
            if (!r.ok) throw new Error(`part HTTP ${r.status}`);
            reader = r.body.getReader();
          }
          const { done, value } = await reader.read();
          if (done) { reader = null; continue; }
          got += value.length;
          return ctl.enqueue(value);
        }
      },
    });
    const mod = await WebAssembly.compileStreaming(new Response(stream, { headers: { 'content-type': 'application/wasm' } }));
    const cs = WebAssembly.Module.customSections(mod, 'pad');
    return { parts: wp.parts.length, bytes: got, expected: wp.total, padLen: cs[0]?.byteLength, expectedPad: wp.payload, ok: got === wp.total && cs[0]?.byteLength === wp.payload, sec: +((now() - t0) / 1000).toFixed(2) };
  });

  // 9. no-cors fetch (opaque) — require-corp 下では cross-origin で失敗するはず
  await guard(out, 'noCorsFetch', async () => {
    const r = await fetch(U('x.raw'), { mode: 'no-cors' });
    return { type: r.type, status: r.status };
  });
  return out;
}

self.onmessage = async (e) => {
  try { self.postMessage({ ok: true, out: await run(e.data) }); }
  catch (err) { self.postMessage({ ok: false, error: String(err?.stack ?? err) }); }
};
