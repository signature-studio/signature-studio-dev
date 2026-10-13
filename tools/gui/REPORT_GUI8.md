# GUI-8 (#184) — e2e 載せ替え・長時間ストレス・Firefox 取込み

(`tools/gui/REPORT.md` §13 から 250 行上限のため分割。内容は同一)

## 11. GUI-8 (#184): e2e の agent-browser 載せ替え・長時間ストレス・Firefox 取込み

### 結論
- `tools/gui/e2e/e2e.mjs` (CDP 直叩き 247 行) を `tools/e2e/suite/drivers/{agent-browser,puppeteer}.mjs` 経由に載せ替えた (既定 agent-browser 0.39.0、`E2E_DRIVER=puppeteer` で puppeteer-core)。`bash tools/gui/e2e.sh` は ALL PASS・golden 差 0 (読み戻し 0/64000 px、スクリーンショット 0 px)。
- 長時間ストレス (`e2e/stress.sh`): 50,000 フレームで入力リング drop 0・out_full_waits 0・wasm memory 増加なし・surface gen 不変。ネガコン 3 本 (golden 改竄 / burst / leak) は全て exit 1 で不合格を検出。
- Firefox は #127 (PR #433, `tools/runtime/REPORT.md` RT-9) の結果を取込み、fallback 方針を `PROTOCOL.md §12` に追記。Safari と Firefox の実描画 (WebGL2/AudioWorklet) は未測定。

### 検証 (検証起点 = コミット済み `0ec2543` (以降のコミットは docs のみでコード不変)、runner 4 CPU、`/proc/loadavg` 開始 0.72 → 終了 2.25)
| 項目 | 結果 |
|---|---|
| `bash tools/gui/e2e.sh` (mingw-w64 + RetDec + emsdk, 全 6a〜6g 段) | rc=0、155 s、ALL PASS |
| 6/6・6b (memory grow)・6d (reach): agent-browser | 全て `EXACT MATCH (0 differing px of 64000)` (読み戻し) + `0 differing px` (実画面)。6c fail-fast も PASS |
| puppeteer-core (Chrome 154.0.8037.97) で e2e.mjs / stress 5,000 フレーム | 両方 PASS・golden 差 0 |
| 6a ネガコン: golden を 1 画素改竄 (`E2E_TAMPER=1`) | exit 1 + `MISMATCH` (握りつぶさない) |
| ストレス (固定メモリ 128 MiB): 50,010 frames / 54,046 moves / 26.6 s | `inDropped=0`・`outFullWaits=0`・mem 134217728→134217728・`gens={"0":1}` 不変・終状態 golden 差 0 |
| ストレス (grow 版; `memory.grow(1page)` を 6 回注入): 50,010 frames / 27.1 s | `inDropped=0`・mem 3801088→4194304 (前半の注入分のみ、後半増加 0)・`memory.buffer` 差替え 6 回 (worker 再取得後も描画継続)・終状態 golden 差 0 |
| ネガコン burst (200,000 move を同期 push) | exit 1: `input ring dropped 198975 events` |
| ネガコン leak (後半も `memory.grow`) | exit 1: `wasm memory still growing in 2nd half: 3801088 → 3932160` |
| worker stats (固定メモリ 50,014 flush) | `flushMs` 合計 10313 ms (平均 0.21 ms/flush)・`maxFlushMs` 5.26・`seqRetries/seqForced/seqDeferred` 0 |

- **判定の作り**: `judgeStress()` (`e2e/e2e_lib.mjs`) が失敗理由配列を返し、非空なら `stress.mjs` は exit 1。`stress.sh` はネガコンを「exit が 1 であること」だけ受理し (0/2/3 は FAIL)、不合格でも exit 0 になる gate を作らない。「メモリ有界」は (a) 中点→末尾で増加なし (b) 絶対上限 256 MiB 以下、で判定。
- **ストレスの負荷の性質**: テスト PE (gui_app) に対し、実マウス down 後にページ内から合成 `pointermove` (1 move = 1 `WM_MOUSEMOVE` = 1 フレーム) を連続投入 (90% は 1 move ごとにフレーム ack 待ち、10% は 8 move 連打)。入力経路 (`gui.ts` の pointer → 入力リング → shim → WndProc → present → worker) は通るが、CDP 実入力ではない (実入力は 1 入力 = 1 agent-browser 子プロセス起動で、シナリオ 10 入力分で 1180 ms かかった実測から数万回は採らなかった)。実入力は前段と終状態収束 (mouse up・key `A`/`b`・Escape) で使用。
- agent-browser 載せ替えで追加した driver API: `mouse(move|down|up)`・`press`・`setViewport` (puppeteer 側にも同 IF で実装)。`screenshot` は viewport 全体 (480x360) を撮り左上 320x200 を golden と比較 (CDP 版の clip 指定は agent-browser に無い)。

### 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
| Safari 未測定 / Firefox の AudioWorklet・Worker WebGL2 は headless で判定不能 / **Firefox 上での gui e2e (本 e2e の Firefox 実行) は未実施** (本 run の両ドライバは Chrome で実行。agent-browser / puppeteer-core の Firefox 起動は未試行) | Firefox の SAB/`Atomics.waitAsync`/OffscreenCanvas 2D は #127 で可と測定済み。ただし gui shim 全体の Firefox 動作は未確認 | #127 (open 維持。実機/BiDi 実行は PM 判断) |
| CI 合流 (`.github/workflows`) | Actions App に workflows 権限なし。`e2e.sh` は emsdk+RetDec+mingw が要り重い | #66 [E2E-4] に「`bash tools/gui/e2e/stress.sh` を単体 job 化 (前提 wasm のビルド後)」を依頼 |
| 実 FLEngine 負荷でのリーク検査 (テスト PE は 1 サーフェス・小規模) | 実アプリでの surface 再生成・GDI ハンドル枯渇は未測 | GUI-3 #174 到達後に #184 へ追記 |
| 24 h 級の soak (本件は 27 s / 50,000 フレーム) | 低頻度リークは未検出の可能性 | 必要なら #184 に STRESS_FRAMES を上げた再実行を依頼 (`STRESS_FRAMES=5000000`) |
