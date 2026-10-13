// cdp_lib.mjs — headless Chrome E2E ドライバの共通部 (静的サーバ COOP/COEP / 最小 CDP クライアント / PNG・PPM)。GUI-13 (#615) の text_e2e.mjs が使う。
//   (e2e.mjs は従来のまま自前の同等実装を持つ。統合は別途; 本ファイルは e2e.mjs を変更しないために切り出した)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { spawn } from "node:child_process";

const MIME = { ".js": "text/javascript", ".mjs": "text/javascript", ".html": "text/html", ".wasm": "application/wasm", ".ppm": "application/octet-stream", ".json": "application/json", ".ttf": "font/ttf" };
/** routes: [[urlPrefix, dir], ...]。dynamic(url) が {type, body} を返せばそれを優先。COOP/COEP 付き (SharedArrayBuffer 用) */
export function startServer(routes, dynamic) {
  const srv = http.createServer((req, res) => {
    const full = decodeURIComponent(req.url || "/");
    let url = full.split("?")[0];
    const headers = { "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp", "Cross-Origin-Resource-Policy": "same-origin", "Cache-Control": "no-store" };
    const dyn = dynamic?.(url, full);
    if (dyn) { res.writeHead(200, { ...headers, "Content-Type": dyn.type }); res.end(dyn.body); return; }
    const hit = routes.find(([p]) => url.startsWith(p));
    if (!hit) { res.writeHead(404, headers); res.end("not found"); return; }
    const file = path.join(hit[1], url.slice(hit[0].length));
    if (!file.startsWith(hit[1]) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404, headers); res.end("not found " + url); return; }
    res.writeHead(200, { ...headers, "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => srv.listen(0, "127.0.0.1", () => resolve({ srv, port: srv.address().port })));
}

export class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.handlers = [];
    ws.addEventListener("message", (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id);
        m.error ? reject(new Error(`${m.error.message} ${m.error.data || ""}`)) : resolve(m.result);
      } else if (m.method) for (const h of this.handlers) h(m);
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }
  on(h) { this.handlers.push(h); }
}

/** headless Chrome を起動して CDP に接続。戻り {chrome, cdp, close()} */
export async function launchChrome(chromeBin, userDataDir, w, h) {
  const chrome = spawn(chromeBin, ["--headless=new", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0", `--user-data-dir=${userDataDir}`,
    "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--force-device-scale-factor=1", `--window-size=${w},${h}`, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
  const wsUrl = await new Promise((resolve, reject) => {
    let acc = "";
    chrome.stderr.on("data", (d) => { acc += d; const m = /DevTools listening on (ws:\/\/\S+)/.exec(acc); if (m) resolve(m[1]); });
    chrome.on("exit", (c) => reject(new Error("chrome exited early code=" + c + "\n" + acc)));
  });
  const ws = new WebSocket(wsUrl); await new Promise((res, rej) => { ws.addEventListener("open", res); ws.addEventListener("error", rej); });
  return { chrome, cdp: new CDP(ws), close() { try { chrome.kill("SIGKILL"); } catch { /* 終了済み */ } } };
}

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
export function writePPM(file, w, h, getPx) {
  const out = Buffer.alloc(w * h * 3);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const [r, g, b] = getPx(x, y), o = (y * w + x) * 3; out[o] = r; out[o + 1] = g; out[o + 2] = b; }
  fs.writeFileSync(file, Buffer.concat([Buffer.from(`P6\n${w} ${h}\n255\n`), out]));
}
