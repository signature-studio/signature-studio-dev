// browser_page.js — 実ブラウザで shimx×gui の web 版 wasm を走らせ、browserEnv (window.open / File System Access) を検査する (#956 / #1159)。
// user activation が要る host 呼出 (window.open / picker) は、ボタン (#gate) を CDP の実マウス入力で押させてから実行する。
// picker は headless で native ダイアログを出せないため showOpenFilePicker / showSaveFilePicker だけ差し替える (browserEnv 本体の経路は通る)。
// window.open は実 API を呼ぶが遷移先は about:blank (外部ネットワーク非依存)。popup ブロックは URL に "blocked" を含むときだけ null を返して模擬する。
import { HostCallBridge, browserEnv } from "./hostcall.js";

const report = { out: [], code: null, error: null, gates: [], opened: [], opens: [], saves: [], saved: [], flushed: null, stage: {}, log: [] };
const print = (s) => report.out.push(s);
const btn = document.getElementById("gate");
let gateSeq = 0;
function gate(label, fn) {
  return new Promise((resolve, reject) => {
    btn.textContent = label; btn.style.display = "block"; window.__gate = { label, seq: ++gateSeq };
    btn.onclick = async () => {
      btn.style.display = "none"; window.__gate = null;
      report.gates.push({ label, active: navigator.userActivation.isActive });
      try { resolve(await fn()); } catch (e) { reject(e); }
    };
  });
}

const realOpen = window.open.bind(window);
window.open = (url, target, features) => {
  report.opened.push({ url: String(url), active: navigator.userActivation.isActive });
  if (String(url).includes("blocked")) return null;
  return realOpen("about:blank", target, features);
};

const fh = (name, bytes) => ({ kind: "file", name, getFile: async () => new File([Uint8Array.from(bytes)], name) });
let openN = 0;
window.showOpenFilePicker = async (opts) => {
  const n = openN++;
  report.opens.push({ n, active: navigator.userActivation.isActive, multiple: !!opts.multiple, types: opts.types ?? null });
  if (n === 0) return [fh("kick.wav", [1, 2, 3])];
  if (n === 1) throw new DOMException("user cancelled", "AbortError");
  if (n === 2) return [fh("a.wav", [10]), fh("b.wav", [11]), fh("c.mid", [12])];
  if (n === 3) return [fh("kick.wav", [1, 2, 3])];
  throw new Error("simulated picker failure");
};
window.showSaveFilePicker = async (opts) => {
  report.saves.push({ active: navigator.userActivation.isActive, types: opts.types ?? null, suggestedName: opts.suggestedName ?? null });
  return { kind: "file", name: "song.flp", createWritable: async () => ({ write: async (b) => { report.saved.push(Array.from(b)); }, close: async () => {} }) };
};

async function main() {
  const mod = await window.coexist({ print, printErr: (s) => { if (/FAIL-FAST|\[gui\]/.test(s)) report.out.push("stderr: " + s); }, noExitRuntime: false, onExit: () => {} });
  let exitRes; const exited = new Promise((r) => { exitRes = r; });
  mod.onExit = (c) => exitRes(c);
  const fsWrap = {
    mkdirp: (d) => { try { mod.FS.mkdirTree(d); } catch { /* 既存 */ } },
    writeFile: (p, b) => mod.FS.writeFile(p, b),
    readFile: (p) => { try { return mod.FS.readFile(p); } catch { return null; } },
  };
  const base = browserEnv(window, fsWrap);
  const env = {
    fs: fsWrap,
    openWindow: (u) => gate(`window.open ${u.slice(0, 40)}`, async () => base.openWindow(u)),
    pickOpen: (o) => gate("open picker", () => base.pickOpen(o)),
    pickSave: (o) => gate("save picker", () => base.pickSave(o)),
  };
  mod._gui_headless_attach(800, 600);
  const bridge = new HostCallBridge(mod.wasmMemory, mod._gui_hostcall_ptr(), env);
  bridge.start();
  report.code = await Promise.race([exited, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout 90s")), 90000))]).catch((e) => { report.error = e.message; return 99; });
  report.flushed = await bridge.flushSaves();
  await bridge.stop();
  report.log = bridge.log;
  const m = /^STAGE (.*)$/m.exec(report.out.join("\n"));
  if (m) {
    report.stage.dir = m[1];
    for (const n of ["kick.wav", "a.wav", "b.wav", "c.mid"]) { try { report.stage[n] = Array.from(mod.FS.readFile(`${m[1]}/${n}`)); } catch { report.stage[n] = null; } }
  }
  window.__report = report;
}
main().catch((e) => { report.error = String((e && e.stack) || e); window.__report = report; });
