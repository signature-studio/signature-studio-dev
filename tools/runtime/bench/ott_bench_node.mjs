import { readFileSync } from "node:fs"; import path from "node:path"; import { fileURLToPath } from "node:url";
import { runBench } from "./ott_bench.mjs";
const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), "../work/bench");
console.log(JSON.stringify(await runBench(readFileSync(dir + "/ott32.wasm"), readFileSync(dir + "/ott64.wasm")), null, 1));
