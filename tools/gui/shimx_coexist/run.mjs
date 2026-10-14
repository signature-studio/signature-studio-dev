// coexist.sh の node 側 host: wasm(PROXY_TO_PTHREAD) の main を走らせ、HostCallBridge で ShellExecute / ダイアログを受ける。
import { createRequire } from "node:module";
import assert from "node:assert/strict";
import { HostCallBridge, deliverDrop, installDropTarget } from "../../../src/runtime/gui_hostcall.ts";

const require = createRequire(import.meta.url);
const create = require(process.argv[2]);

const opened = [];
const dialogs = [];
let openN = 0;
const bytes = (a) => Uint8Array.from(a);
let mod;
const env = {
  fs: { mkdirp: (d) => { try { mod.FS.mkdirTree(d); } catch { /* 既存 */ } }, writeFile: (p, b) => mod.FS.writeFile(p, b), readFile: (p) => { try { return mod.FS.readFile(p); } catch { return null; } } },
  openWindow: (u) => { opened.push(u); return !u.includes("blocked"); },
  async pickOpen(o) {
    const n = openN++; dialogs.push({ kind: "open", n, ...o });
    if (n === 0) return [{ name: "kick.wav", bytes: bytes([1, 2, 3]) }];
    if (n === 1) return null;
    if (n === 2) return [{ name: "a.wav", bytes: bytes([10]) }, { name: "b.wav", bytes: bytes([11]) }, { name: "c.mid", bytes: bytes([12]) }];
    if (n === 3) return [{ name: "kick.wav", bytes: bytes([1, 2, 3]) }];
    throw new Error("simulated picker failure");
  },
  async pickSave(o) { dialogs.push({ kind: "save", ...o }); return { name: "song.flp", write: async (b) => { saved.push(Array.from(b)); } }; },
};
const saved = [];

let out = "";
mod = await create({
  print: (s) => { out += s + "\n"; console.log(s); },
  printErr: (s) => { if (/FAIL-FAST|\[gui\]/.test(s)) console.log("stderr:", s); },
  noExitRuntime: false,
  onExit: () => {},
});
const done = new Promise((res) => { mod.onExit = (c) => res(c); });
mod._gui_headless_attach(800, 600);
const bridge = new HostCallBridge(mod.wasmMemory, mod._gui_hostcall_ptr(), env);
if (process.env.COEXIST_NC !== "nohost") bridge.start();   // NC: host 無しなら C 側の dialog/ShellExecute テストが落ちること
const code = await Promise.race([done, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout 60s")), 60000))]).catch((e) => { console.log("HOST ERROR", e.message); return 99; });
await bridge.stop();

const m = /RESULT pass=(\d+) fail=(\d+)/.exec(out);
const checks = [];
const ck = (name, f) => { try { f(); checks.push([name, true]); } catch (e) { checks.push([name, false, e.message]); } };
ck("wasm 側 C テスト fail=0", () => { assert.ok(m, "RESULT 行無し"); assert.equal(m[2], "0"); });
ck("exit code 0", () => assert.equal(code, 0));
ck("window.open に渡った URL (C 側で拒否した 4 件は host に来ない)", () => assert.deepEqual(opened, ["https://example.com/a?b=1", "mailto:x@example.com", "http://example.com/old-style", "https://blocked.example/"]));
ck("open ダイアログ 5 回 + save 1 回", () => assert.equal(dialogs.length, 6));
ck("filter → types 変換 (WAV only; *.* は無制限)", () => assert.deepEqual(dialogs[0].types, [{ description: "WAV (*.wav)", accept: { "application/octet-stream": [".wav"] } }]));
ck("multi フラグ", () => assert.deepEqual(dialogs.filter((d) => d.kind === "open").map((d) => d.multiple), [false, false, true, false, false]));
ck("ステージング: kick.wav の内容", () => assert.deepEqual(Array.from(mod.FS.readFile(UTF() + "/kick.wav")), [1, 2, 3]));
ck("ステージング: multi 3 本", () => assert.deepEqual(["a.wav", "b.wav", "c.mid"].map((n) => Array.from(mod.FS.readFile(UTF() + "/" + n))), [[10], [11], [12]]));
ck("save: FL が閉じた save 先 (CloseHandle) の内容が実体 (mock handle) へ自動で反映 (flushSaves の手動呼出し無し)", () => { assert.deepEqual(saved, [Array.from(new TextEncoder().encode("FLP-DATA"))]); });
ck("host log に想定外エラー無し (想定: blocked 1 + picker failure 1)", () => assert.deepEqual(bridge.log.filter((l) => !/blocked|simulated/.test(l)), []));
function UTF() { const mm = /^STAGE (.*)$/m.exec(out); assert.ok(mm, "STAGE 行無し"); return mm[1]; }

// ---- drop の host 側 (ブラウザ DataTransfer → FS ステージング → gui_drop_files): wasm 終了後なので偽 module で検証 ----
{
  const heap = new Uint8Array(4096), calls = [], wrote = [];
  const fake = { _malloc: () => 16, _free: () => {}, HEAPU8: heap, UTF8ToString: () => "/stage", _gui_stage_dir_posix: () => 0,
    _gui_drop_files: (x, y, n, p) => { let e = p; while (!(heap[e] === 0 && heap[e + 1] === 0)) e++; calls.push([x, y, n, new TextDecoder().decode(heap.slice(p, e)).split("\0")]); return 1; } };
  const fs2 = { mkdirp() {}, writeFile: (p, b) => wrote.push([p, Array.from(b)]), readFile: () => null };
  const f = (name, bytes) => ({ name, arrayBuffer: async () => Uint8Array.from(bytes).buffer });
  const r = await deliverDrop(fake, fs2, [f("a.wav", [1]), f("../evil", [2]), f("b.mid", [3]), f("x/y", [4])], 110.4, 70.6);
  ck("deliverDrop: 不正名 (../ / パス区切り) を除外して 2 件を FS へ・gui_drop_files(110,71,2,...)", () => {
    assert.equal(r, 1); assert.deepEqual(wrote, [["/stage/a.wav", [1]], ["/stage/b.mid", [3]]]); assert.deepEqual(calls, [[110, 71, 2, ["a.wav", "b.mid"]]]);
  });
  const hs = {}; let res = null;
  const el = { addEventListener: (t, h) => { hs[t] = h; }, removeEventListener: (t) => { delete hs[t]; }, getBoundingClientRect: () => ({ left: 10, top: 20 }) };
  const off = installDropTarget(el, fake, fs2, (v) => { res = v; });
  let prevented = 0; const ev = { preventDefault: () => { prevented++; }, clientX: 120, clientY: 90, dataTransfer: { files: [f("c.wav", [9])] } };
  hs.dragover(ev); hs.drop(ev); await new Promise((r2) => setTimeout(r2, 20));
  ck("installDropTarget: dragover/drop を preventDefault し、canvas 座標 (110,70) で配送", () => { assert.equal(prevented, 2); assert.equal(res, 1); assert.deepEqual(calls.at(-1), [110, 70, 1, ["c.wav"]]); });
  off(); ck("installDropTarget: 解除で listener 除去", () => assert.deepEqual(Object.keys(hs), []));
}
let bad = 0;
for (const [n, ok, why] of checks) { console.log(`${ok ? "PASS" : "FAIL"} host: ${n}${ok ? "" : " — " + why}`); if (!ok) bad++; }
console.log(`HOST RESULT pass=${checks.length - bad} fail=${bad}`);
process.exit(bad || code ? 1 : 0);
