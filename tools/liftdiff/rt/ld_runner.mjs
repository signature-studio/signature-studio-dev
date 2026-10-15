// liftdiff wasm ランナ (node). stdin: 1 行プロトコル (LAYOUT 以外は native と共通)。stdout: 1 case 1 行 JSON。
// 使い方: node ld_runner.mjs <wasm.cjs> <image.bin> <origin-hex> <delta-hex> [--layout]
//   --layout: arena/heap/stack のアドレスを JSON 1 行で出力して終了 (native ランナの LAYOUT 行の元)
import fs from 'fs';
import readline from 'readline';
import path from 'path';
import vm from 'vm';

const [, , wasmJs, imageBin, originHex, deltaHex, ...rest] = process.argv;
const initExports = (rest.find((x) => x.startsWith('--init=')) || '--init=').slice(7).split(',').filter(Boolean);
const layoutOnly = rest.includes('--layout');
// wasm 1 case の打切り ms (target JSON wasm_timeout_ms)。既定 1000
const wasmTimeoutMs = Number((rest.find((x) => x.startsWith('--timeout-ms=')) || '--timeout-ms=1000').slice(13)) || 1000;
const mod = await (await import(path.resolve(wasmJs))).default({ printErr: () => {}, print: () => {} });
const exp = mod.wasmExports || mod.asm || {};
const origin = BigInt('0x' + originHex), delta = BigInt('0x' + deltaHex);
const img = imageBin === '-' ? Buffer.alloc(0) : fs.readFileSync(imageBin);
const u8 = () => mod.HEAPU8;
u8().set(img, Number(origin));
mod._ld_w_init(origin, delta);
for (const e of initExports) mod['_' + e]();
const lay = new BigUint64Array(6);
{
  const p = mod._malloc(48);
  mod._ld_w_layout(p);
  const v = new BigUint64Array(mod.HEAPU8.buffer, p, 6);
  for (let i = 0; i < 6; i++) lay[i] = v[i];
  mod._free(p);
}
const hx = (b) => '0x' + b.toString(16);
if (layoutOnly) {
  console.log(JSON.stringify({ arena: hx(lay[0]), arena_size: hx(lay[1]), heap: hx(lay[2]), heap_size: hx(lay[3]), stack_base: hx(lay[4]), stack_end: hx(lay[5]) }));
  process.exit(0);
}
const inbuf = mod._ld_w_inbuf();
const enc = new TextEncoder();
function putStr(s, extra = []) {
  const parts = [s, ...extra];
  let off = inbuf;
  for (const q of parts) {
    const b = enc.encode(q);
    mod.HEAPU8.set(b, off); mod.HEAPU8[off + b.length] = 0; off += b.length + 1;
  }
}
const sp_get = mod._emscripten_stack_get_current;
const sp_restore = mod.__emscripten_stack_restore || exp.emscripten_stack_restore || mod._emscripten_stack_restore;
let spSnap = 0;   // LD-126: SNAPSHOT 時の SP (RESET で戻す)

const dv = new DataView(new ArrayBuffer(8));
const toF64 = (b) => { dv.setBigUint64(0, BigInt.asUintN(64, b), true); return dv.getFloat64(0, true); };
const toF32 = (b) => { dv.setUint32(0, Number(BigInt.asUintN(32, b)), true); return dv.getFloat32(0, true); };
const f64bits = (x) => { dv.setFloat64(0, x, true); return dv.getBigUint64(0, true); };
const f32bits = (x) => { dv.setFloat32(0, x, true); return BigInt(dv.getUint32(0, true)); };
const fnCache = new Map();
function getFn(va) {
  const nm = 'function_' + va.toString(16);
  if (fnCache.has(nm)) return fnCache.get(nm);
  const f = exp[nm] || mod['_' + nm] || null;
  fnCache.set(nm, f);
  return f;
}
function coerce(ty, b, kind) {
  switch (ty) {
    case 'i64': return BigInt.asIntN(64, b);
    case 'double': return toF64(b);
    case 'float': return toF32(b);
    case 'ptr': case 'i32': return Number(BigInt.asIntN(32, b & 0xffffffffn));
    case 'i16': return Number(b & 0xffffn);
    case 'i8': return Number(b & 0xffn);
    case 'i1': return Number(b & 1n);
    default: return 0;
  }
}

function runCase(line) {
  // JS 専用トークン sig= rt= を抜く (C 側は未知キーを無視)
  let sig = [], rt = 'i64';
  for (const t of line.split(/\s+/)) {
    if (t.startsWith('sig=')) sig = t.slice(4) ? t.slice(4).split(',') : [];
    else if (t.startsWith('rt=')) rt = t.slice(3);
  }
  putStr(line);
  mod._ld_w_case_begin();
  const va = mod._ld_w_fn();
  const f = getFn(va);
  const sp0 = sp_get();
  let status = 'ok', detail = '', rax = 0n, x0 = 0n, hasRet = 1;
  if (!f) {
    status = 'no_export'; detail = 'function_' + va.toString(16); hasRet = 0;
  } else {
    const na = mod._ld_w_nargs();
    const args = [];
    for (let i = 0; i < sig.length; i++) {
      const v = i < na ? mod._ld_w_arg(i) : 0n;
      args.push(coerce(sig[i], v, i < na ? mod._ld_w_arg_kind(i) : 0));
    }
    try {
      globalThis.__ld_call = () => f(...args);
      const r = vm.runInThisContext('__ld_call()', { timeout: wasmTimeoutMs });
      if (rt === 'void') hasRet = 0;
      else if (rt === 'double') x0 = f64bits(r);
      else if (rt === 'float') x0 = f32bits(r);
      else if (typeof r === 'bigint') rax = BigInt.asUintN(64, r);
      else if (typeof r === 'number') rax = BigInt(r >>> 0);
    } catch (e) {
      status = 'trap'; hasRet = 0;
      const msg = (e && e.message) || String(e);
      if (/timed out/.test(msg)) status = 'timeout';
      const frames = ((e && e.stack) || '').split('\n').map((s) => (s.match(/at (\S+) \(/) || [])[1]).filter(Boolean).slice(0, 8);
      detail = msg + ' @ ' + frames.join(' < ');
      try { sp_restore(sp0); } catch (_) {}
    }
  }
  putStr(status, [detail, rt]);
  const p = mod._ld_w_case_end(rax, 0n, x0, 0n, hasRet);
  return mod.UTF8ToString(p);
}

function out(s) {
  const b = Buffer.from(s + '\n');
  let off = 0;
  while (off < b.length) {
    try { off += fs.writeSync(1, b, off, b.length - off); }
    catch (e) { if (e.code !== 'EAGAIN') throw e; }
  }
}
const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const l of rl) {
  if (l.startsWith('WR ')) {
    const [a, b] = l.slice(3).split(' ');
    mod._ld_w_add_wr(BigInt('0x' + a), BigInt('0x' + b));
  } else if (l === 'SNAPSHOT') {
    mod._ld_w_snapshot(img.length); spSnap = mod._emscripten_stack_get_current(); out('{"ready":true}');
  } else if (l.startsWith('RESET ')) {
    const m = Number(l.slice(6));
    if (m & 9) sp_restore(spSnap);   // 1 (stk) と 8 (sp) のどちらでも SP を戻す
    mod._ld_w_reset(m);
  } else if (l.startsWith('BLOB ')) {
    const k = l.indexOf(' ', 5); putStr(l.slice(5, k), [l.slice(k + 1)]); mod._ld_w_blob();
  } else if (l.startsWith('FIX ')) {
    const k = l.indexOf(' ', 4); putStr(l.slice(4, k), [l.slice(k + 1)]); mod._ld_w_fix();
  } else if (l.startsWith('CASE ')) {
    out(runCase(l.slice(5)));
  } else if (l.startsWith('PEEK ')) {
    const [, tok, cnt] = l.split(' ');
    let addr;
    if (tok.startsWith('i:')) addr = Number(origin) + Number(tok.slice(2));
    else if (tok.startsWith('a:')) addr = Number(lay[0]) + Number(tok.slice(2));
    else if (tok.startsWith('h:')) addr = Number(lay[2]) + Number(tok.slice(2));
    else addr = Number(tok);
    out(Buffer.from(mod.HEAPU8.subarray(addr, addr + Number(cnt))).toString('hex'));
  } else if (l === 'STATE') {
    putStr('STATE', ['', '']); out(mod.UTF8ToString(mod._ld_w_state()));
  } else if (/^(SIMG|SHEAP|SMODEL) /.test(l) || l === 'SSNAP') {
    const parts = l.split(' ');
    putStr(parts[0], [parts[1] || '', parts[2] || '']); mod._ld_w_state();
  } else if (l === 'QUIT') break;
}
