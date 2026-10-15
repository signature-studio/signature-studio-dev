// kh29_stack_probe.cjs — #1821 (KH-29): 入口 function_180ef7fc0 を実行して trap させ、kh_stack に残る
// PE 絶対 VA 形 (0x1_8xxxxxxx) の 8 byte 値を列挙する。戻り番地 (emulated native VA) と、trap 時点で
// 呼び出し元が渡した引数 (rdx = const char*) を区別して読むのに使う。
//   node scripts/kh29_stack_probe.cjs [workDir]   (license/ で実行。workDir 既定: work/licF)
const path = require('path');
const dir = path.resolve(process.argv[2] || 'work/licF');
const Mod = require(path.join(dir, 'mod.cjs'));
(async () => {
  const M = await Mod();
  let msg = null;
  try { M['_function_180ef7fc0'](0x04000000n, 0n, 0n, 0n); } catch (e) { msg = String(e && e.message || e); }
  console.log('entry run ->', msg);
  const base = Number(M['_kh_stack_ptr']());
  const H = M.HEAPU8, dv = new DataView(H.buffer);
  console.log('kh_stack base 0x' + base.toString(16) + ' (stack 窓を 8 byte 単位で走査)');
  for (let a = Math.max(0, base - 0x100); a + 8 <= Math.min(H.length, base + 0x10100); a += 8) {
    const lo = dv.getUint32(a, true), hi = dv.getUint32(a + 4, true);
    if (hi === 1 && lo >= 0x80000000 && lo < 0x90000000) {
      console.log('  off', a - base, 'value 0x1' + lo.toString(16).padStart(8, '0'));
    }
  }
})().catch(e => { console.error('probe error', e); process.exit(1); });
