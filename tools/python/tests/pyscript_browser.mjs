// .pyscript 同梱スクリプトを agent-browser (tools/e2e) 経由で Chrome 上の wasm CPython で実行する (PY-11 / #466)。
//   node tests/pyscript_browser.mjs --dump work/pyscript_chrome.json [--chrome /usr/bin/google-chrome] [--scripts /work/pyscripts.json]
// 前提: build_flpy.sh 済み・`node tests/pyscript_e2e.mjs --export-scripts work/pyscripts.json` 済み・tools/e2e で `npm ci --ignore-scripts` 済み。
// exit: 0 = 全 check PASS / 1 = FAIL・ページ例外・タイムアウト (不合格を 0 で返さない)。
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { createDriver } from "../../e2e/suite/drivers/agent-browser.mjs";

const here = path.dirname(new URL(import.meta.url).pathname);
const arg = (k, d = null) => { const i = process.argv.indexOf(k); return i >= 0 ? process.argv[i + 1] : d; };
const dump = arg("--dump");
const chrome = arg("--chrome", "/usr/bin/google-chrome");
const scripts = arg("--scripts", "/work/pyscripts.json"); // tools/python 配下の URL パス。ネガコンで改変版に差し替える
if (!fs.existsSync(path.join(here, "../work/pyscripts.json"))) { console.error("work/pyscripts.json が無い (node tests/pyscript_e2e.mjs --export-scripts work/pyscripts.json)"); process.exit(2); }

const server = spawn(process.execPath, [path.join(here, "browser/serve.mjs"), "0"], { stdio: ["ignore", "pipe", "inherit"] });
const port = await new Promise((res) => server.stdout.on("data", (d) => { const m = /PORT (\d+)/.exec(String(d)); if (m) res(m[1]); }));
const drv = await createDriver({ chrome, session: `pyscript-${process.pid}` });
let code = 1;
try {
  const t0 = Date.now();
  await drv.open(`http://127.0.0.1:${port}/tests/browser/pyscript.html?scripts=${encodeURIComponent(scripts)}`);
  const done = await drv.waitFn(`document.getElementById('result').textContent !== 'PENDING'`, 240000);
  const text = await drv.eval(`document.getElementById('result').textContent`);
  const m = /^RESULT (.*)$/s.exec(text || "");
  if (!done || !m) { console.error("タイムアウトまたは結果なし:", String(text).slice(0, 300), await drv.pageErrors()); }
  else {
    const out = JSON.parse(m[1]);
    out.wall_seconds = Number(((Date.now() - t0) / 1000).toFixed(1));
    out.driver = `${drv.name} ${drv.version}`;
    if (out.error) console.error("ページ内例外:", out.error);
    else {
      for (const r of out.results) console.log(r.ok ? "PASS" : "FAIL", r.name, r.ok ? "" : r.detail);
      console.log(JSON.stringify({ env: out.env, crossOriginIsolated: out.crossOriginIsolated, driver: out.driver, ...out.summary, wall_seconds: out.wall_seconds }));
      if (dump) { fs.mkdirSync(path.dirname(dump), { recursive: true }); fs.writeFileSync(dump, JSON.stringify(out)); }
      code = out.summary.fail === 0 && out.summary.total > 0 && out.crossOriginIsolated ? 0 : 1;
    }
  }
} finally { await drv.close(); server.kill(); }
process.exit(code);
