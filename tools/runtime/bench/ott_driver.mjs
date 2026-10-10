// OTT t1 (M10 e2e_check 相当) の最小ドライバ。wasm32 / wasm64 両ビルドを同一手順で駆動し出力 bit ハッシュを返す。
import { makeImports } from "../lib/emenv.mjs";
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = 256;

export async function loadOtt(bytesOrModule) {
  const module = bytesOrModule instanceof WebAssembly.Module ? bytesOrModule : await WebAssembly.compile(bytesOrModule);
  let memory = null;
  const { imports, missing } = makeImports(module, { getMemory: () => memory });
  const inst = await WebAssembly.instantiate(module, imports);
  const e = inst.exports;
  memory = e.memory;
  e.emscripten_stack_init?.();
  e.__wasm_call_ctors();
  e.m6_data_install();
  const is64 = memory.buffer.byteLength >= 0 && (WebAssembly.Memory.prototype.type ? memory.type().address === "i64" : false);
  return { e, memory, missing, is64 };
}

export function makeRunner({ e, memory }) {
  const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
  const view = () => ({ U8: new Uint8Array(memory.buffer), U32: new Uint32Array(memory.buffer), F32: new Float32Array(memory.buffer), dv: new DataView(memory.buffer) });
  function setup(val) {
    const { U8, U32, F32 } = view();
    e.function_18011d400(BigInt(OBJ), 0n);
    for (let i = 0; i < 20; i++) e.function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val));
    e.function_180120800(BigInt(OBJ));
    U8[OBJ + 0x248] = 0;
    for (let i = 0; i < N; i++) {
      F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
      F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
    }
    U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
    U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
  }
  const process = () => e.function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  function hash() { // FNV-1a over 512 output f32 bit patterns
    const { dv } = view(); let h = 0x811c9dc5;
    for (let i = 0; i < N * 2; i++) { h ^= dv.getUint32(BUF + N * 8 + i * 4, true); h = Math.imul(h, 0x01000193) >>> 0; }
    return h >>> 0;
  }
  return { setup, process, hash };
}
