// MIDI shim テストページ: モック MIDIAccess (または ?real=1 で実 Web MIDI) + FlMidiShim を起動し、wasm (flmidi_test) とフェーズ同期で進める。
import { FlMidiShim } from "./js/midi-shim.js";

const q = new URLSearchParams(location.search);
const corrupt = q.get("corrupt") ?? "";          // ネガティブコントロール: drop500 | sysexflip | noprepare
const logEl = document.getElementById("log");
const log = (s) => { logEl.textContent += s + "\n"; console.log(s); };

class MockIn { constructor(id, name) { this.id = id; this.name = name; this.state = "connected"; this.onmidimessage = null; this.opened = 0; this.delivered = 0; this.noHandler = 0; }
  async open() { this.opened++; }
  emit(data) { if (this.onmidimessage) { this.delivered++; this.onmidimessage({ data: Uint8Array.from(data), timeStamp: performance.now() }); } else this.noHandler++; } }
class MockOut { constructor(id, name) { this.id = id; this.name = name; this.state = "connected"; this.sent = []; }
  async open() {} send(d) { this.sent.push(Array.from(d)); } }
const kb = new MockIn("in-kb", "Mock Keyboard");
const longn = new MockIn("in-long", "A Very Long MIDI Device Name Exceeding 31 Chars");
const syn = new MockOut("out-syn", "Mock Synth"), drum = new MockOut("out-drum", "Mock Drum");
const access = { inputs: new Map([[kb.id, kb], [longn.id, longn]]), outputs: new Map([[syn.id, syn], [drum.id, drum]]), onstatechange: null };
const hot = new MockIn("in-hot", "Hotplugged Pad");

const short = (n) => [0x90 | (n & 15), n & 0x7f, (n >> 7) & 0x7f];
const sysex = (len) => { const a = new Uint8Array(len); a[0] = 0xf0; for (let i = 1; i + 1 < len; i++) a[i] = (i * 7 + 3) & 0x7f; a[len - 1] = 0xf7; return a; };
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

window.__done = new Promise((resolveAll, rejectAll) => {
  const stderr = [];
  window.Module = {
    onAbort: (w) => setTimeout(() => resolveAll({ aborted: true, what: String(w), stderr }), 200),
    print: (t) => log("[wasm] " + t),
    printErr: (t) => { stderr.push(String(t)); log("[wasm!] " + t); if (String(t).includes("FAIL-FAST")) setTimeout(() => resolveAll({ aborted: true, what: "fail-fast", stderr }), 500); },
    onRuntimeInitialized: () => {
      const M = window.Module;
      const api = { init: () => M._flm_init(), getBuffer: () => M.wasmMemory.buffer, ctlPtr: () => M._flm_ctl_ptr(), layoutCount: () => M._flm_layout_count(), layoutOff: (i) => M._flm_layout_off(i), layoutName: (i) => M.UTF8ToString(M._flm_layout_name(i)) };
      const shim = new FlMidiShim(api, access, { log, keepSendLog: true });
      window.__shim = shim;
      shim.attach();
      const phase = () => new Int32Array(M.wasmMemory.buffer, M._fla_midi_test_phase_ptr(), 1);
      const go = () => new Int32Array(M.wasmMemory.buffer, M._fla_midi_test_go_ptr(), 1);
      const done = () => new Int32Array(M.wasmMemory.buffer, M._fla_midi_test_done_ptr(), 1);
      const jsInfo = { phases: [] };
      const inSlot = () => [...shim.inSlots.entries()][0];
      let closedSlot = null;
      const doPhase = async (n) => {
        jsInfo.phases.push(n);
        switch (n) {
          case 1: for (let i = 0; i < 10; i++) kb.emit(short(i)); break;
          case 2: for (let i = 0; i < 1000; i++) { if (corrupt === "drop500" && i === 500) continue; kb.emit(short(i)); if (i % 50 === 49) await sleep(1); } break;
          case 3: kb.emit(sysex(300)); { const s = sysex(1000); if (corrupt === "sysexflip") s[500] ^= 1; kb.emit(s); } break;
          case 4: for (let i = 0; i < 3; i++) { kb.emit(sysex(100)); await sleep(50); } break;
          case 5: for (let i = 0; i < 5; i++) kb.emit(short(i)); break;
          case 6: { closedSlot = inSlot(); for (let i = 0; i < 5000; i++) kb.emit(short(i)); break; }
          case 7: { jsInfo.handlerAfterClose = kb.onmidimessage === null; const before = kb.noHandler; for (let i = 0; i < 3; i++) kb.emit(short(i)); jsInfo.noHandlerEmits = kb.noHandler - before;
            if (closedSlot) for (let i = 0; i < 3; i++) shim.injectForTest(closedSlot[0], closedSlot[1].gen, Uint8Array.from(short(i))); break; }
          case 8: shim.outPaused = true; break;
          case 9: shim.outPaused = false; break;
          case 10: access.inputs.set(hot.id, hot); access.onstatechange?.({}); break;
          case 11: access.inputs.delete(hot.id); break;
        }
      };
      (async () => {
        const deadline = performance.now() + 90000;
        let served = 0;
        for (;;) {
          if (Atomics.load(done(), 0) !== 0) break;
          if (performance.now() > deadline) { rejectAll(new Error("test timeout")); return; }
          const p = Atomics.load(phase(), 0);
          if (p > served) {
            served = p; await doPhase(p);
            if (corrupt === "noprepare" && p === 3) { /* 予約 */ }
            Atomics.store(go(), 0, p); Atomics.notify(go(), 0);
          } else { const r = Atomics.waitAsync(phase(), 0, p, 50); if (r.async) await r.value; }
        }
        const text = M.UTF8ToString(M._fla_midi_test_result_ptr());
        let result; try { result = JSON.parse(text); } catch { rejectAll(new Error("bad result json: " + text)); return; }
        result.js = { ...jsInfo, outSent: { syn: syn.sent.length, drum: drum.sent.length }, synFirst: syn.sent.slice(0, 3), synShortOk: syn.sent.slice(0, 100).every((m, n) => m.length === 3 && m[0] === (0x90 | (n & 15)) && m[1] === (n & 0x7f) && m[2] === ((n >> 7) & 0x7f)),
          synSysex: syn.sent.slice(100).map((m) => ({ len: m.length, ok: m[0] === 0xf0 && m[m.length - 1] === 0xf7 && m.every((b, i) => i === 0 || i === m.length - 1 || b === ((i * 7 + 3) & 0x7f)) })), commands: shim.commandsHandled, kbOpened: kb.opened };
        result.snapshot = { in_dropped: Atomics.load(new Int32Array(M.wasmMemory.buffer), (M._flm_ctl_ptr() + 68) >> 2) };
        resolveAll(result);
      })();
    },
  };
  const s = document.createElement("script"); s.src = "flmidi_test.js"; document.body.appendChild(s);
});
