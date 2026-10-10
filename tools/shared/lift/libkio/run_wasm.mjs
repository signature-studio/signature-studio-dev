// lift 済み wasm (kio.wasm) を node で実行して cases.json の各ケースの戻り値/書込バッファを res_wasm.json へ出力
import { readFileSync, writeFileSync } from "node:fs";
const W = process.argv[2];
const { sig, cases } = JSON.parse(readFileSync(`${W}/cases.json`, "utf8"));
const wasm = readFileSync(`${W}/kio.wasm`);
const mod = await WebAssembly.compile(wasm);
const imports = {};
for (const i of WebAssembly.Module.imports(mod)) { imports[i.module] ??= {}; if (i.kind === "function") imports[i.module][i.name] = () => 0; }
const inst = await WebAssembly.instantiate(mod, imports);
const ex = inst.exports; const mem = new Uint8Array(ex.memory.buffer);
// IR の define から各関数の wasm 側パラメータ型を取得 (kio_norm.ll)
const ll = readFileSync(`${W}/kio_norm.ll`, "utf8");
const P = {};
for (const m of ll.matchAll(/^define (\S+) @(\S+?)\((.*?)\)/gm)) P[m[2]] = { ret: m[1], params: m[3].split(",").filter(s => s.trim()).map(s => s.trim().split(" ")[0]) };
const f32 = new Float32Array(1), u32 = new Uint32Array(f32.buffer), f64 = new Float64Array(1), u64 = new BigUint64Array(f64.buffer);
const hex = (b) => Buffer.from(b).toString("hex");
const out = [];
for (const c of cases) {
  const fn = ex[c.fn]; const p = P[c.fn]; const rt = sig[c.fn][0];
  if (!fn) { out.push({ ret: "ERR:noexport" }); continue; }
  let sp = 4 * 1024 * 1024; const alloc = (n) => { const a = sp; sp += (n + 15) & ~15; return a; };
  const raw = []; let bufAddr = null, bufLen = 0;
  for (const a of c.args) {
    if (a.t === "buf") { const b = Buffer.from(a.hex, "hex"); const ad = alloc(b.length); mem.set(b, ad); raw.push({ ptr: ad }); if (a.dump) { bufAddr = ad; bufLen = b.length; } }
    else if (a.t === "ref") { const ad = alloc(8); new DataView(ex.memory.buffer).setBigInt64(ad, BigInt(a.v), true); raw.push({ ptr: ad }); }
    else if (a.t === "f64ref") { const ad = alloc(8); new DataView(ex.memory.buffer).setFloat64(ad, a.v, true); raw.push({ ptr: ad }); }
    else if (a.t === "i64") raw.push({ i: BigInt(a.v) });
    else if (a.t === "f32") raw.push({ f: a.v });
  }
  const args = raw.map((r, i) => {
    const ty = p.params[i];
    if (r.ptr !== undefined) return ty === "i64" ? BigInt(r.ptr) : r.ptr;       // ポインタ引数: ptr(i32) または i64
    if (r.f !== undefined) return r.f;
    return ty === "i64" ? BigInt.asIntN(64, r.i) : Number(BigInt.asIntN(32, r.i)); // 64bit long が i32 引数に潰される場合は下位 32bit のみ渡る (IR の型復元欠陥をそのまま測る)
  });
  while (args.length < p.params.length) args.push(p.params[args.length] === 'i64' ? 0n : 0);   // RetDec が余分に生やした未使用 arg を 0 埋め
  let ret, sret = null;
  try {
    if (p.ret === "i128") { sret = alloc(16); ret = fn(sret, ...args); }
    else ret = fn(...args);
  } catch (e) { out.push({ ret: "ERR:" + e.message }); continue; }
  let rhex = "";
  const dv = new DataView(ex.memory.buffer);
  if (rt === "void") rhex = "";
  else if (rt === "f32") { if (sret !== null) rhex = Buffer.from(mem.slice(sret, sret + 4)).toString("hex"); else { f32[0] = ret; rhex = u32[0].toString(16).padStart(8, "0").match(/../g).reverse().join(""); } }
  else if (rt === "f64") { if (sret !== null) rhex = Buffer.from(mem.slice(sret, sret + 8)).toString("hex"); else { f64[0] = ret; rhex = Buffer.from(new Uint8Array(f64.buffer)).toString("hex"); } }
  else { const v = typeof ret === "bigint" ? ret : BigInt(ret); rhex = (rt === "u32" ? BigInt.asUintN(32, v) : BigInt.asUintN(64, v)).toString(16); }
  const o = { ret: rhex }; if (bufAddr !== null) o.buf = hex(mem.slice(bufAddr, bufAddr + bufLen));
  out.push(o);
}
writeFileSync(`${W}/res_wasm.json`, JSON.stringify(out));
