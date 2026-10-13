// browser_e2e_t13.mjs — shimx×gui 共存 wasm を headless Chrome で走らせ、browserEnv の window.open / File System Access 経路を検査する (#956 / #1159 SHX-T19)。
//   usage: node browser_e2e_t13.mjs <webdir>   (browser_e2e_t13.sh が webdir を作る)
//   user activation が要る host 呼出は、ページの #gate を CDP の Input.dispatchMouseEvent (実マウス) で押させる。
//   exit 0 = 全 PASS / 1 = 判定 FAIL / 2 = 実行エラー / 3 = watchdog
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { startServer, launchChrome } from "../e2e/cdp_lib.mjs";

const WEB = path.resolve(process.argv[2]);
const CHROME = process.env.CHROME || "google-chrome";
const wd = setTimeout(() => { console.error("[browser] WATCHDOG timeout"); process.exit(3); }, Number(process.env.E2E_TIMEOUT_MS || 240000));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { srv, port } = await startServer([["/", WEB]]);
const udd = fs.mkdtempSync(path.join(process.env.OPENCODE_TMP || os.tmpdir(), "shx-browser-chrome-"));
const br = await launchChrome(CHROME, udd, 800, 600);
const cdp = br.cdp;
const consoleLines = [];
const checks = [];
const ck = (name, ok, why = "") => { checks.push([name, !!ok, why]); console.log(`${ok ? "PASS" : "FAIL"} browser: ${name}${ok ? "" : " — " + why}`); };
let code = 2;
try {
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const S = (method, params = {}) => cdp.send(method, params, sessionId);
  cdp.on((m) => {
    if (m.sessionId !== sessionId) return;
    if (m.method === "Runtime.consoleAPICalled") consoleLines.push(m.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
    if (m.method === "Runtime.exceptionThrown") consoleLines.push("EXC " + (m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text || ""));
  });
  await S("Page.enable"); await S("Runtime.enable");
  const E = async (expr) => { const r = await S("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error("eval: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text)); return r.result.value; };
  await S("Page.navigate", { url: `http://127.0.0.1:${port}/browser_index.html` });

  const clickGate = async () => {
    for (let i = 0; i < 600; i++) {
      const rect = await E(`(() => { const b = document.getElementById("gate"); if (!b || b.style.display === "none") return null; const r = b.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, label: b.textContent }; })()`);
      if (rect) {
        await S("Input.dispatchMouseEvent", { type: "mouseMoved", x: rect.x, y: rect.y });
        await S("Input.dispatchMouseEvent", { type: "mousePressed", x: rect.x, y: rect.y, button: "left", clickCount: 1 });
        await S("Input.dispatchMouseEvent", { type: "mouseReleased", x: rect.x, y: rect.y, button: "left", clickCount: 1 });
        return rect.label;
      }
      await sleep(100);
    }
    throw new Error("gate never shown");
  };
  // host 呼出が gate を出すたびに実クリック。gate が無くなるまで押し続ける (wasm の main 完了まで)
  const pumping = (async () => { const labels = []; for (;;) { const done = await E(`!!window.__report`); if (done) break; try { labels.push(await clickGate()); } catch (e) { if (String(e.message).includes("never shown")) { await sleep(100); continue; } throw e; } } return labels; })();
  const labels = await Promise.race([pumping, sleep(200000).then(() => { throw new Error("pump timeout"); })]);
  const rep = await E(`window.__report`);
  if (rep.error) throw new Error("page error: " + rep.error);
  code = rep.code;

  const m = /RESULT pass=(\d+) fail=(\d+)/.exec(rep.out.join("\n"));
  ck("wasm 側 C テスト fail=0 (web build)", m && m[2] === "0", `RESULT=${m?.[0]}`);
  ck("exit code 0", code === 0, `code=${code}`);
  const wantOpen = ["https://example.com/a?b=1", "mailto:x@example.com", "http://example.com/old-style", "https://blocked.example/"];
  ck("window.open に渡った URL (C 側で拒否した 4 件は host に来ない)", JSON.stringify(rep.opened.map((o) => o.url)) === JSON.stringify(wantOpen), JSON.stringify(rep.opened));
  ck("window.open は transient user activation 下で呼ばれた", rep.opened.length > 0 && rep.opened.every((o) => o.active), JSON.stringify(rep.opened));
  ck("open picker 5 回 + save 1 回", rep.opens.length === 5 && rep.saves.length === 1, `opens=${rep.opens.length} saves=${rep.saves.length}`);
  ck("picker は user activation 下で開いた", rep.opens.every((o) => o.active) && rep.saves.every((o) => o.active), JSON.stringify(rep.gates));
  ck("filter → types 変換 (WAV only)", JSON.stringify(rep.opens[0]?.types) === JSON.stringify([{ description: "WAV (*.wav)", accept: { "application/octet-stream": [".wav"] } }]), JSON.stringify(rep.opens[0]?.types));
  ck("multi フラグ", JSON.stringify(rep.opens.map((o) => o.multiple)) === JSON.stringify([false, false, true, false, false]), JSON.stringify(rep.opens.map((o) => o.multiple)));
  ck("ステージング: kick.wav の内容 (buffer 反映)", JSON.stringify(rep.stage["kick.wav"]) === JSON.stringify([1, 2, 3]), JSON.stringify(rep.stage["kick.wav"]));
  ck("ステージング: multi 3 本 (buffer 反映)", JSON.stringify([rep.stage["a.wav"], rep.stage["b.wav"], rep.stage["c.mid"]]) === JSON.stringify([[10], [11], [12]]), JSON.stringify([rep.stage["a.wav"], rep.stage["b.wav"], rep.stage["c.mid"]]));
  ck("save: FL が書いた内容が実 handle へ反映", rep.flushed === 1 && JSON.stringify(rep.saved) === JSON.stringify([Array.from(Buffer.from("FLP-DATA"))]), `flushed=${rep.flushed} saved=${JSON.stringify(rep.saved)}`);
  ck("host log に想定外エラー無し (想定: blocked 1 + picker failure 1)", rep.log.filter((l) => !/blocked|simulated/.test(l)).length === 0, JSON.stringify(rep.log));
  ck("ページで未捕捉の例外無し", !consoleLines.some((l) => l.startsWith("EXC")), consoleLines.filter((l) => l.startsWith("EXC")).slice(0, 3).join(" | "));
  const bver = (await cdp.send("Browser.getVersion")).product;
  console.log(`[browser] chrome=${bver} gates=${labels.length} (${rep.gates.map((g) => g.label).join(" / ")})`);
  if (rep.out.length) console.log("[browser] wasm stdout tail:\n" + rep.out.slice(-6).join("\n"));
} catch (e) {
  console.error("[browser] ERROR", e.message, "\n console tail:", consoleLines.slice(-10).join(" | "));
  code = 2;
} finally {
  const exited = new Promise((r) => br.chrome.once("exit", r));
  br.close(); srv.close();
  await Promise.race([exited, sleep(5000)]);
  try { fs.rmSync(udd, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch { /* Chrome 終了直後の書込残り (一時dir のみ) */ }
  clearTimeout(wd);
}
const bad = checks.filter((c) => !c[1]).length;
console.log(`BROWSER RESULT pass=${checks.length - bad} fail=${bad}`);
process.exit(bad || code !== 0 ? (checks.length ? 1 : 2) : 0);
