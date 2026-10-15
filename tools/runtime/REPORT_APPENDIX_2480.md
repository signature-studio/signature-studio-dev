# RT-6 実 loader 接続 (#125 2 回目) 付録: PluginPool → hostbridge 実 loader → lowbase 版 OTT

REPORT.md の 250 行上限のため、§RT-6 実 loader 接続 (#125 2 回目) の全文を分割移動した (PR #2480 で追加。移動の際も本文は無変更)。
RT-13 (#2519) で、本節の未解決「`MemoryBudget` の SharedArrayBuffer カウンタを `PluginPool` の既定経路 (Worker) に配線し…」は解決済み (`REPORT.md` の RT-13 節)。
同じく「撤去後の `pnpm runtime:memload:real` の PASS 実測 (RT-15 受入 1)」も RT-13 節の実測で満たした。

## RT-6 実 loader 接続 (#125 2 回目): PluginPool → hostbridge 実 loader → lowbase 版 OTT
既知類型との関係 (DEFECTS.md): 該当なし (ランタイム資源管理)。測定 commit は 2 つ: `80b69fa2` (初回測定) と `c531cf69` (コード HEAD。`114ee54e` と同じコードで、後続の `079dca82`・`c531cf69` は文書のみ)。`80b69fa2` 以後のコード差分は末尾の `git diff 80b69fa2 HEAD -- tools/runtime/memload/real src/runtime package.json` の出力に示す。`c531cf69` 以後のコード差分は同じ範囲で 0 行。
- 実装: `tools/runtime/memload/real/real_worker.mjs` (Worker) と `run_real.mjs` (Chrome ドライバ、`pnpm runtime:memload:real`)。`PluginPool` (`src/runtime/memory_budget.ts` を transpile) の loader を hostbridge の実 loader (共有 `hb_bridge.mjs` の `HostBridge`) に、dispose を `bridge.FreeLibrary` に接続。下の測定 (`80b69fa2`) は派生 loader `PoolBridge` (handle 採番だけを単調増加に置換) で行った。`PoolBridge` は RT-15 (#2552) で撤去済み (`REPORT_APPENDIX_2552.md`)。OTT は `tools/hostbridge/lowbase/retdec/build_m10_lb.sh` の lowbase 版 (LB_BASE 0x10000, initial 24 MiB / max 64 MiB, `ott_hb.wasm` 848,256 B)。host は `retdec/build_host_lb.sh` (`host_vst2.wasm` 3,734 B)。
- 入力素材 (展開確認済み): `work-m6-ott` (`tools/m10/work/ott_m10.ll` 957,145 B を入力に使う。lowbase 再ビルドは `lb_reloc` で再配置した copy `tools/hostbridge/lowbase/work/m10_0x10000/ott_m10.ll` 955,899 B を読む)。`plugins-ott` は NSIS インストーラ。`7z x` で取り出した `OTT_x64.dll` (PE32+, ImageBase 0x180000000, SizeOfImage 0x308000, 3,146,752 B) を `$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll` (環境変数。対応は `docs/REFERENCES.md` §4) として配置。`toolchain-emsdk` は runner 既存の [EMSDK] (emcc 6.0.12) を使用 (artifact は展開していない)。`toolchain-retdec` は ott_m10.ll があるため不使用。
- 試験内容: 150 種の alias (同一 OTT ファイル、各々独立の Memory) を sweep で 1 回ずつ pin、続けて 170 回の偏った pin (70% が先頭 40 種、同時 pin 最大 3)。cap は `DEFAULT_PLUGIN_CAPACITY` 96。cold ロード直後の初回 block (128 frame) の出力 sha256 を基準 (同ページ内の最初の cold ロード) と照合。warm pin は出力を照合せず、param 0 の読み戻し (0.5) で生存だけを見る。全 instance が同じ値を持つため、取り違えは検出しない (取り違え検出は未試験)。最後に全 unpin → 全 unload。
- 実測 (コミット済み `80b69fa2` を clean worktree で 3 回, Chrome 154.0.8037.97, 4 vCPU, 1 分 loadavg 0.58→1.70 (各回開始時)):
  | 項目 | run1 | run2 | run3 |
  |---|---|---|---|
  | pool 試験 PASS (pins 320 / loads 165 / evictions 69 / 生存 96 / peakSize 96 / peakInUse 96) | PASS | PASS | PASS |
  | cold 照合 (165 件) 全て基準と bit 一致 / warm pin param 不一致 | 0 / 0 | 0 / 0 | 0 / 0 |
  | 全 unload 後 size / inUse / bridge 登録 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
  | 試験本体 run (Chrome 内) | 1.85 s | 1.86 s | 1.81 s |
  | ネガコン neg_cap130 (cap を実測上限超) | OOM at load 124 | OOM at load 124 | OOM at load 125 |
  | ネガコン neg_nofree (dispose で FreeLibrary しない) | OOM at load 124 | OOM at load 124 | OOM at load 124 |
  | ALL PASS / exit / wall | ALL PASS / 0 / 7.05 s | ALL PASS / 0 / 6.92 s | ALL PASS / 0 / 7.09 s |
- 判定: 累計ロード 165 (> 124)、追い出し 69 で生存は 96 以下。実 OTT lowbase で、Memory 個数上限 (124) を超えるロードを pool 経由で通した。
- コード HEAD `c531cf69` の実測 (`git archive` の一時展開で 3 回。Chrome 154.0.8037.97、1 分 loadavg 0.39 (1 回目開始時のみ記録)。ref sha256 先頭 `9c77523d15157285` は `80b69fa2` と同じで、計数も一致):
  | 項目 | run1 | run2 | run3 |
  |---|---|---|---|
  | pool 試験 PASS (pins 320 / loads 165 / evictions 69 / 生存 96 / peakSize 96 / peakInUse 96。cold 照合・param・全解放の判定を含む) | PASS | PASS | PASS |
  | 試験本体 run (Chrome 内) | 1.61 s | 1.49 s | 1.48 s |
  | ネガコン neg_cap130 (OOM at load) | 125 | 124 | 125 |
  | ネガコン neg_nofree (OOM at load) | 124 | 124 | 125 |
  | ALL PASS / exit / wall | ALL PASS / 0 / 6.51 s | ALL PASS / 0 / 5.79 s | ALL PASS / 0 / 5.55 s |
- 実測で確定した事項: (a) 本試験で観測した Memory 参照の解放経路は `FreeLibrary` (dispose で呼ばないと bridge が握り続け、pool の追い出しに関係なく 124 で OOM)。他の経路は観測していない。(b) `host_close` は単一の `g_info.hmodule` (最後に load した plugin) を解放するため、任意の plugin の解放には使えない。pool は `bridge.FreeLibrary(handle)` を直接呼ぶ。(c) 採番の衝突: `hb_bridge.mjs` の旧 `LoadLibraryW` は `handle = HMODULE_BASE + (loaded.size + 1) * 0x10000` で採番するため、解放後の再ロードが既存 handle と一致し得る (再現とネガコンは `tools/hostbridge/REPORT.md` §5-c)。本節の測定は派生 `PoolBridge` で回避していた。共有 poc の単調採番 (`allocHandle`) は #2553 (RT-14) で merge 済み。
- 範囲外 / 検証範囲: Chrome 154 のみ (Firefox/Safari 未測定)。Worker 1 本のみ (per-thread カウンタ、SAB 共有カウンタは未配線)。異なる DLL の同時ロードは未実施 (plugins-ott は OTT のみ)。cold 照合の基準は node 参照ではなく同ページの最初の cold ロード (node との bit 突合は lowbase e2e 側で 500 block 実施済み)。warm pin は OTT が block 間で DSP 状態を持つため出力を照合しない。
- 再現: `bash tools/hostbridge/lowbase/retdec/build_m10_lb.sh` (前提: `$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll`、`tools/m10/work/ott_m10.ll`) → `bash tools/hostbridge/lowbase/retdec/build_host_lb.sh` → `pnpm runtime:memload:real` (`--pos-only` / `--neg-only` 可)。`c531cf69` の実測は `git archive` で一時展開した先に `work-m6-ott` を展開し、その中で上の 3 コマンドを実行した (共有 checkout の `work/` は使わない)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `MemoryBudget` の SharedArrayBuffer カウンタを `PluginPool` の既定経路 (Worker) に配線し、main+Worker 合算の 124 を pool 経路で試験 | 本試験は per-thread カウンタ。実運用の上限は未検証 | [RT-13] #2519 |
| 撤去後の `pnpm runtime:memload:real` の PASS 実測 (RT-15 受入 1) | 未実測。OTT DLL (`analysis-ott-binaries`) 素材無しで lowbase ビルドが停止 (`REPORT_APPENDIX_2552.md`)。撤去は共有 poc と挙動が同一 (採番は #2553 で merge 済み、`tools/hostbridge/REPORT.md` §5-c) | 未起票 (再測定のみ。素材が揃った run で実測し本表を更新) |
| dispose 時の FL 側 state 保存仕様 (保存の要否・形式) | 設計判断。pool は dispose フックだけ提供 | #125 へコメント (未決として記載済み) |
| 1 wasm に常駐 Memory が 124 超を載せる場合 (Kilohearts 47 stub 等の同居) | 追い出し対象外の常駐は回避できず OOM になる。回避策は未実装 | #96 (HB-H7) |
| Chrome 以外の Memory 上限 (Firefox / Safari) | 予算値 96 は Chrome 154 の実測のみに基づく | #127 (RT-9) |
| OTT 以外の DLL (freshair / serum2 / massivex) の同時ロード | 異なる lift 系統の DLL の同居は未試験 (素材 plugins-freshair 等が未取得。本 PR の範囲外) | #125 (未確認・既定は実施しない) |

- 測定後のコード差分 (`git diff 80b69fa2 HEAD -- tools/runtime/memload/real src/runtime package.json`、commit `39fb363f` と `114ee54e`)。コメント・失敗メッセージ・no-op 式の削除のみで、判定ロジックと実行経路は変えていない。出力:
```diff
diff --git a/tools/runtime/memload/real/real_worker.mjs b/tools/runtime/memload/real/real_worker.mjs
index 78ccd06f..12705ead 100644
--- a/tools/runtime/memload/real/real_worker.mjs
+++ b/tools/runtime/memload/real/real_worker.mjs
@@ -1,5 +1,5 @@
-// RT-6 実 loader 試験 (#125): PluginPool (src/runtime/memory_budget.ts) を hostbridge の実 loader に接続する Worker。
-// 実 loader = host_vst2.wasm の LoadLibraryW / FreeLibrary (hb_bridge.mjs) で、lowbase 版 OTT (DLL 1 本 = 1 Memory, initial 24 MiB) を
+// RT-6 実 loader 試験 (#125): PluginPool (src/runtime/memory_budget.ts) を hostbridge の loader に接続する Worker。
+// loader = host_vst2.wasm + hb_bridge.mjs の LoadLibraryW / FreeLibrary (LoadLibraryW の採番だけ PoolBridge で置換)。lowbase 版 OTT (DLL 1 本 = 1 Memory, initial 24 MiB) を
 // PluginPool 経由で pin / unpin / LRU 追い出しする。判定は run_real.mjs 側。
 import { ModuleTable, HostBridge, EmscriptenGuest, HMODULE_BASE } from "./hb_bridge.mjs";
 import { PluginPool, MemoryBudget, DEFAULT_PLUGIN_CAPACITY } from "./memory_budget.js";
@@ -72,7 +72,7 @@ async function runCase(mode) {
   });
 
   // OTT は block 間で DSP 状態を持つ。bit 一致を見られるのは cold ロード直後の初回 block だけ (基準 = 最初の cold ロード)。
-  // warm pin (追い出されず残っていた instance) は、出力ではなくパラメータの読み戻しで instance の取り違えを見る。
+  // warm pin (追い出されず残っていた instance) は出力を照合せず、param 0 の読み戻しで生存だけを見る (全 instance が同じ値を持つため取り違えは検出しない)。
   const use = async (k, held) => {
     const before = R.loads;
     const h = await pool.pin(`p${k}`);
diff --git a/tools/runtime/memload/real/run_real.mjs b/tools/runtime/memload/real/run_real.mjs
index ee164c21..49382281 100644
--- a/tools/runtime/memload/real/run_real.mjs
+++ b/tools/runtime/memload/real/run_real.mjs
@@ -1,6 +1,6 @@
 #!/usr/bin/env node
 // RT-6 実 loader 試験 (#125) 1 コマンド: `node tools/runtime/memload/real/run_real.mjs [--neg-only|--pos-only]`
-// PluginPool を hostbridge の実 loader (host_vst2.wasm の LoadLibraryW/FreeLibrary) に接続し、lowbase 版 OTT を
+// PluginPool を hostbridge の loader (host_vst2.wasm + hb_bridge.mjs。LoadLibraryW の採番だけ PoolBridge で置換) に接続し、lowbase 版 OTT を
 // 150 種 + 320 pin で回す。各ケースは新しい headless Chrome (= 新しいレンダラ)。判定が崩れたら exit 1。
 // ネガティブコントロール (NEG) は「壊すと OOM / 判定 FAIL になる」ことを確認し、検出しなければ exit 1。
 // 前提: bash tools/hostbridge/lowbase/retdec/build_m10_lb.sh (lowbase 版 OTT) と retdec/build_host_lb.sh (host_vst2.wasm)。
@@ -48,7 +48,7 @@ const isOom = (e) => !!e && /could not allocate memory|Out of memory/i.test(e.me
 const checks = {
   pos: (r) => {
     const f = [];
-    if (r.fatal || r.err) f.push(`例外 ${JSON.stringify(r.err)} (ロード ${r.loads} 回目${r.atLoad != null ? "" : ""})`);
+    if (r.fatal || r.err) f.push(`例外 ${JSON.stringify(r.err)} (ロード ${r.loads} 回目)`);
     if (r.pins !== PINS) f.push(`pins=${r.pins} != ${PINS}`);
     if (r.loads <= NATIVE_LIMIT) f.push(`累計ロード ${r.loads} がネイティブ上限 ${NATIVE_LIMIT} を超えていない (追い出しが効いていない)`);
     if (r.loads !== r.evictions + r.finalSize) f.push(`loads(${r.loads}) != evictions(${r.evictions}) + 生存(${r.finalSize}) (追い出し以外で entry が消えた/残った)`);
@@ -56,7 +56,7 @@ const checks = {
     if (r.finalInUse !== r.finalSize) f.push(`枠と entry の不一致 inUse=${r.finalInUse} size=${r.finalSize}`);
     if (r.coldLoads !== r.loads) f.push(`cold 照合 ${r.coldLoads} 件 != ロード ${r.loads} 件 (照合されていないロードがある)`);
     if (r.hashMismatch !== 0) f.push(`cold ロード直後の出力 sha256 が基準と不一致 ${r.hashMismatch} 件 (基準 ${r.refHash?.slice(0, 16)})`);
-    if (r.paramMismatch) f.push(`warm pin でパラメータ読み戻しが不一致 ${r.paramMismatch} 件 (instance の取り違え疑い)`);
+    if (r.paramMismatch) f.push(`warm pin で param 読み戻しが不一致 ${r.paramMismatch} 件 (instance の状態喪失疑い)`);
     if (r.handleMismatch !== 0) f.push(`hostbridge の handle と pool の対応が崩れた ${r.handleMismatch} 件`);
     if (!r.refHash) f.push("出力 sha256 の基準が無い");
     if (r.bridgeLoaded !== r.finalSize || r.bridgeHandles !== r.bridgeLoaded) f.push(`bridge の登録数 ${r.bridgeLoaded} / 一意 handle ${r.bridgeHandles} が生存 entry ${r.finalSize} と一致しない`);
```
- **コード HEAD (`c531cf69`) の e2e は上の表のとおり実測済み** (3/3 PASS、計数と ref sha256 は `80b69fa2` と一致)。上の差分出力は `80b69fa2` 基準で、`c531cf69` 以後のコード差分は 0 行。
