// PY-4 (#77) e2e: アプリ (Vite dev server, COOP/COEP) を headless Chrome で開き、MCP JSON-RPC を UI / devtools から実行する。
//   node tools/python/tests/mcp_ui_check.mjs [--neg]    -> "MCP UI OK {...}" / exit 0  (--neg: "NEG-CONTROL DETECTED" / exit 1)
// 前提: tools/python/dist/ (build_flpy.sh) と tools/python/work/{MCPTools.pyc,midi.py,utils.py} (fetch_inputs.sh 相当で利用者の FL から供給)。
// 検証: (1) 供給前は start() が失敗 (リポジトリ非同梱の確認) (2) /py/work/ は 404 (配信物に FL 由来ファイルが無い)
//       (3) UI: ファイル選択 → 起動 → tools/list = 48 → get_tempo を tools/call (4) devtools: window.flMcp.rpc で tools/list / tools/call / 未知 tool
//   --neg: MCPTools.pyc を 1 バイト壊して供給 → 起動が失敗し、tools/list=48 の判定が FAIL することを確認 (ネガティブコントロール)
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { createServer } from "vite";
import { launchChrome } from "../../runtime/lib/chrome.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const work = path.join(here, "../work");
const neg = process.argv.includes("--neg");
const checks = {};
const check = (name, cond, extra) => { checks[name] = !!cond; if (!cond) console.error(`FAIL ${name}`, extra ?? ""); };

const tmp = mkdtempSync(path.join(tmpdir(), "mcp-ui-"));
const files = { "MCPTools.pyc": path.join(work, "MCPTools.pyc"), "midi.py": path.join(work, "midi.py"), "utils.py": path.join(work, "utils.py") };
if (neg) {
  const b = readFileSync(files["MCPTools.pyc"]);
  b[0] ^= 0xff; // pyc magic 破壊
  files["MCPTools.pyc"] = path.join(tmp, "MCPTools.pyc");
  writeFileSync(files["MCPTools.pyc"], b);
}

const t0 = Date.now();
const vite = await createServer({ root, logLevel: "warn", server: { port: 0, host: "127.0.0.1", strictPort: false } });
await vite.listen();
const base = `http://127.0.0.1:${vite.config.server.port ?? vite.httpServer.address().port}`;
const chrome = await launchChrome();
let out = { ok: false };
try {
  const page = await chrome.newPage();
  await page.goto(`${base}/?mcp=1`);
  check("crossOriginIsolated", await page.evaluate("crossOriginIsolated"));
  check("flMcp exposed", await page.evaluate("typeof window.flMcp?.rpc === 'function'"));

  // (1) 供給前の start() は失敗する
  const pre = await page.evaluate(`window.flMcp.start().then(() => "started", (e) => String(e))`);
  check("start without FL files rejects", /供給が必要/.test(pre), pre);
  // (2) FL 由来ファイルは配信しない / 許可外パスも 404
  const status = await page.evaluate(`Promise.all(["/py/work/MCPTools.pyc", "/py/work/midi.py", "/py/src/fl_rt.py", "/py/dist/flpy.wasm"].map((u) => fetch(u).then((r) => r.status)))`);
  check("work/ not served (404,404,404) and flpy.wasm served (200)", JSON.stringify(status) === "[404,404,404,200]", status);

  // (3) UI 経路: file input へ 3 ファイルを設定 → 起動 → tool 選択 → tools/call
  const { root: docRoot } = await page.send("DOM.getDocument", {});
  const { nodeId } = await page.send("DOM.querySelector", { nodeId: docRoot.nodeId, selector: "#mcp-files" });
  await page.send("DOM.setFileInputFiles", { nodeId, files: Object.values(files) });
  await page.waitForExpr(`document.getElementById("mcp-start") && !document.getElementById("mcp-start").disabled`, 10000);
  check("UI: start enabled after 3 files", true);
  await page.evaluate(`document.getElementById("mcp-start").click()`);
  let stateText = "";
  try {
    stateText = await page.waitForExpr(`/起動済み: |失敗: /.test(document.getElementById("mcp-state").textContent) && document.getElementById("mcp-state").textContent`, 60000);
  } catch (e) { stateText = String(e); }
  check("UI: tools/list = 48", /tools\/list = 48 /.test(stateText), stateText);
  if (neg) check("neg: broken pyc is reported as 失敗 (not a hang)", /^失敗:[\s\S]*pyc magic mismatch/.test(stateText), stateText);
  if (/tools\/list = 48 /.test(stateText)) {
    await page.evaluate(`(() => { const s = document.getElementById("mcp-tool"); s.value = "get_tempo"; document.getElementById("mcp-call").click(); })()`);
    const outText = await page.waitForExpr(`document.getElementById("mcp-out").textContent`, 20000);
    check("UI: tools/call get_tempo", /^ok: Current tempo is 130 BPM/.test(outText), outText);
    out.ui = { state: stateText, out: outText };

    // (4) devtools 経路
    const dev = await page.evaluate(`(async () => {
      const r = {};
      const l = await flMcp.rpc({ jsonrpc: "2.0", id: 1, method: "tools/list" });
      r.list = l.result.tools.length; r.listId = l.id; r.schema = !!l.result.tools[0].inputSchema;
      const set = await flMcp.rpc(JSON.stringify({ jsonrpc: "2.0", id: "s", method: "tools/call", params: { name: "set_tempo", arguments: { bpm: 140 } } }));
      const get = await flMcp.call("get_tempo");
      r.set = set.result; r.get = get;
      const bad = await flMcp.rpc({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "no_such_tool", arguments: {} } });
      r.bad = bad.result;
      const priv = await flMcp.rpc({ jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "get_mcp_tools_json", arguments: {} } });
      r.priv = priv.result;
      const err = await flMcp.rpc({ jsonrpc: "2.0", id: 5, method: "tools/call", params: { name: "set_tempo", arguments: { nope: 1 } } });
      r.badArgs = err.result;
      r.nomethod = (await flMcp.rpc({ jsonrpc: "2.0", id: 6, method: "x/y" })).error?.code;
      r.parse = (await flMcp.rpc("{")).error?.code;
      return r;
    })()`);
    check("devtools: tools/list = 48 with inputSchema, id echoed", dev.list === 48 && dev.schema && dev.listId === 1, dev);
    check("devtools: tools/call set_tempo isError=false", dev.set.isError === false && dev.set.content[0].type === "text", dev.set);
    check("devtools: get_tempo reflects set_tempo(140)", /Current tempo is 140 BPM/.test(dev.get.text) && dev.get.isError === false, dev.get);
    check("unknown tool -> isError=true", dev.bad.isError === true && /Unknown tool/.test(dev.bad.content[0].text), dev.bad);
    check("non-tool __main__ attr (get_mcp_tools_json) -> isError=true", dev.priv.isError === true, dev.priv);
    check("known tool, bad arguments -> isError=true", dev.badArgs.isError === true, dev.badArgs);
    check("unknown method -> -32601, bad JSON -> -32700", dev.nomethod === -32601 && dev.parse === -32700, dev);
    out.devtools = dev;
  }
  out.exceptions = page.exceptions.slice(0, 3);
} finally {
  await chrome.close();
  await vite.close();
  rmSync(tmp, { recursive: true, force: true });
}
// --neg の期待: 主判定 (tools/list = 48) が FAIL し、原因が pyc magic mismatch として報告される (= 判定が壊れた入力を検出できる)。終了コード: 通常 PASS=0 / FAIL=2、--neg は検出できたとき 1 (FAIL を検出できていなければ 2)
const ok = Object.keys(checks).length > 0 && (neg ? Object.entries(checks).every(([k, v]) => (k === "UI: tools/list = 48" ? !v : v)) : Object.values(checks).every(Boolean));
out = { ...out, ok, checks, seconds: (Date.now() - t0) / 1000, neg };
console.log((ok ? (neg ? "MCP UI NEG-CONTROL DETECTED " : "MCP UI OK ") : "MCP UI FAIL ") + JSON.stringify(out));
process.exit(ok ? (neg ? 1 : 0) : 2);
