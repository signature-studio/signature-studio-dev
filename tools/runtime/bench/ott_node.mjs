import { readFileSync } from "node:fs";
import { loadOtt, makeRunner } from "./ott_driver.mjs";
import path from "node:path"; import { fileURLToPath } from "node:url";
const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), "../work/bench");
for (const v of ["ott32", "ott64"]) {
  const o = await loadOtt(readFileSync(path.join(dir, v + ".wasm")));
  const r = makeRunner(o);
  r.setup(0.5); r.process();
  console.log(v, "is64=", o.is64, "missing imports:", o.missing.length, "hash=", r.hash().toString(16));
}
