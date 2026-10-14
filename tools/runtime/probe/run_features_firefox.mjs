#!/usr/bin/env node
// Firefox 機能マトリクス実測 (geckodriver / WebDriver classic 経由):
//   node tools/runtime/probe/run_features_firefox.mjs  → work/features_result_firefox.json
// 環境変数: FIREFOX_BIN (既定 firefox) / GECKODRIVER_BIN (既定 geckodriver)
//   FIREFOX_HEADLESS=0 で -headless を付けない (Xvfb 等の仮想ディスプレイ上で実行する場合)
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { serve } from "../lib/serve.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const GD_PORT = 4444 + Math.floor(Math.random() * 1000);
const gd = spawn(process.env.GECKODRIVER_BIN || "geckodriver", ["--port", String(GD_PORT)], { stdio: "ignore" });
const wd = async (method, p, body) => {
  if (process.env.RUNTIME_VERBOSE) console.error("[wd]", method, p.replace(/^\/session\/[^/]+/, ""));
  const r = await fetch(`http://127.0.0.1:${GD_PORT}${p}`, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json();
  if (j.value?.error) throw new Error(`${j.value.error}: ${j.value.message}`);
  return j.value;
};
for (let i = 0; ; i++) {
  try { await fetch(`http://127.0.0.1:${GD_PORT}/status`); break; } catch { if (i > 100) throw new Error("geckodriver start timeout"); await new Promise((r) => setTimeout(r, 100)); }
}

const srv = await serve([{ prefix: "/", dir: here }]);
let sid;
try {
  const caps = { browserName: "firefox", pageLoadStrategy: "none", "moz:firefoxOptions": {
    binary: process.env.FIREFOX_BIN || undefined,
    args: process.env.FIREFOX_HEADLESS === "0" ? [] : ["-headless"],
    prefs: { "media.autoplay.default": 0, "media.autoplay.blocking_policy": 0, ...JSON.parse(process.env.FIREFOX_PREFS || "{}") },
  } };
  const s = await wd("POST", "/session", { capabilities: { alwaysMatch: caps } });
  sid = s.sessionId;
  await wd("POST", `/session/${sid}/timeouts`, { script: 30000 });
  await wd("POST", `/session/${sid}/url`, { url: `http://127.0.0.1:${srv.port}/features.html` });
  const t0 = Date.now();
  let r;
  while (!(r = await wd("POST", `/session/${sid}/execute/sync`, { script: "return window.__result ? JSON.stringify(window.__result) : null", args: [] }))) {
    if (Date.now() - t0 > 120000) {
      const step = await wd("POST", `/session/${sid}/execute/sync`, { script: "return window.__step + ' | ' + JSON.stringify(window.__partial)", args: [] });
      throw new Error("waitFor(__result) timeout; last step / partial: " + step);
    }
    await new Promise((res) => setTimeout(res, 200));
  }
  const out = JSON.parse(r);
  out.firefox = s.capabilities.browserVersion;
  mkdirSync(path.join(here, "../work"), { recursive: true });
  writeFileSync(path.join(here, "../work/features_result_firefox.json"), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 1));
} finally {
  if (sid) await wd("DELETE", `/session/${sid}`).catch(() => {});
  gd.kill();
  await srv.close();
}
