// HostCallBridge の openHelp op (#554): wasm 側を JS で模擬 (SharedArrayBuffer に req を書き resp_seq を待つ)。
//   node --test tools/startup/helpviewer/test/hostcall_help.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { HC, HC_OP, HC_MAGIC, HostCallBridge } from "../../../../src/runtime/gui_hostcall.ts";

function rig(env) {
  const sab = new SharedArrayBuffer(HC.size);
  const i32 = new Int32Array(sab), u8 = new Uint8Array(sab);
  const bridge = new HostCallBridge({ buffer: sab }, 0, env);
  Atomics.store(i32, HC.magic >> 2, HC_MAGIC);
  bridge.start();
  const call = async (op, text) => {
    const b = new TextEncoder().encode(text);
    u8.set(b, HC.in); Atomics.store(i32, HC.inLen >> 2, b.length); Atomics.store(i32, HC.op >> 2, op);
    const seq = Atomics.add(i32, HC.reqSeq >> 2, 1) + 1;
    Atomics.notify(i32, HC.reqSeq >> 2);
    for (let n = 0; n < 400 && Atomics.load(i32, HC.respSeq >> 2) !== seq; n++) await new Promise((r) => setTimeout(r, 5));
    assert.equal(Atomics.load(i32, HC.respSeq >> 2), seq, "host が応答しない");
    return Atomics.load(i32, HC.result >> 2);
  };
  return { bridge, call };
}
const ROOT = "C:\\Program Files\\Image-Line\\FL Studio 2026";

test("op openHelp: env.openHelp にパスが渡り、true → result 1 / false → 0", async () => {
  const seen = [];
  const { bridge, call } = rig({ openWindow: () => true, openHelp: async (p) => { seen.push(p); return !p.includes("reject"); }, fs: {} });
  try {
    assert.equal(await call(HC_OP.openHelp, `${ROOT}\\Help\\index_offline.html`), 1);
    assert.equal(await call(HC_OP.openHelp, `${ROOT}\\Help\\reject.html`), 0);
    assert.deepEqual(seen, [`${ROOT}\\Help\\index_offline.html`, `${ROOT}\\Help\\reject.html`]);
    assert.ok(bridge.log.some((l) => l.startsWith("openHelp rejected")));
  } finally { await bridge.stop(); }
});

test("op openHelp: viewer 未接続 (openHelp 無し) は 0 + log / 例外は HC_ERR", async () => {
  const a = rig({ openWindow: () => true, fs: {} });
  try { assert.equal(await a.call(HC_OP.openHelp, `${ROOT}\\Help\\x.html`), 0); assert.ok(a.bridge.log.includes("openHelp: no viewer")); } finally { await a.bridge.stop(); }
  const b = rig({ openWindow: () => true, openHelp: async () => { throw new Error("boom"); }, fs: {} });
  try { assert.equal(await b.call(HC_OP.openHelp, `${ROOT}\\Help\\x.html`), -16); } finally { await b.bridge.stop(); }
});

test("op openUrl は従来どおり (回帰)", async () => {
  const opened = [];
  const { bridge, call } = rig({ openWindow: (u) => { opened.push(u); return true; }, openHelp: async () => assert.fail("openUrl で openHelp が呼ばれた"), fs: {} });
  try { assert.equal(await call(HC_OP.openUrl, "https://example.com/a"), 1); assert.deepEqual(opened, ["https://example.com/a"]); } finally { await bridge.stop(); }
});
