// 入力: 決定的 (整数 LCG → 2^-15 倍で exact)。bit-exact 判定はサーバ側 (node) の makeRef と比較する。
const BUF = 4096, OUT = BUF + 512;
const inputAt = (b, i) => { const x = (Math.imul(b * 128 + i, 1103515245) + 12345) & 0xffff; return Math.fround(x / 32768 - 1); };
const fnv = (h, f32) => { const u = new Uint32Array(f32.buffer, f32.byteOffset, f32.length); for (let i = 0; i < u.length; i++) { h = Math.imul(h ^ u[i], 16777619) >>> 0; } return h; };
const med = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[s.length >> 1]; };

onmessage = async (e) => {
  const { c, salt, blocks } = e.data; const out = { c, salt, blocks };
  try {
    let t = performance.now();
    const buf = await (await fetch(`/wasm?c=${c}&salt=${salt}`)).arrayBuffer();
    out.fetchMs = performance.now() - t; out.bytes = buf.byteLength;
    t = performance.now(); const mod = await WebAssembly.compile(buf); out.compileMs = performance.now() - t;
    t = performance.now(); const inst = await WebAssembly.instantiate(mod, {}); out.instantiateMs = performance.now() - t;
    const { memory, ws_process, ws_buffers } = inst.exports;
    const inPtr = ws_buffers();
    const first = []; let h = 2166136261; const raw = [];
    const timings = [];
    for (let b = 0; b < blocks; b++) {
      const inp = new Float32Array(memory.buffer, inPtr, 128);
      for (let i = 0; i < 128; i++) inp[i] = inputAt(b, i);
      const t0 = performance.now(); ws_process(128); const dt = performance.now() - t0;
      const o = new Float32Array(memory.buffer, OUT, 128);
      h = fnv(h, o); if (b < 8) raw.push(Array.from(o));
      timings.push(dt);
    }
    out.firstCallMs = timings[0]; out.callsMs_2_10 = timings.slice(1, 10);
    // 区間平均 (performance.now の粗い分解能を避ける): 32 ブロックごとの平均 µs
    const chunk = []; for (let i = 32; i + 32 <= timings.length; i += 32) chunk.push(timings.slice(i, i + 32).reduce((x, y) => x + y, 0) / 32 * 1000);
    out.steadyUsPerBlockP50 = med(chunk); out.steadyUsPerBlockMax = Math.max(...chunk);
    out.hash = h; out.raw8 = raw;
    out.timerResolutionMs = (() => { let m = Infinity; const a = performance.now(); let b = a; for (let i = 0; i < 2e5 && m > 0; i++) { b = performance.now(); if (b > a) { m = Math.min(m, b - a); break; } } return m; })();
  } catch (er) { out.error = String(er && er.stack || er).slice(0, 400); }
  postMessage(out);
};
