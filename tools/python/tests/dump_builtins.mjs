import createFlPython from "../dist/flpy.js";
import fs from "node:fs";
const out = [];
const M = await createFlPython({ locateFile: (p) => new URL("../dist/" + p, import.meta.url).pathname, print: (t) => out.push(t), printErr: (t) => out.push(t) });
M.ccall("flpy_init", "number", ["string"], [""]);
M.ccall("flpy_run", "number", ["string", "string"], ["import sys, json\nprint(json.dumps({'builtin_module_names': sorted(sys.builtin_module_names), 'version': sys.version, 'stdlib_dir': sys.path}))", "x"]);
fs.writeFileSync(new URL("../work/wasm_builtins.json", import.meta.url), out.join("\n"));
