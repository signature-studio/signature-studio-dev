// AU-35 (#3193): harness/safari.mjs の WebDriver 手順を safaridriver_mock.mjs に対して確かめる (Linux・ブラウザ無し)。
// 使い方: SAFARIDRIVER=tools/audio/test/safaridriver_mock.mjs node tools/audio/test/safari_mock_test.mjs
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { withSafari } from "../harness/safari.mjs";

const root = fs.mkdtempSync(path.join(process.env.RUNNER_TEMP ?? os.tmpdir(), "safari-mock-"));
fs.writeFileSync(path.join(root, "index.html"), "<!doctype html><title>mock</title>");
const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"} ${msg}`); if (!ok) process.exitCode = 1; };

const got = await withSafari({ root, page: "index.html?api=asio&mode=sine&buf=256&depth=2&secs=4" }, async (sf) => {
  return await sf.eval("window.__done");
});
check(got?.ok === true, "execute/async の戻り値が JSON 文字列として parse される");
check(got?.urls?.length === 1 && /^http:\/\/127\.0\.0\.1:\d+\/index\.html\?api=asio&mode=sine&buf=256&depth=2&secs=4$/.test(got.urls[0]), `初回 navigate の URL (${got?.urls?.[0]})`);
check(got?.timeouts?.script === 600000, "script timeout が 600000 ms に延長される");

let threw = null;
try { await withSafari({ root, page: "index.html" }, async (sf) => sf.eval("window.__fail")); } catch (e) { threw = String(e); }
check(threw !== null && threw.includes("page exception: Error: mock page exception"), `ページ側の例外 (ページの try/catch → __exc) が呼び出し側へ伝わる (${threw})`);
threw = null;
try { await withSafari({ root, page: "index.html" }, async (sf) => sf.eval("window.__http")); } catch (e) { threw = String(e); }
check(threw !== null && threw.includes("javascript error"), `HTTP エラー応答 (500) が呼び出し側へ伝わる (${threw})`);

process.exit(process.exitCode ?? 0);
