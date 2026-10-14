// AU-35 (#3193): Safari が WebDriver BiDi を話すかの確認 (macOS)。safaridriver の新規セッションで webSocketUrl: true を要求し、
// 返った capabilities の webSocketUrl が文字列なら BiDi 接続の入口がある。1 行の JSON を出す。
// 使い方 (macOS): node harness/safari_probe.mjs    終了コード 0 = webSocketUrl あり / 1 = なし・エラー
import { startSafaridriver } from "./safari.mjs";

let sd = null, caps = null, sid = null, err = null;
try {
  sd = await startSafaridriver();
  const v = await sd.req("POST", "/session", { capabilities: { alwaysMatch: { browserName: "Safari", webSocketUrl: true } } });
  sid = v.sessionId;
  caps = v.capabilities;
} catch (e) { err = String(e); } finally {
  if (sid) await sd.req("DELETE", `/session/${sid}`).catch(() => {});
  sd?.close();
}
const bidi = typeof caps?.webSocketUrl === "string";
console.log(JSON.stringify({ browserName: caps?.browserName ?? null, browserVersion: caps?.browserVersion ?? null, webSocketUrl: caps?.webSocketUrl ?? null, bidi, error: err }));
process.exit(bidi ? 0 : 1);
