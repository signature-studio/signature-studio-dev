// 単発実行: node harness/midi_one.mjs ["corrupt=drop500"]  (index_midi.html の結果 JSON を出力)
import { withChrome } from "./chrome.mjs";
import path from "node:path"; import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const r = await withChrome({ root: path.join(here, "../build/web"), page: "index_midi.html" + (process.argv[2] ? "?" + process.argv[2] : ""), log: () => {} }, (c) => c.eval("window.__done"));
console.log(JSON.stringify(r, null, 1));
