// flapi provider の実装集合を id 順に出力する (PY-280: provider_check.mjs の期待集合の移行前後の一致検査)。
//   node tests/provider_impl_dump.mjs > impl.txt     (前提: provider/build.sh 済み)
// 出力: 実装済み id を 1 行ずつ。末尾に件数行 (implemented / unimplemented)。
import fs from "node:fs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const engine = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
let impl = 0, unimpl = 0;
for (const id of ids) {
  let notImpl = false;
  try { engine.call(id, []); } catch (e) { notImpl = !!e.message?.startsWith("Unspecified error (not implemented:"); }
  if (notImpl) unimpl++;
  else { impl++; console.log(id); }
}
console.log(`implemented=${impl} unimplemented=${unimpl} total=${ids.length}`);
