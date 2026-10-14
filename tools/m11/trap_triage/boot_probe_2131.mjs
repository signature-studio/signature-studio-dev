// #2131: boot 直後に ON/OFF で分かれるページ (既定 0x10250000) の差と、boot 中の [ov] / icall trace を出す。
//   usage: BP_A=<ON dir> BP_B=<OFF dir> [BP_PAGE=0x10250000] node trap_triage/boot_probe_2131.mjs
import fs from 'fs';

const PG = 4096;
const PAGE = parseInt(process.env.BP_PAGE || '0x10250000', 16);

const boot = async (dir) => {
  const m = await import(dir + '/m11_boot.cjs');
  const err = [];
  const mod = await m.default({ printErr: (s) => err.push(String(s)) });
  mod.HEAPU8.set(fs.readFileSync(dir + '/m11_image.bin'), 0);
  mod._m11_set_survey(1);
  if (process.env.BP_TRACE) mod._m11_set_trace(1);
  const sp_boot = mod._emscripten_stack_get_current();
  try { mod._m11_boot_enter(0n, 1n); } catch (e) {
    if (!(e && e.m11_dllmain_done !== undefined)) throw e;
    mod.__emscripten_stack_restore(sp_boot);
  }
  mod._m11_set_trace(0);
  return { mod, err };
};

const A = await boot(process.env.BP_A), B = await boot(process.env.BP_B);
const a = A.mod.HEAPU8, b = B.mod.HEAPU8;
const ba = Buffer.from(a.buffer, a.byteOffset, a.length), bb = Buffer.from(b.buffer, b.byteOffset, b.length);
const diffs = [];
for (let off = 0; off < a.length; off += PG) if (!ba.subarray(off, off + PG).equals(bb.subarray(off, off + PG))) diffs.push(off);
console.log('boot diff pages:', diffs.length, diffs.slice(0, 40).map((o) => '0x' + o.toString(16)).join(' '));
const pa = ba.subarray(PAGE, PAGE + PG), pb = bb.subarray(PAGE, PAGE + PG);
const bytes = [];
for (let i = 0; i < PG; i += 8) if (!pa.subarray(i, i + 8).equals(pb.subarray(i, i + 8))) bytes.push(i);
console.log(`page 0x${PAGE.toString(16)}: differing 8-byte slots=${bytes.length}`);
for (const i of bytes.slice(0, 24)) console.log(`  +0x${i.toString(16)} ON=${pa.readBigUInt64LE(i).toString(16)} OFF=${pb.readBigUInt64LE(i).toString(16)}`);
const ovA = A.err.join('\n').split('\n').filter((l) => /\[ov\]|\[m11\]\[(icall|InitUnits|InitLib)/.test(l));
const ovB = B.err.join('\n').split('\n').filter((l) => /\[ov\]|\[m11\]\[(icall|InitUnits|InitLib)/.test(l));
console.log('boot trace ON lines:', ovA.length, 'OFF lines:', ovB.length);
console.log(ovA.slice(0, 30).join('\n'));
console.log('ASCII ON  0x' + PAGE.toString(16) + ':', JSON.stringify(Buffer.from(ba.subarray(PAGE, PAGE + 96)).toString('latin1')));
console.log('ASCII OFF 0x' + PAGE.toString(16) + ':', JSON.stringify(Buffer.from(bb.subarray(PAGE, PAGE + 96)).toString('latin1')));
