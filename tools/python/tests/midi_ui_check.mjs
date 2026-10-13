// PY-6 (#76) e2e: アプリ (Vite dev server, COOP/COEP) を headless Chrome で開き、device script → Web MIDI → callback 配送を UI / devtools から実行する。
//   node tools/python/tests/midi_ui_check.mjs [--neg]    -> "MIDI UI OK {...}" exit 0 / FAIL exit 2 / --neg: "NEG-CONTROL DETECTED" exit 1
// 前提: tools/python/dist/ (build_flpy.sh)。FL 由来ファイルは不要 (tests/fixtures/ の合成 device script を device_*.py の名前でコピーして供給)。
// 検証: (1) 供給前は loadDeviceScript が reject (非同梱) (2) /py/ は host/*.mjs と dist/ だけ 200、fixtures / work / src は 404
//       (3) UI: ファイル選択 → 起動 + 読込 + OnInit → 2 script (4) 偽 MIDIAccess (入力 2 つ) → connectWebMidi → 連投が到着順・port 別に配送
//       (5) 実 Chrome の navigator.requestMIDIAccess に connectWebMidi (この runner には MIDI デバイスが無いので入力 0 件で解決するかを観測)
//   --neg: 構文エラーを足した device script を供給 → 起動が失敗し、「2 script 読込」の判定が FAIL して原因 (SyntaxError) が UI に出る
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { createServer } from "vite";
import { launchChrome } from "../../runtime/lib/chrome.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const neg = process.argv.includes("--neg");
const checks = {};
const check = (name, cond, extra) => { checks[name] = !!cond; if (!cond) console.error(`FAIL ${name}`, extra === undefined ? "" : JSON.stringify(extra)); };
const KEY = "UI: 2 device script を読込み・OnInit 済み";

const tmp = mkdtempSync(path.join(tmpdir(), "midi-ui-"));
const fixture = (n) => readFileSync(path.join(here, "fixtures", n), "utf8");
const files = [
  ["device_rec.py", fixture("device_recorder.py") + (neg ? "\ndef (:\n" : "")],
  ["device_fwd.py", fixture("device_forward_cc.py")],
].map(([n, src]) => { const p = path.join(tmp, n); writeFileSync(p, src); return p; });

const t0 = Date.now();
const vite = await createServer({ root, logLevel: "warn", server: { port: 0, host: "127.0.0.1", strictPort: false } });
await vite.listen();
const base = `http://127.0.0.1:${vite.config.server.port ?? vite.httpServer.address().port}`;
const chrome = await launchChrome();
let out = { ok: false };
try {
  const page = await chrome.newPage();
  await page.send("Browser.grantPermissions", { permissions: ["midi", "midiSysex"], origin: base }).catch(() => {});
  await page.goto(`${base}/?midi=1`);
  check("crossOriginIsolated", await page.evaluate("crossOriginIsolated"));
  check("flMidi exposed", await page.evaluate("typeof window.flMidi?.midiIn === 'function'"));

  const pre = await page.evaluate(`window.flMidi.loadDeviceScript("x", "def OnInit(): pass").then(() => "loaded", (e) => String(e))`);
  check("start 前の loadDeviceScript は reject", /start\(\) が未実行/.test(pre), pre);
  const status = await page.evaluate(`Promise.all(["/py/host/midi_host.mjs", "/py/dist/flpy.wasm", "/py/tests/fixtures/device_recorder.py", "/py/work/midi.py", "/py/src/fl_rt.py"].map((u) => fetch(u).then((r) => r.status)))`);
  check("配信: host/midi_host.mjs と dist/flpy.wasm は 200、fixtures / work / src は 404", JSON.stringify(status) === "[200,200,404,404,404]", status);

  const { root: docRoot } = await page.send("DOM.getDocument", {});
  const { nodeId } = await page.send("DOM.querySelector", { nodeId: docRoot.nodeId, selector: "#midi-files" });
  await page.send("DOM.setFileInputFiles", { nodeId, files });
  await page.waitForExpr(`document.getElementById("midi-start") && !document.getElementById("midi-start").disabled`, 10000);
  check("UI: device script 供給後に起動ボタンが有効", true);
  await page.evaluate(`document.getElementById("midi-port").value = "0"; document.getElementById("midi-start").click()`);
  let stateText = "";
  try {
    stateText = await page.waitForExpr(`/起動済み: |失敗: /.test(document.getElementById("midi-state").textContent) && document.getElementById("midi-state").textContent`, 60000);
  } catch (e) { stateText = String(e); }
  const loaded = /起動済み: .*device_rec.*device_fwd|起動済み: .*device_fwd.*device_rec/.test(stateText);
  check(KEY, loaded && (await page.evaluate(`window.flMidi.output.some((l) => /fixture forward-cc init, port 0/.test(l))`)), stateText);
  if (neg) check("neg: 構文エラーは「失敗:」として UI に出る (ハングしない)", /^失敗:[\s\S]*SyntaxError/.test(stateText), stateText);
  if (loaded) {
    const scripts = await page.evaluate(`window.flMidi.scripts()`);
    check("UI: 全 script が port=0 で登録・rec は 27 callback", scripts.device_rec?.port === 0 && scripts.device_rec.callbacks.length === 27 && scripts.device_fwd?.port === 0, scripts);

    // 偽 MIDIAccess (入力 2 つ + 後から接続 1 つ)。ブラウザの Web MIDI 実体ではなく、結線コード (listener / port 採番 / 到着順) の検証
    const fake = await page.evaluate(`(async () => {
      const mk = (id, name) => ({ id, name, type: "input", state: "connected", onmidimessage: null, send(b) { this.onmidimessage?.({ data: Uint8Array.from(b), timeStamp: 2.5 }); } });
      const A = mk("A", "Keys"), B = mk("B", "Pads"), C = mk("C", "Late");
      const access = { inputs: new Map([["A", A], ["B", B]]), onstatechange: null };
      const r = await window.flMidi.connectWebMidi({ access, portMap: { Pads: 3 } });
      window.flMidi.deliveries.length = 0;
      for (let i = 0; i < 60; i++) A.send([0x90, i, 100]);
      B.send([0xb0, 74, 99]);
      access.inputs.set("C", C); access.onstatechange({ port: C }); C.send([0xc0, 5]);
      await window.flMidi.scripts(); // 直列キューの最後尾
      const d = window.flMidi.deliveries.map((x) => ({ s: x.fields.status, d1: x.fields.data1, p: x.fields.port, scripts: x.result.results.map((y) => y.script + ":" + y.called.join("/")) }));
      window.flMidi.disconnectWebMidi();
      return { inputs: r.inputs, handlersCleared: A.onmidimessage === null && B.onmidimessage === null && C.onmidimessage === null && access.onstatechange === null, d };
    })()`);
    const notes = fake.d.filter((x) => x.s === 0x90);
    const cc = fake.d.find((x) => x.s === 0xb0), pc = fake.d.find((x) => x.s === 0xc0);
    check("Web MIDI(偽): 入力名を返す・60 件連投が到着順に port 0 の rec へ OnMidiIn/OnMidiMsg/OnNoteOn", fake.inputs.join() === "Keys,Pads" && notes.length === 60 && notes.every((x, i) => x.d1 === i && x.p === 0 && x.scripts.join() === "device_rec:OnMidiIn/OnMidiMsg/OnNoteOn,device_fwd:OnMidiIn/OnMidiMsg"), { n: notes.length, first: notes[0] });
    check("Web MIDI(偽): portMap{Pads:3} の CC は port 3 → port 0 の script は受けない (配送 0 script)", cc?.p === 3 && cc.scripts.length === 0, cc);
    check("Web MIDI(偽): 接続後に増えた入力は連番 port 1 → 配送 0 script (port 0 のみ登録のため)", pc?.p === 1 && pc.scripts.length === 0, pc);
    check("Web MIDI(偽): disconnect で全リスナ解除", fake.handlersCleared);

    // port=0 の CC は fwd が device.forwardMIDICC へ (合成 fixture) — devtools から注入
    const inj = await page.evaluate(`window.flMidi.midiIn([0xb0, 74, 99], { port: 0 })`);
    const fwd = inj.results.find((r) => r.script === "device_fwd");
    check("devtools: midiIn(CC, port 0) → fwd の OnMidiIn → OnMidiMsg (handled で型別 OnControlChange へは進まない)", fwd.called.join() === "OnMidiIn,OnMidiMsg" && fwd.errors.length === 0 && inj.results.find((r) => r.script === "device_rec").called.join() === "OnMidiIn,OnMidiMsg,OnControlChange", inj.results);
    const cb = await page.evaluate(`window.flMidi.callback("OnRefresh", [4]).then((r) => r.results.map((x) => x.script + ":" + x.called.join("/")).join(","), (e) => String(e))`);
    check("devtools: 非 MIDI callback (OnRefresh) を全 script へ配送", cb === "device_rec:OnRefresh,device_fwd:", cb);

    // 実 Chrome の Web MIDI (この runner には MIDI デバイスなし)。結線コードが本物の MIDIAccess でも例外なく付く/外れることを観測
    const real = await page.evaluate(`(async () => {
      try {
        const r = await Promise.race([window.flMidi.connectWebMidi({ sysex: true }), new Promise((_, rej) => setTimeout(() => rej(new Error("requestMIDIAccess timeout 10s")), 10000))]);
        window.flMidi.disconnectWebMidi();
        return { settled: "resolved", inputs: r.inputs.length };
      } catch (e) { return { settled: "rejected", error: String(e).slice(0, 200) }; }
    })()`);
    out.realWebMidi = real;
    check("実 Chrome の requestMIDIAccess: connectWebMidi が解決 or 理由付き reject で完了 (ハングしない)", real.settled === "resolved" || /\S/.test(real.error ?? ""), real);
    out.deliveries = { notes: notes.length, ccPort: cc?.p, pcPort: pc?.p };
  }
  out.state = stateText;
  out.exceptions = page.exceptions.slice(0, 3);
} finally {
  await chrome.close();
  await vite.close();
  rmSync(tmp, { recursive: true, force: true });
}
// --neg の期待: 主判定 (KEY) が FAIL し、原因が SyntaxError として UI に出る。終了コード: PASS=0 / FAIL=2 / --neg で検出できたとき 1
const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
const ok = Object.keys(checks).length > 0 && (neg ? failed.length === 1 && failed[0] === KEY : failed.length === 0);
out = { ...out, ok, checks: Object.keys(checks).length, failed, seconds: (Date.now() - t0) / 1000, neg };
console.log((ok ? (neg ? "MIDI UI NEG-CONTROL DETECTED " : "MIDI UI OK ") : "MIDI UI FAIL ") + JSON.stringify(out));
process.exit(ok ? (neg ? 1 : 0) : 2);
