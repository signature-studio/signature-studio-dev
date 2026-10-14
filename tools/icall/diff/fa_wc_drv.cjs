const m = require(process.argv[2]);
const va = parseInt(process.argv[3], 16);
const xs = [0.5,-1.25,2.0,0.75,-3.0,1.5,-0.25,3.5];
m().then((mod) => {
  for (const x of xs) {
    try {
      const g = [0,1,2,3].map(() => BigInt(mod._malloc(0x400)));
      const dv = new DataView(new ArrayBuffer(8)); dv.setFloat64(0, x);
      mod._ott_run(0x30000000 + (va - 0x180000000), g[0], g[1], g[2], g[3], dv.getBigUint64(0), 0n, 0n, 0n);
      console.log('OK');
    } catch (e) { console.log('TRAP ' + String(e).slice(0, 80)); }
  }
});
