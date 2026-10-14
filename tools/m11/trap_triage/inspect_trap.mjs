// #1602: build を変えずに trap 時点の wasm local を読む (V8 inspector の pause on exception)。
// 使い方: node --wasm-enforce-bounds-checks --import ./tools/m11/trap_triage/inspect_trap.mjs tools/m11/m11_survey.mjs
//   --wasm-enforce-bounds-checks が要る: 既定 (trap handler) だと OOB 時の frame に local の side table が無く、local が空で返る。
// 環境変数: M11_INSPECT_OUT=<path> (JSONL の出力先。既定 stderr) / M11_INSPECT_FN=<idx,..> (記録する先頭 wasm 関数 index。既定は全部)
//   M11_INSPECT_PEEK=<json> 関数 index ごとに guest メモリの u64 を追う。{"3372":[["$var0",8,8]]} は local $var0 から
//     addr1=local+8, v1=*addr1, addr2=v1+8, v2=*addr2 を順に読む。addr は i32 に wrap し、範囲外なら 'oor'
//   M11_INSPECT_DUMP=<addr>:<len>[,<addr>:<len>..] peek を持つ関数の trap 時点で、guest メモリのこの範囲を hex で添える (addr は 0x 可)
//   M11_INSPECT_FRAMES=<n> peek を持つ関数の trap で、呼出し元 n フレームの local (0 以外のみ) も添える
// trap 時の例外 (RuntimeError) だけを記録し、すぐ resume する。wasm 側の build・実行内容は変えない。
import inspector from 'node:inspector';
import fs from 'node:fs';

const out = process.env.M11_INSPECT_OUT;
const only = process.env.M11_INSPECT_FN ? new Set(process.env.M11_INSPECT_FN.split(',')) : null;
const peek = process.env.M11_INSPECT_PEEK ? JSON.parse(process.env.M11_INSPECT_PEEK) : {};
const emit = (o) => { const s = JSON.stringify(o) + '\n'; if (out) fs.appendFileSync(out, s); else process.stderr.write('[inspect] ' + s); };
if (out) fs.writeFileSync(out, '');

let mem = null;
const origInst = WebAssembly.instantiate;
WebAssembly.instantiate = async function (...a) {
  const r = await origInst.apply(this, a);
  const inst = r.instance ?? r;
  for (const v of Object.values(inst.exports)) if (v instanceof WebAssembly.Memory) mem = v;
  return r;
};

const session = new inspector.Session();
session.connect();
const post = (m, p) => { let res, err; session.post(m, p, (e, r) => { err = e; res = r; }); if (err) throw new Error(m + ': ' + JSON.stringify(err)); return res; };
post('Debugger.enable');
post('Debugger.setPauseOnExceptions', { state: 'all' });

const props = (objectId) => post('Runtime.getProperties', { objectId, ownProperties: true }).result;
const wasmValue = (v) => {
  if (!v) return null;
  if (v.subtype !== 'wasmvalue' || !v.objectId) return v.value ?? v.description ?? null;
  const o = {};
  for (const q of props(v.objectId)) o[q.name] = q.value?.value ?? q.value?.unserializableValue ?? q.value?.description;
  return o.type + ':' + o.value;
};

let seq = 0;
session.on('Debugger.paused', (ev) => {
  const p = ev.params;
  try {
    const top = p.callFrames[0];
    const exc = p.data;
    const desc = String(exc?.description || '');
    const m = /^RuntimeError: ([^\n]*)\n\s+at wasm:\/\/wasm\/[0-9a-f]+:wasm-function\[(\d+)\]:0x([0-9a-f]+)/.exec(desc);
    if (p.reason !== 'exception' || !top || !m) return;
    const rec = { seq: seq++, msg: m[1], fnIdx: Number(m[2]), off: '0x' + m[3], frame: top.functionName, frameOff: top.location.columnNumber, locals: null };
    if (only && !only.has(String(rec.fnIdx))) { rec.skipped = true; emit(rec); return; }
    const frameLocals = (f, nonzero) => {
      let r = null;
      for (const sc of f.scopeChain) {
        if (sc.type !== 'local' || !sc.object?.objectId) continue;
        r = {};
        for (const q of props(sc.object.objectId)) { const v = wasmValue(q.value); if (!nonzero || !/^i(32|64):0n?$/.test(String(v))) r[q.name] = v; }
      }
      return r;
    };
    rec.locals = frameLocals(top, false);
    const nfr = Number(process.env.M11_INSPECT_FRAMES || 0);
    if (nfr && peek[rec.fnIdx]) rec.callers = p.callFrames.slice(1, 1 + nfr).map((f) => ({ frame: f.functionName, off: f.location.columnNumber, nonzero_locals: frameLocals(f, true) }));
    rec.mem_bytes = mem ? mem.buffer.byteLength : null;
    if (peek[rec.fnIdx] && rec.locals && mem) {
      if (process.env.M11_INSPECT_DUMP) {
        rec.dump = process.env.M11_INSPECT_DUMP.split(',').map((r) => {
          const [da, dl] = r.split(':').map(Number);
          return { addr: '0x' + da.toString(16), hex: da + dl <= mem.buffer.byteLength ? Buffer.from(new Uint8Array(mem.buffer, da, dl)).toString('hex') : 'oor' };
        });
      }
      const dv = new DataView(mem.buffer), size = mem.buffer.byteLength;
      rec.peek = peek[rec.fnIdx].map(([local, ...offs]) => {
        const lv = String(rec.locals[local] ?? '').split(':')[1] ?? '0';
        let v = BigInt(lv.replace(/n$/, ''));
        const steps = [{ local, value: '0x' + BigInt.asUintN(64, v).toString(16) }];
        for (const off of offs) {
          const addr = Number(BigInt.asUintN(32, v + BigInt(off)));
          if (addr + 8 > size) { steps.push({ addr: '0x' + addr.toString(16), v: 'oor' }); break; }
          v = dv.getBigUint64(addr, true);
          steps.push({ addr: '0x' + addr.toString(16), v: '0x' + v.toString(16) });
        }
        return steps;
      });
    }
    emit(rec);
  } catch (e) {
    emit({ error: String((e && e.stack) || e) });
  } finally {
    session.post('Debugger.resume');
  }
});
