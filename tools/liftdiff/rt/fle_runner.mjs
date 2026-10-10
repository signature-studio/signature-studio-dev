// fle_runner.mjs — flelift target (x64c lift) 用 wasm ランナ (CAB-232)。
// ld_runner.mjs のプロトコル実装を共有し、case の関数呼出しだけを flelift ブリッジ
// (_ld_w_case_begin → _fle_ld_run / _fle_ld_xmm0 → _ld_w_case_end) に差し替える。
// 使い方: node fle_runner.mjs <wasm.cjs> <image.bin|-> <origin-hex> <delta-hex> [--layout] [--init=...]
import fs from 'fs';
import readline from 'readline';
import path from 'path';
import vm from 'vm';

const [, , wasmJs, imageBin, originHex, deltaHex, ...rest] = process.argv;
const initExports = (rest.find((x) => x.startsWith('--init=')) || '--init=').slice(7).split(',').filter(Boolean);
const layoutOnly = rest.includes('--layout');
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

const dv = new DataView(new ArrayBuffer(8));

function runCase(line) {
  // JS 専用トークン sig= rt= を抜く (C 側は未知キーを無視)
  let rt = 'i64';
  for (const t of line.split(/\s+/)) {
    if (t.startsWith('rt=') && t.slice(3)) rt = t.slice(3);
  }
  putStr(line);
  mod._ld_w_case_begin();
  const sp0 = sp_get();
  let status = 'ok', detail = '', rax = 0n, x0 = 0n, hasRet = 1;
  try {
    globalThis.__ld_call = () => mod._fle_ld_run();
    const r = vm.runInThisContext('__ld_call()', { timeout: 1000 });
    if (rt === 'void') hasRet = 0;
    else if (rt === 'double' || rt === 'float') x0 = BigInt.asUintN(64, mod._fle_ld_xmm0());   // 生 bits (cmp_ret が幅で処理)
    else if (typeof r === 'bigint') rax = BigInt.asUintN(64, r);
    else if (typeof r === 'number') rax = BigInt(r >>> 0);
  } catch (e) {
    status = 'trap'; hasRet = 0;
    const msg = (e && e.message) || String(e);
    if (/timed out/.test(msg)) status = 'timeout';
    const frames = ((e && e.stack) || '').split('\n').map((s) => (s.match(/at (\S+) \(/) || [])[1]).filter(Boolean).slice(0, 8);
    detail = msg + ' @ ' + frames.join(' < ');
    try { sp_restore(sp0); } catch (_) {}
    // emcc abort / vm timeout / trap は C スタック状態を毒する恐れがある — 正常応答を返してから
    // プロセスを終了し、セッション側のランナ再起動 (crash → restart) に委ねる (badjson 連鎖の防止)。
    // wasm の単純 OOB trap はモジュール状態が健常なので継続する (sp_restore 済)。
    if (/Aborted|abort\(/i.test(msg) || /timed out/.test(msg)) {
      putStr(status, [detail, rt]);
      const p = mod._ld_w_case_end(rax, 0n, x0, 0n, hasRet);
      out(mod.UTF8ToString(p));
      process.exit(0);
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
    mod._ld_w_snapshot(); out('{"ready":true}');
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
