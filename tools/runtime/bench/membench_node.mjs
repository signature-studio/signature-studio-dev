import { readFileSync } from "node:fs"; import path from "node:path"; import { fileURLToPath } from "node:url";
import { runMemBench } from "./membench_run.mjs";
const d = path.join(path.dirname(fileURLToPath(import.meta.url)), "../work/bench");
console.log(JSON.stringify(await runMemBench(readFileSync(d + "/mem32.wasm"), readFileSync(d + "/mem64.wasm")), null, 1));
