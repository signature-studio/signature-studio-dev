// Safari 駆動 (safaridriver の WebDriver classic を直叩き, 依存なし) + COOP/COEP 付き静的サーバ (chrome.mjs の serve を共用)。
// withChrome (chrome.mjs) と同じ形の cdp ({ navigate, eval }) を返すので、ページ側の window.__done の取り方は同じ。
// 使い方: await withSafari({ root, page }, async (sf) => { await sf.eval("window.__done"); })
// 前提 (macOS): `sudo safaridriver --enable` で remote automation を許可しておく。Safari は headless でないので GUI セッションが要る。
// WebDriver BiDi は使わない (BiDi 対応の確認は safari_probe.mjs)。
import { spawn } from "node:child_process";
import net from "node:net";
import { serve } from "./chrome.mjs";

const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));
const freePort = () => new Promise((ok, ng) => {
  const s = net.createServer();
  s.on("error", ng);
  s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => ok(p)); });
});

// safaridriver を起動し、待受けを /status で確かめてから返す。req は WebDriver classic の 1 リクエスト (値 value を返す)
export async function startSafaridriver() {
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const cp = spawn(process.env.SAFARIDRIVER ?? "safaridriver", ["-p", String(port)], { stdio: ["ignore", "pipe", "pipe"] });
  let errbuf = "", spawnErr = null;
  cp.on("error", (e) => (spawnErr = e));
  cp.stdout.on("data", (d) => (errbuf += d));
  cp.stderr.on("data", (d) => (errbuf += d));
  const t0 = Date.now();
  for (;;) {
    try { await fetch(`${base}/status`); break; } catch {
      if (spawnErr) throw new Error(`safaridriver を起動できない (${spawnErr.message})。Safari の実行は macOS の GUI セッションと \`sudo safaridriver --enable\` が要る`);
      if (cp.exitCode !== null) throw new Error(`safaridriver exit ${cp.exitCode}\n${errbuf.slice(-2000)}`);
      if (Date.now() - t0 > 60000) { cp.kill("SIGTERM"); throw new Error(`safaridriver 待受けタイムアウト\n${errbuf.slice(-2000)}`); }
      await sleep(200);
    }
  }
  const req = async (method, p, body) => {
    const r = await fetch(base + p, { method, headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.value?.error) throw new Error(`${j.value?.error ?? r.status}: ${j.value?.message ?? ""}`);
    return j.value;
  };
  return { req, close: () => cp.kill("SIGTERM") };
}

export async function withSafari({ root, page }, fn) {
  const { srv, port } = await serve(root);
  const sd = await startSafaridriver();
  let sid = null;
  try {
    sid = (await sd.req("POST", "/session", { capabilities: { alwaysMatch: { browserName: "Safari" } } })).sessionId;
    const S = `/session/${sid}`;
    // 既定の script timeout は 30 s。1 シナリオの window.__done は十数秒かかるので延ばす (WebDriver の上限内)
    await sd.req("POST", `${S}/timeouts`, { script: 600000 });
    const navigate = (pg) => sd.req("POST", `${S}/url`, { url: `http://127.0.0.1:${port}/${pg}` });
    // 評価結果は JSON 文字列で返し、Node 側で parse する (chrome.mjs の returnByValue と同じ値にする)
    const evaluate = async (expression) => {
      const script = `const done = arguments[arguments.length - 1];
(async () => { try { const v = await (${expression}); done(v === undefined ? null : JSON.stringify(v)); } catch (e) { done({ __exc: String(e) }); } })();`;
      const v = await sd.req("POST", `${S}/execute/async`, { script, args: [] });
      if (v?.__exc) throw new Error("page exception: " + v.__exc);
      return typeof v === "string" ? JSON.parse(v) : undefined;
    };
    await navigate(page);
    return await fn({ navigate, eval: evaluate });
  } finally {
    if (sid) await sd.req("DELETE", `/session/${sid}`).catch(() => {});
    sd.close();
    srv.close();
  }
}
