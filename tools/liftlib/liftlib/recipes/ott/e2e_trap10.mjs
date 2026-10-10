const M10 = process.env.OTT_CJS;
const mk = await import(M10);
let oob = 0;
for (const n of ['function_1801c69cc', 'function_1801c91cc']) {
  const mod = await (mk.default ? mk.default() : mk());
  if (mod._m6_data_install) mod._m6_data_install();
  const obj = BigInt(mod._function_18011d400(BigInt(0x30000000 + 0x310000), 0n));
  const args = n === 'function_1801c69cc' ? [obj] :
    [0x30310000, BigInt(0), BigInt(0), BigInt(0)];
  try { mod['_' + n](...args); console.log('OK  (no trap):', n); }
  catch (e) {
    const msg = String(e.message || e);
    if (/out of bounds/i.test(msg)) { console.log('FAIL (OOB!!):', n); oob++; }
    else console.log('OK  (fail-fast missing CRT, OOB 不発):', n, '|', msg.slice(0, 60));
  }
}
process.exit(oob ? 1 : 0);
