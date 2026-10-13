// browser_e2e.mjs — SHX-T19 (#1159): 実 Chrome で browserEnv の window.open / File System Access 経路を CDP から検査する。
//   usage: node browser_e2e.mjs <webdir (coexistWeb.js)> <jsdir (gui_hostcall.js)>
//   user activation は CDP Runtime.evaluate の userGesture:true で与える (有/無しを同じ page で切り替えて比較する)。
//   exit 0 = 全 PASS / 1 = FAIL / 2 = 実行エラー
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startServer, launchChrome } from "../e2e/cdp_lib.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const [WEBDIR, JSDIR] = process.argv.slice(2).map((p) => path.resolve(p));
const CHROME = process.env.CHROME || "google-chrome";
const checks = [];
const ck = (name, ok, why = "") => { checks.push([name, !!ok]); console.log(`${ok ? "PASS" : "FAIL"} browser: ${name}${ok ? "" : " — " + why}`); };
const wd = setTimeout(() => { console.error("[browser] WATCHDOG timeout"); process.exit(2); }, 240000);

const HTML = `<!doctype html><meta charset="utf-8"><script src="/wasm/coexistWeb.js"></script><script type="module" src="/page/browser_page.mjs"></script>`;
const { srv, port } = await startServer(
  [["/wasm/", WEBDIR], ["/js/", JSDIR], ["/page/", HERE]],
  (url) => (url === "/" ? { type: "text/html", body: HTML } : null),
);
const udd = fs.mkdtempSync(path.join(process.env.RUNNER_TEMP || os.tmpdir(), "shx-browser-"));
const br = await launchChrome(CHROME, udd, 480, 360);
const { cdp } = br;
const ver = await fetch(`http://127.0.0.1:${new URL(br.cdp.ws.url).port}/json/version`).then((r) => r.json()).catch(() => null);
let fail = 0;
try {
  const { targetId } = await cdp.send("Target.createTarget", { url: `http://127.0.0.1:${port}/` });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const S = (m, p) => cdp.send(m, p, sessionId);
  const logs = []; cdp.on((m) => { if (m.sessionId === sessionId && m.method === "Runtime.exceptionThrown") logs.push(JSON.stringify(m.params.exceptionDetails).slice(0, 400)); });
  await S("Runtime.enable"); await S("Page.enable");
  const ev = async (expr, gesture = false) => {
    const r = await S("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true, userGesture: gesture, timeout: 60000 });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  for (let t = 0; ; t++) {
    const ok = await ev("typeof window.__init === 'function' && typeof window.coexistWeb === 'function'").catch(() => false);
    if (ok) break;
    if (t > 100) throw new Error("page did not load");
    await new Promise((r) => setTimeout(r, 100));
  }
  await ev("window.__init()");
  // user activation の失効を待つ (Chrome は約 5 秒)。activation 無しの試験を前の gesture に乗らせない
  const waitIdle = async () => { for (let t = 0; t < 120; t++) { if (!(await ev("navigator.userActivation.isActive"))) return; await new Promise((r) => setTimeout(r, 100)); } throw new Error("activation did not expire"); };
  const withoutActivation = async (expr) => { await waitIdle(); return ev(expr, false); };
  ck("実 Chrome の page で web build wasm を起動 (SharedArrayBuffer / pthread)", await ev("typeof SharedArrayBuffer === 'function' && crossOriginIsolated === true"), "crossOriginIsolated 偽");
  const ua = await ev("navigator.userAgent");
  const chromeVer = /Chrome\/(\S+)/.exec(ua)?.[1] ?? "?";
  console.log(`[browser] chrome=${chromeVer} ${ver?.Browser ?? ""}`);

  // ---- 1. ShellExecute → window.open ----
  const o1 = await ev(`window.__req(1, ["https://example.com/a?b=1"])`, true);
  ck("window.open: user activation 下の https は開く (result=1)", o1.result === 1, JSON.stringify(o1));
  const o2 = await withoutActivation(`window.__req(1, ["https://example.com/no-activation"])`);
  ck("window.open: user activation 無しは Chrome のポップアップブロックで失敗 (result=0 → ShellExecute 失敗)", o2.result === 0, JSON.stringify(o2));
  const o3 = await ev(`window.__req(1, ["javascript:alert(1)"])`, true);
  ck("window.open: javascript: は host 側で拒否 (result=0・window.open 未呼出)", o3.result === 0);

  // ---- 2. GetOpenFileNameW → showOpenFilePicker ----
  const f0 = await withoutActivation("window.__req(2, ['Open','', '', '', '', '', '', '', 'WAV (*.wav)', '*.wav'], 0)");
  ck("showOpenFilePicker: user activation 無しは実 API が SecurityError → 失敗 (result=-16 / HC_ERR)", f0.result === -16, JSON.stringify(f0));
  const f1 = await ev("window.__req(2, ['Open','', '', '', '/stage', 'C:\\\\s', '0', '0', 'WAV (*.wav)', '*.wav'], 0)", true);
  ck("showOpenFilePicker: activation 下で呼ばれ、選択結果が guest の応答 buffer に反映 (result=1, 'kick.wav')", f1.result === 1 && f1.out.startsWith("kick.wav"), JSON.stringify(f1));
  const ff = await ev("window.__fsRead('/stage/kick.wav')");
  ck("選択ファイルの内容がステージング FS へ書き出される ([1,2,3])", JSON.stringify(ff) === "[1,2,3]", JSON.stringify(ff));

  // ---- 3. GetSaveFileNameW → showSaveFilePicker ----
  await ev("window.__fsWrite('/stage/song.flp', [70,76,80])");
  const s0 = await withoutActivation("window.__req(3, ['Save','', 'flp', 'song.flp', '/stage', 'C:\\\\s', '0', '0', 'FL (*.flp)', '*.flp'], 0)");
  ck("showSaveFilePicker: user activation 無しは失敗 (result=-16)", s0.result === -16, JSON.stringify(s0));
  const s1 = await ev("window.__req(3, ['Save','', 'flp', 'song.flp', '/stage', 'C:\\\\s', '0', '0', 'FL (*.flp)', '*.flp'], 0)", true);
  ck("showSaveFilePicker: activation 下で呼ばれ、save 先 handle が返る (result=1, 'song.flp')", s1.result === 1 && s1.out.startsWith("song.flp"), JSON.stringify(s1));
  const nf = await ev("window.__flush()");
  const wr = await ev("window.__writes()");
  ck("save: FL が書いた内容が選択 handle (createWritable) へ反映される", nf === 1 && JSON.stringify(wr) === "[[70,76,80]]", JSON.stringify({ nf, wr }));

  const lg = await ev("window.__log()");
  // 想定内: activation 無しの window.open (blocked) / javascript: 拒否 (rejected) / activation 無しの open・save picker (user gesture 要求で失敗) の計 4 件
  const expected = [/^openUrl blocked: https:\/\/example\.com\/no-activation$/, /^openUrl rejected \(scheme javascript:\)$/, /^op 2 failed: .*Must be handling a user gesture/, /^op 3 failed: .*Must be handling a user gesture/];
  const unexpected = lg.filter((l) => !expected.some((re) => re.test(l)));
  ck("host log は想定内 (activation 無しの blocked/拒否 3 件) のみ", unexpected.length === 0 && lg.length === expected.length, JSON.stringify({ unexpected, n: lg.length }));
  ck("page 例外なし", logs.length === 0, logs.join(" | "));
  console.log(`[browser] calls=${JSON.stringify(await ev("window.__calls()"))}`);
  console.log(`[browser] log=${JSON.stringify(lg)}`);
} catch (e) {
  console.error("[browser] ERROR", e.message); fail = 2;
} finally {
  br.close(); srv.close(); clearTimeout(wd);
}
const bad = checks.filter(([, ok]) => !ok).length;
console.log(`BROWSER RESULT pass=${checks.length - bad} fail=${bad} chrome=${ver?.Browser ?? "?"}`);
process.exit(fail || bad ? 1 : 0);
