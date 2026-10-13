// e2e_lib.mjs — gui e2e ドライバ (e2e.mjs / stress.mjs) の共通部。ブラウザ操作は tools/e2e/suite/drivers/* 経由。
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.join(HERE, "..");
export const BUILD = path.join(ROOT, "build");
export const W = 320, H = 200;

// ---------------- 静的サーバ (COOP/COEP) ----------------
const MIME = { ".js": "text/javascript", ".mjs": "text/javascript", ".html": "text/html", ".wasm": "application/wasm", ".ppm": "application/octet-stream", ".json": "application/json" };
export function startServer() {
  const map = [["/wasm/", process.env.GUI_WASM_DIR ? path.resolve(process.env.GUI_WASM_DIR) : path.join(BUILD, "wasm")], ["/js/", path.join(BUILD, "js")], ["/e2e/", HERE], ["/golden/", path.join(ROOT, "golden")]];
  const srv = http.createServer((req, res) => {
    let url = decodeURIComponent((req.url || "/").split("?")[0]);
    if (url === "/") url = "/e2e/index.html";
    const hit = map.find(([p]) => url.startsWith(p));
    const headers = { "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp", "Cross-Origin-Resource-Policy": "same-origin", "Cache-Control": "no-store" };
    if (!hit) { res.writeHead(404, headers); res.end("not found"); return; }
    const file = path.join(hit[1], url.slice(hit[0].length));
    if (!file.startsWith(hit[1]) || !fs.existsSync(file)) { res.writeHead(404, headers); res.end("not found " + url); return; }
    res.writeHead(200, { ...headers, "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => srv.listen(0, "127.0.0.1", () => resolve({ srv, port: srv.address().port })));
}

// ---------------- ドライバ選択 (E2E_DRIVER=agent-browser|puppeteer) ----------------
export async function openDriver(url) {
  const name = process.env.E2E_DRIVER || "agent-browser";
  if (name !== "agent-browser" && name !== "puppeteer") throw new Error(`E2E_DRIVER=${name} 未対応 (agent-browser|puppeteer)`);
  const mod = await import(`../../e2e/suite/drivers/${name}.mjs`);
  const drv = await mod.createDriver({ chrome: process.env.CHROME || "/usr/bin/google-chrome", session: `gui-e2e-${process.pid}` });
  await drv.open(url);
  await drv.setViewport(480, 360);
  return drv;
}

// ---------------- PNG (8bit RGB/RGBA, 非 interlace) デコード ----------------
export function decodePNG(buf) {
  let p = 8, w = 0, h = 0, ct = 0; const idat = [];
  while (p < buf.length) {
    const len = buf.readUInt32BE(p), type = buf.toString("latin1", p + 4, p + 8), data = buf.subarray(p + 8, p + 8 + len);
    if (type === "IHDR") { w = data.readUInt32BE(0); h = data.readUInt32BE(4); ct = data[9]; if (data[8] !== 8 || data[12] !== 0) throw new Error("png: unsupported"); }
    if (type === "IDAT") idat.push(data);
    p += 12 + len;
  }
  const bpp = ct === 6 ? 4 : ct === 2 ? 3 : 0; if (!bpp) throw new Error("png: color type " + ct);
  const raw = zlib.inflateSync(Buffer.concat(idat)); const stride = w * bpp; const out = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)]; const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? out[y * stride + x - bpp] : 0, b = y ? out[(y - 1) * stride + x] : 0, c = x >= bpp && y ? out[(y - 1) * stride + x - bpp] : 0;
      let v = line[x];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const pp = a + b - c, pa = Math.abs(pp - a), pb = Math.abs(pp - b), pc = Math.abs(pp - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      out[y * stride + x] = v & 255;
    }
  }
  return { w, h, bpp, data: out };
}
export function readPPM(file) {
  const b = fs.readFileSync(file); const m = /^P6\s+(\d+)\s+(\d+)\s+255\s/.exec(b.toString("latin1", 0, 32));
  return { w: +m[1], h: +m[2], data: b.subarray(m[0].length) };
}
export function diffRGB(wantRGB, w, h, getPx) {
  let diff = 0, first = null;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [r, g, b] = getPx(x, y), o = (y * w + x) * 3;
    if (r !== wantRGB[o] || g !== wantRGB[o + 1] || b !== wantRGB[o + 2]) { diff++; if (!first) first = { x, y, got: [r, g, b], want: [wantRGB[o], wantRGB[o + 1], wantRGB[o + 2]] }; }
  }
  return { diff, first };
}
export function writePPM(file, w, h, getPx) {
  const out = Buffer.alloc(w * h * 3);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const [r, g, b] = getPx(x, y), o = (y * w + x) * 3; out[o] = r; out[o + 1] = g; out[o + 2] = b; }
  fs.writeFileSync(file, Buffer.concat([Buffer.from(`P6\n${w} ${h}\n255\n`), out]));
}

// ---------------- ストレス判定 (純関数; stress.mjs と selftest が共用) ----------------
// samples: [{ frames, inDropped, outFullWaits, memBytes, gens: {surfId: gen} }, ...] (時刻順)
// 戻り値: 失敗理由の配列 (空 = 合格)。呼び出し側が非空なら非 0 exit にする (不合格でも exit 0 になる gate を作らない)。
// 「メモリ有界」= 後半 (中点 → 末尾) で wasm memory が増えないこと + 絶対上限以内。
export function judgeStress(samples, { minFrames = 1, maxMemBytes = 256 * 1024 * 1024, maxOutFullWaits = 0 } = {}) {
  const f = [];
  if (samples.length < 4) { f.push(`samples ${samples.length} < 4 (判定不能)`); return f; }
  const first = samples[0], last = samples[samples.length - 1];
  if (last.frames - first.frames < minFrames) f.push(`frames ${last.frames - first.frames} < ${minFrames}`);
  if (last.inDropped !== 0) f.push(`input ring dropped ${last.inDropped} events (want 0)`);
  if (last.outFullWaits > maxOutFullWaits) f.push(`out ring full waits ${last.outFullWaits} > ${maxOutFullWaits}`);
  for (let i = 1; i < samples.length; i++) if (samples[i].frames <= samples[i - 1].frames) { f.push(`frames stalled between samples ${i - 1}→${i} (${samples[i - 1].frames}→${samples[i].frames})`); break; }
  const half = samples[Math.floor(samples.length / 2)];
  if (last.memBytes > half.memBytes) f.push(`wasm memory still growing in 2nd half: ${half.memBytes} → ${last.memBytes} bytes`);
  if (last.memBytes > maxMemBytes) f.push(`wasm memory ${last.memBytes} > bound ${maxMemBytes}`);
  const g0 = JSON.stringify(first.gens), g1 = JSON.stringify(last.gens);
  if (g0 !== g1) f.push(`surface gen changed during run: ${g0} → ${g1} (surface 再生成 = churn/leak)`);
  return f;
}

// RGBA バッファ vs 期待 RGB (行 stride 同一 w*3) の画素差。stress の independent oracle で使う
export function countPixelDiff(rgba, wantRGB, w, h) {
  let n = 0;
  for (let i = 0; i < w * h; i++) if (rgba[i * 4] !== wantRGB[i * 3] || rgba[i * 4 + 1] !== wantRGB[i * 3 + 1] || rgba[i * 4 + 2] !== wantRGB[i * 3 + 2]) n++;
  return n;
}
