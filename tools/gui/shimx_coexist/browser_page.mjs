// browser_page.mjs — 実ブラウザ page 側 (SHX-T19 #1159)。web 版 wasm の shared memory 上の hostcall 要求を、
// 本物の window.open / File System Access 呼出経路 (browserEnv) で処理させる。
// 差し替えは picker の UI だけ: activation 下の呼出は headless で操作できない native picker の代わりに mock handle を返す。
// activation 無しの呼出は実 API へ流し、Chrome の拒否 (SecurityError) を見る。
import { HostCallBridge, browserEnv, HC, HC_IN } from "/js/gui_hostcall.js";

const calls = [];
const writes = [];
const act = () => navigator.userActivation.isActive;
const KICK = new Uint8Array([1, 2, 3]);
const realOpen = window.showOpenFilePicker.bind(window);
const realSave = window.showSaveFilePicker.bind(window);
window.showOpenFilePicker = async (o) => {
  calls.push({ api: "open", active: act(), multiple: !!o.multiple });
  if (!act()) return realOpen(o);
  return [{ name: "kick.wav", getFile: async () => new File([KICK], "kick.wav") }];
};
window.showSaveFilePicker = async (o) => {
  calls.push({ api: "save", active: act() });
  if (!act()) return realSave(o);
  return { name: "song.flp", createWritable: async () => ({ write: async (b) => { writes.push(Array.from(b)); }, close: async () => {} }) };
};

let mod, bridge, base;
const fsOf = () => ({
  mkdirp: (d) => { try { mod.FS.mkdirTree(d); } catch { /* 既存 */ } },
  writeFile: (p, b) => mod.FS.writeFile(p, b),
  readFile: (p) => { try { return mod.FS.readFile(p); } catch { return null; } },
});

window.__init = async () => {
  mod = await window.coexistWeb({});
  base = mod._gui_hostcall_ptr();
  bridge = new HostCallBridge(mod.wasmMemory, base, browserEnv(window, fsOf()));
  bridge.start();
  return true;
};
// wasm 側 (gui_hostcall.h) と同じ手順で要求を書き、respSeq を待つ
window.__req = async (op, fields, flags = 0) => {
  const i = new Int32Array(mod.wasmMemory.buffer, base, HC.size >> 2);
  const b = new Uint8Array(mod.wasmMemory.buffer, base, HC.size);
  const bytes = new TextEncoder().encode(fields.join("\0") + "\0").subarray(0, HC_IN);
  b.set(bytes, HC.in);
  Atomics.store(i, HC.op >> 2, op);
  Atomics.store(i, HC.flags >> 2, flags);
  Atomics.store(i, HC.inLen >> 2, bytes.length);
  const seq = Atomics.add(i, HC.reqSeq >> 2, 1) + 1;
  Atomics.notify(i, HC.reqSeq >> 2);
  for (;;) {
    const cur = Atomics.load(i, HC.respSeq >> 2);
    if (cur === seq) break;
    const w = Atomics.waitAsync(i, HC.respSeq >> 2, cur, 1000);
    if (w.async) await w.value;
  }
  const n = Atomics.load(i, HC.outLen >> 2);
  return { result: Atomics.load(i, HC.result >> 2), out: new TextDecoder().decode(b.slice(HC.out, HC.out + n)) };
};
window.__calls = () => calls;
window.__writes = () => writes;
window.__log = () => bridge.log;
window.__flush = () => bridge.flushSaves();
window.__fsRead = (p) => { try { return Array.from(mod.FS.readFile(p)); } catch { return null; } };
window.__fsWrite = (p, arr) => mod.FS.writeFile(p, Uint8Array.from(arr));
