// headless Chrome を CDP (node 組込 WebSocket) で直接駆動する最小クライアント。
// 依存ゼロ (puppeteer 不要)。page console / 例外 / worker console を収集する。
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, existsSync, rmSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const CHROME = process.env.CHROME_BIN || "google-chrome";

export async function launchChrome({ userDataDir, extraArgs = [], headless = "new", keepProfile = false } = {}) {
  const base = process.env.RUNTIME_TMP || "/tmp/opencode";
  mkdirSync(base, { recursive: true });
  const udd = userDataDir || mkdtempSync(path.join(base, "chrome-prof-"));
  const args = [
    `--headless=${headless}`, "--no-sandbox", "--disable-gpu", "--no-first-run",
    "--no-default-browser-check", "--disable-background-networking",
    "--remote-debugging-port=0", `--user-data-dir=${udd}`,
    "--autoplay-policy=no-user-gesture-required",
    ...extraArgs, "about:blank",
  ];
  rmSync(path.join(udd, "DevToolsActivePort"), { force: true }); // 再利用プロファイルの stale port を除去
  const proc = spawn(CHROME, args, { stdio: ["ignore", "ignore", "pipe"] });
  let stderr = "";
  proc.stderr.on("data", (d) => (stderr += d));
  const portFile = path.join(udd, "DevToolsActivePort");
  const t0 = Date.now();
  while (!existsSync(portFile)) {
    if (proc.exitCode !== null) throw new Error("chrome exited: " + stderr.slice(-500));
    if (Date.now() - t0 > 30000) throw new Error("chrome start timeout");
    await new Promise((r) => setTimeout(r, 50));
  }
  const [port] = readFileSync(portFile, "utf8").split("\n");
  const ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  const browser = new CDP(ver.webSocketDebuggerUrl);
  await browser.open();
  const api = {
    proc, userDataDir: udd, version: ver.Browser, browser,
    async newPage(url) {
      const { targetId } = await browser.send("Target.createTarget", { url: "about:blank" });
      const { sessionId } = await browser.send("Target.attachToTarget", { targetId, flatten: true });
      const page = new Page(browser, sessionId, targetId);
      await page.init();
      if (url) await page.goto(url);
      return page;
    },
    async close() {
      try { await browser.send("Browser.close"); } catch {}
      browser.ws.close();
      await new Promise((r) => (proc.exitCode !== null ? r() : proc.once("exit", r)));
      if (!keepProfile && !userDataDir) rmSync(udd, { recursive: true, force: true });
    },
  };
  return api;
}

export class CDP {
  constructor(url) { this.url = url; this.id = 0; this.pending = new Map(); this.listeners = []; }
  open() {
    return new Promise((res, rej) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => res();
      this.ws.onerror = (e) => rej(new Error("ws error"));
      this.ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.id) {
          const p = this.pending.get(m.id);
          if (p) { this.pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
        } else for (const l of this.listeners) l(m);
      };
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }
  on(fn) { this.listeners.push(fn); }
}

export class Page {
  constructor(cdp, sessionId, targetId) {
    this.cdp = cdp; this.sessionId = sessionId; this.targetId = targetId;
    this.logs = []; this.exceptions = []; this.workerSessions = new Map();
  }
  send(method, params) { return this.cdp.send(method, params, this.sessionId); }
  async init() {
    this.cdp.on((m) => {
      if (m.sessionId === this.sessionId || this.workerSessions.has(m.sessionId)) this._event(m);
      if (m.method === "Target.attachedToTarget" && m.sessionId === this.sessionId) {
        const ws = m.params.sessionId;
        this.workerSessions.set(ws, m.params.targetInfo);
        this.cdp.send("Runtime.enable", {}, ws).catch(() => {});
        this.cdp.send("Runtime.runIfWaitingForDebugger", {}, ws).catch(() => {});
      }
    });
    await this.send("Runtime.enable");
    await this.send("Page.enable");
    await this.send("Target.setAutoAttach", { autoAttach: true, waitForDebuggerOnStart: true, flatten: true });
  }
  _event(m) {
    if (m.method === "Runtime.consoleAPICalled") {
      const txt = m.params.args.map((a) => (a.value !== undefined ? (typeof a.value === "string" ? a.value : JSON.stringify(a.value)) : a.description ?? a.type)).join(" ");
      const src = this.workerSessions.has(m.sessionId) ? "worker" : "page";
      this.logs.push({ src, type: m.params.type, text: txt });
      if (process.env.RUNTIME_VERBOSE) console.error(`[${src}:${m.params.type}] ${txt}`);
    } else if (m.method === "Runtime.exceptionThrown") {
      const d = m.params.exceptionDetails;
      const t = d.exception?.description || d.text;
      this.exceptions.push(t);
      if (process.env.RUNTIME_VERBOSE) console.error("[exception]", t);
    }
  }
  async goto(url) {
    const loaded = new Promise((res) => {
      const fn = (m) => { if (m.sessionId === this.sessionId && m.method === "Page.loadEventFired") { res(); } };
      this.cdp.on(fn);
    });
    await this.send("Page.navigate", { url });
    await loaded;
  }
  async evaluate(expression, { awaitPromise = true, timeout = 120000 } = {}) {
    const p = this.send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true, userGesture: true });
    let to;
    const r = await Promise.race([p, new Promise((_, rej) => (to = setTimeout(() => rej(new Error("evaluate timeout: " + expression.slice(0, 80))), timeout)))]);
    clearTimeout(to);
    if (r.exceptionDetails) throw new Error("evaluate exception: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value;
  }
  /** expr が truthy を返すまで 100ms 間隔で polling し、その値を返す */
  async waitForExpr(expr, timeout = 120000) {
    const t0 = Date.now();
    for (;;) {
      const v = await this.evaluate(expr, { awaitPromise: false });
      if (v) return v;
      if (Date.now() - t0 > timeout) throw new Error(`waitForExpr timeout: ${expr.slice(0, 80)}`);
      await new Promise((r) => setTimeout(r, 100));
    }
  }
  /** window[name] が非 undefined になるまで 100ms 間隔で polling (固定 sleep ではなく条件待ち) */
  async waitFor(name, timeout = 120000) {
    const t0 = Date.now();
    for (;;) {
      const v = await this.evaluate(`window[${JSON.stringify(name)}]`, { awaitPromise: false });
      if (v !== undefined && v !== null) return v;
      if (this.exceptions.length && process.env.RUNTIME_FAILFAST) throw new Error("page exception: " + this.exceptions[0]);
      if (Date.now() - t0 > timeout) throw new Error(`waitFor(${name}) timeout`);
      await new Promise((r) => setTimeout(r, 100));
    }
  }
}
