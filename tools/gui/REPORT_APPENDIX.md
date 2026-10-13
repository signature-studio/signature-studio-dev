# gui REPORT 付録 — §9 GUI-4 (#180) 全文

REPORT.md の 250 行上限のため §9 (#180) と §15 (#181 続き) を分割移動。本体: [REPORT.md](REPORT.md)。

## 9. GUI-4 (#180): WebGL2 present / dirty 複数矩形 / rAF 同期 / seqlock
既知類型との関係: 該当なし (lift 欠陥ではなく present 経路の設計。`docs/DEFECTS.md` への追加類型なし)。検証起点 commit: コードは `88efd49` (レビュー指摘 A・B・軽微 2 の修正後; present e2e 30 run・seqlock・tearing・golden・auto 降格の数値は全てこの HEAD・クリーン tree での実測)。frame time 表だけは修正前の `09e3db9` での実測 (bench は再測定していない; `88efd49` は seqlock 経路・staged 転送の関数分割 `stage()`/`uploadStaged()`・auto 判定のみを変え、seqlock off の GL 経路の処理は同一)。

### 結論
- **FL 非依存の範囲を実装し e2e 済み・FL 依存の範囲は未達** (受入条件は満たしていない → PR は `Refs #180`)。実装: `src/runtime/gui_present_gl.ts` (WebGL2: BGRA を `texSubImage2D` + fragment swizzle)・`gui_dirty.ts` (surface 内複数矩形の併合)・`gui_renderer.ts` (`GuiPresentOptions`: `backend` / `sync` / `seqlock`)・shim の seqlock 書込み側 (`GuiSurface.wseq`, `gui_core.c` / `gui_gdi.c`)。既定は従来経路 (2D + 即時) で挙動不変。仕様は [PROTOCOL.md §4](PROTOCOL.md)。
- **golden 画素一致 (差 0)**: 模擬 guest で GuiShared を駆動 (wasm / lift 不要)。同一の操作列 46 step (生成・z 前面化・表示切替・移動・リサイズ・破棄/再生成・1〜4 個/step の dirty 矩形 (隣接を含む)・alpha 乱数) を 4 方式 (従来 CPU・WebGL2 direct+即時・WebGL2 staged+rAF+seqlock・CPU+rAF+seqlock) へ流し、**毎 step 640×360 px (u32 全件) を独立 oracle** (バイト単位 painter's algorithm) と比較: **4 方式とも 46 step × 230,400 px = 10,598,400 px で差 0**。CDP スクリーンショット (ブラウザ合成後) 4 面 × 230,400 px も差 0。
- **実 GPU の frame time は未測** (CI の headless Chrome は SwiftShader = ソフトウェア GL)。この環境の比較表を下に示すが、**GPU 化の効果の判断材料にはならない** (下記 解釈)。
- **seqlock**: 書込み中 surface は読まず直前の整合フレームを保ち、静止後に再試行して新フレームを出す (決定的テスト: 書込み中 4 方式 + 読出し後・検証前に書込みが始まる経路 4 方式)。WebGL2 は staging へ行コピー → `stable()` で検証 → 成功時のみ `texSubImage2D` (検証前にテクスチャへ書かない; seqlock off は従来どおり共有メモリを直接転送)。確率的 tearing 試験 (WebGL2 + rAF, 90 frame, 30 run): off で tear 発生 4〜9 件 / **on で 0 件 (30 run 全て; 強制読出し 0)**。ただし**検出と再試行であり snapshot isolation ではない**。

### 検証 (`bash tools/gui/present/e2e.sh`; `tools/gui/e2e.sh` の 6f/6 にも組込み)
| 検査 | 結果 (`bash tools/gui/present/e2e.sh` bench 省略を 30 run: **30 PASS / 0 FAIL**) | 陰性対照 |
|---|---|---|
| golden 4 方式 × 46 step × 230,400 px | 30 run × 4 方式 = 120 件全て差 0 | present せず 1 px 書換え → 差 **1** px を検出 / fragment swizzle を `.rgb` へ壊す → 差 10,557,172 px (FAIL) |
| スクリーンショット 4 面 | 差 0 | swizzle 破壊で差 229,492 px (FAIL) |
| 複数矩形併合 (WebGL2 direct) | 68〜89 PRESENT → 54〜70 矩形 (30 run 全てで矩形数 < PRESENT 数; PRESENT 数は ingest のまとまり方で run ごとに変わる) | `mergeRects` 単体 7 件 (性質テスト: 400 ケースで入力全画素が出力に含まれる = ビットマップ検算) |
| rAF 同期 (staged+raf) | 30 run 全てで rAF 起動 = flush 数 (29 run は 46、1 run は 47 flush)・即時 0・タイマ救済 0。判定は「rAF 起動 ≥ flush − max(1, 10%)・即時 0」 (レビューで旧 `timer === 0` の厳密一致が 19 run 中 1 run `timer=1` で FAIL したため緩和) | 未実施 (許容内のタイマ救済を再現する手段なし。`rafFlushes > 0` と即時 0 の条件は維持) |
| seqlock 決定的 (書込み中) | gl/cpu × 即時/rAF 4 方式 × 30 run: 書込み中は旧フレーム維持 (deferred 1〜5)・静止後 10〜23 ms で新フレーム・forced 0。**検証の前から `wseq` が奇数の経路だけ**を通る | seqlock off は書込み中に新フレームを読む (保護なし; 30 run 全て) |
| seqlock 決定的 (検証中の書込み開始) | 4 方式 × 30 run: surface を読んだ直後・検証の前に guest の書込み開始 (`wseq` 偶→奇) を注入 → 注入 1 回・retries 1・deferred 1〜5・読んだ内容は表示されず旧フレーム維持・静止後 11〜24 ms で新フレーム・forced 0 | 修正前 (`96cf00b` の renderer/GL に同じテストを適用): **gl 即時・gl rAF の 2 方式は新フレームを表示 (= 検証前に `texSubImage2D` していた) で FAIL**、cpu 2 方式は修正前も OK |
| `backend: auto` の降格 | 正常 → webgl2 / シェーダ不可 → 2d へ降格して readback 可 / プローブ後に描画先だけ失敗 → `[gui] 2D fallback unavailable: ...` の明示エラー (30 run 同一) | 修正前: シェーダ不可で `TypeError: Cannot set properties of null (setting 'fillStyle')` |
| tearing 確率的 | 下記 (30 run 全て「on の発生 ≤ forced」成立) | seqlock off (WebGL2) で tear 発生 4〜9 件 (30 run; 全 run で off ≥ 4 > on = 0) |
- **全体 `bash tools/gui/e2e.sh` (`88efd49`, クリーン tree, 4 CPU, RetDec・emsdk・mingw あり): ALL PASS, 55.7 s** (1 run; 6f/6 の present e2e の load は 2.20 → 2.02)。内訳: native `selftest` 319 passed / 0 failed・native lift golden EXACT MATCH・`reach_test` 11 / `adapt_test` 28 passed・wasm の golden EXACT MATCH (固定メモリ・ALLOW_MEMORY_GROWTH)・fail-fast OK・reach log 36 API・sigprobe `signature mismatch=0` (陰性対照 177)・present e2e ALL PASS。他に `tsc --noEmit`・`pnpm build`・`node tools/runtime/gui_e2e.mjs` (ALL OK, 4.2 s) も `88efd49` で確認。
- **tearing 試験の定義**: guest worker が 1280×720 全面を 1 色/フレームで行ごとに描画 (行あたり 8 µs の busy、書込みは busy だけで 5.76 ms/フレーム以上、周期 16 ms、90 frame、seqlock 書込み側プロトコルに従う)。描画器は rAF 同期。毎 flush 後に左端 1 列を読戻し、行ごとに色が混在すれば tear。「発生件数」= 整合→tear への遷移回数。WebGL2: seqlock off 4〜9 件、on 0 件 (30 run; on の `forced` は 30 run 全て 0、`deferred` 19〜34、`seqRetries` 0〜4)。検査は「on の発生件数 ≤ forced」 (強制読出し = 飢餓回避は整合を諦めるので tear を許容する)。CPU は ingest が FRAME_END 直後に完了するため off でも 0 件 (対照にならない; on の deferred は 2〜94)。on の deferred が多いのは検証用の `readPixels` が worker を GPU 同期で止めて読出しが遅れるため (検証ハーネス由来)。
- **修正前の欠陥と経路 (レビュー指摘 A)**: 修正前 (`96cf00b`) の WebGL2 は `stable()` の中で `texSubImage2D` していた。**読み始めた後・検証の前に guest が書込みを始める**と (`seqRetries` に計上) 検証は失敗して矩形を持ち越すが、テクスチャには旧フレームと新フレームの行が混在したまま残り、`ingest()` は転送の成否によらず `drawRects` に入れたので次の rAF commit がその混在テクスチャを描画した (4 ms 後の再試行が先に直せば表に出ない = 確率的)。レビュー実測では on でも forced=0 のまま tear 発生 1 件 (19 run 中 1 run)。修正後は staging へコピー → 検証 → 成功時のみ転送とし、持ち越した矩形は `drawRects` に入れず再試行が成功してから描く (その間は直前の整合フレームが見える)。**「seqlock 決定的 (書込み中)」は検証の前から奇数の経路しか通らない**ので、この経路は「検証中の書込み開始」の決定的テストと確率的 tearing 試験で見る。direct 転送 (共有メモリ view を直接 `texSubImage2D`) の利点は seqlock 有効時のみ失われる (staging へのコピーが 1 回入る)。
- 設計判断: rAF 同期は **ingest (FRAME_END 時点で surface を読む) と commit (rAF で画面反映 + ack) の分離**にした。当初の「FRAME_END を rAF まで遅延して読む」実装は読出しが次フレームの guest 書込みと重なり、CPU 経路 (seqlock off) でも tear 状態の flush が 87 回中 19 回出た。分離後は 86〜87 回中 0 回 (3 run)。

### frame time (headless Chrome 154.0.8037.97, **SwiftShader = 実 GPU ではない**, 4 CPU)
`ms/frame`: flush(submit) = worker 内 CPU 時間 (`GuiRenderer.stats.flushMs / flushes`: 読出し・変換・転送・描画発行); +GPU sync = flush + 1 px `readPixels` による GPU 完了待ち; wall = guest の PRESENT push → ack。各セル = 60 frame × 3 rep × 3 run の **min–max** (n=9)。load average (1 分) は run 開始→終了で 0.68→1.71 / 1.71→2.60 / 2.40→2.63。
| size | dirty | 方式 | flush(submit) | +GPU sync | wall | rect/frame |
|---|---|---|---|---|---|---|
| 1280×720 | 全面 | CPU putImageData | 2.09–2.13 | — | 2.16–2.21 | 1 |
| 1280×720 | 全面 | WebGL2 direct | 0.35–0.58 | 5.67–8.21 | 6.99–9.96 | 1 |
| 1280×720 | 25% | CPU / WebGL2 direct | 0.54–0.56 / 0.07–0.15 | — / 1.74–2.68 | 0.58–0.63 / 1.11–2.54 | 1 |
| 1280×720 | 8 矩形 (128×72) | CPU / WebGL2 direct | 0.19–0.20 / 0.06–0.07 | — / 0.81–1.59 | 0.22–0.27 / 0.11–0.97 | 8 |
| 1920×1080 | 全面 | CPU putImageData | 4.72–4.85 | — | 4.90–5.04 | 1 |
| 1920×1080 | 全面 | WebGL2 direct | 0.75–1.00 | 12.67–13.05 | 17.51–18.25 | 1 |
| 1920×1080 | 全面 | WebGL2 staged | 1.51–1.70 | 13.29–13.52 | 18.16–18.76 | 1 |
| 1920×1080 | 25% | CPU / WebGL2 direct | 1.19–1.35 / 0.29–0.64 | — / 3.70–6.71 | 1.26–1.54 / 0.60–7.68 | 1 |
| 1920×1080 | 64×64 | CPU / WebGL2 direct | 0.01–0.02 / 0.01–0.03 | — / 0.32–0.41 | 0.04–0.06 / 0.05–0.06 | 1 |
| 1920×1080 | 8 矩形 (128×72) | CPU / WebGL2 direct | 0.19–0.20 / 0.04–0.08 | — / 1.37–1.47 | 0.22–0.26 / 0.10–0.17 | 8 |
- 全 24 セル (2 サイズ × 4 dirty × 3 方式: CPU / WebGL2 direct / WebGL2 staged) の完全表は `present_e2e.mjs` の出力 (`bash tools/gui/present/e2e.sh`)。
- **解釈**: GL 経路は worker の CPU 時間 (flush) を CPU 経路の 1/2〜1/6 に減らす (1080p 全面 4.72–4.85→0.75–1.00 ms、1080p 25% 1.19–1.35→0.29–0.64 ms)。一方 SwiftShader では GPU 完了まで 12.7–13.1 ms かかり CPU 経路より遅い (ソフトウェア GL がテクスチャ転送と quad 描画を CPU で行うため)。**実 GPU での完了時間・消費電力・合成コストは未測**で、GUI-4 の「必要性を実測で判断」は実 GPU ブラウザ + 実 FL 負荷が要る。`direct` (共有メモリ view を直接 `texSubImage2D`) は Chrome 154 で許容され、`staged` (行コピー) より全面更新の flush が 0.3〜0.9 ms 小さい。他ブラウザで拒否された場合は `staged` に自動降格 (コード上; 他ブラウザでは未検証)。
- 従来 CPU 経路の数値 (1080p 全面 4.72–4.85 ms) は §3 の旧実測 (2.2〜3.8 ms) と異なる: §3 は別環境・合成画像の変換ループ計測で、本表は `GuiRenderer` の flush を CI runner (4 CPU, load 0.7〜2.6) で測ったもの。両者は直接比較しない。

### 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine 負荷 (全面再描画 + 多数 BitBlt) での frame time / 入力→表示レイテンシ | #180 完了条件の「実 FLEngine 負荷」「実 GPU の frame time 比較表」が未達 | #180 (Refs のまま open) / GUI-3 (#174) 後 |
| 実 GPU での比較 (SwiftShader のみ) | GL 化の採否判断ができない | #180 に実 GPU ブラウザでの計測を追記 (headed Chrome か実機; ユーザ依頼候補) |
| shim の dirty は surface あたり単一外接矩形のまま (host は複数 PRESENT を併合して扱える) | 離れた小領域が多い描画で転送が増える | #180 (shim 側 `g_dirty` を矩形リスト化; 要 selftest 追加) |
| seqlock は検出と再試行 (back buffer なし) | guest が連続描画だと `staleMs` (100 ms) 後に tear を許容 | #180 (surface の double buffer 化) |
| 入力→表示レイテンシ・rAF 同期の 30fps 目標 (#10) の実 FL 計測 | 同上 | #180 / #10 |
| `tools/gui/e2e.sh` 6e/6 sigprobe の `unresolved-imports=0` は **runner に `wasm-objdump` (wabt) が無く `|| true` で常に 0 になる** (本 run の出力に `wasm-objdump: command not found`)。`signature mismatch=0` と陰性対照 `mismatch=177` は有効 | 「未解決 import なし」の確認が空振り (既存の挙動; 本変更とは無関係) | #180 にコメント (runner image へ wabt を足す、または不在時に fail させる) |
| dirty 内の前面 surface 再描画が surface id 順で z 昇順ではない (`present()` / `glDrawRects()`; レビュー軽微 1) | 前面側が 2 枚以上重なると z の小さい方が上に描かれ得る (golden のシナリオでは顕在化しない; ブラウザ再現は未確認) | #180 にコメント済み (issuecomment-6136756050) |
| `bash tools/gui/e2e.sh` 0/6 の `gen_api.py` が `tools/gui/IMPORTS.md` の先頭の「自動生成・人手編集禁止」ヘッダを落として書き換える (本 run では diff を commit せず元へ戻した) | e2e を回すたびに作業ツリーが dirty になる (既存の挙動) | #180 にコメント (生成元の `gen_api.py` がヘッダを出すようにする) |
| **既存の不安定**: native `selftest` (ASan) が `gui_headless.c:blit_surf` で heap-use-after-free することがある (render thread が `surf_free` 済みの画素を読む)。変更前の `origin/main` で 3/20、本変更後 3/14 回が exit 1 (同一スタック) | `tools/gui/e2e.sh` 1/6 が 15〜21% (3/20・3/14) で FAIL しうる (本変更とは無関係) | **#489 `[GUI-12]`** (headless host の render thread と shim の free の競合; 本 run で起票) |
- 範囲: FL 非依存の模擬 guest・headless Chrome 154 のみ。Firefox / Safari、複数 `canvas`、WebGL コンテキストロスト復帰 (コードあり・未試験) は範囲外。

### 再現
```
bash tools/gui/present/e2e.sh                      # tsc → mergeRects 単体 → golden/screenshot/seqlock/tearing/bench (bench 込み 44.4–44.8 s, 3 run, `09e3db9`; PRESENT_SKIP_BENCH=1 で bench 省略 9.6–11.2 s, 30 run, `88efd49`, load 0.34–3.44)
bash tools/gui/test/selftest.sh                    # native 319 assertion (seqlock wseq の 5 件を追加)
node tools/runtime/gui_e2e.mjs                     # Vite バンドル経由 (本番 worker) で WebGL2+rAF+seqlock の render-selftest を追加
bash tools/gui/e2e.sh                              # 全体 (PE lift を含む); 要 RetDec・emsdk・mingw
```

## 15. GUI-5 (#181) 続き: e2e.sh 全体と wasm shim 全体の SIMD/scalar 比較

既知類型との関係: lift 欠陥ではなく shim の意味論 (§10 の同一サーフェス複数クリップ欠陥は `docs/DEFECTS.md` D18 に登録)。
検証起点: 現 HEAD `e11701db` (main `c5df4657` 取り込み後、`tools/gui/src`・`include` は main と同一)。本節の測定値は全て `e11701db` の実測。`b44ddcd`・`ea7a538` 等の旧 HEAD の値は直前の試行として試行表に残す。runner 4 CPU、`[EMSDK]`・`[RETDEC]`、mingw-w64 GCC 13 (apt `gcc-mingw-w64-x86-64`)。emcc は `[EMSDK]` の `upstream/emscripten`・`upstream/bin` と node `24.19.0_64bit` を PATH に直接指定 (`emsdk_env.sh` が emcc を PATH に出さないため)。`fl-win64` は本 run で不要 (e2e の step 3 は `test/gui_app.c` を使う)。

### 1. `bash tools/gui/e2e.sh` (RetDec 付き・全層)

| HEAD | 試行 | 実行者 | rc | 所要 | load (開始→終了) | 1/6 selftest | ASan UAF |
|---|---|---|---|---|---|---|---|
| `e11701db` | **現 HEAD (本節)** | 本 run (fix モード) | **0** | **188 s** | 0.55 → 2.70 | 428 passed / 0 failed | 0 件 |
| `e11701db` | selftest 単体 20 回連続 | 本 run | 0 (20/20) | 256 s (1 回約 13 s) | 1.91 → 1.49 | 428 passed / 0 failed (20 回) | 0 件 (20 回) |
| `b44ddcd` | 直前の試行 | 本 run (前回) | 0 | 99 s | 0.75 → 1.11 | 428 passed | 0 件 |
| `b44ddcd` | (修正前 `a440fe9` の 6f/6 が rc=1) | 本 run (前回) | 1 | 27 s / 109 s | — | 1c0/6 通過。6f/6 の `node --test` 集計 grep が 0 行で rc=1 → `b44ddcd` で修正 | — |
| `1457db3` | T1 | bot (PR コメント) | 1 | 15 s | — | 1/6 で ASan heap-use-after-free | **発火** |
| `1457db3` | T2 | bot (PR コメント) | 0 | 189 s | — → 2.13 | 426 passed | 0 |
| `1457db3` | R1 | レビュワー独立 | — | — | — | 426 passed (5/6 は検証用 worktree の `node_modules` 不在で停止。不計上) | 0 |
| `1457db3` | R2 | レビュワー独立 | 1 | — | — | 1/6 で ASan heap-use-after-free (`gui_headless.c:33 blit_surf` ↔ `gui_core.c:177 surf_free`) | **発火** |
| `1f20ec7` | run1 | 検証 subagent | 0 | 173 s | 0.11 → 1.71 | 426 passed | 0 |
| `1f20ec7` | run2 | 検証 subagent | 0 | 102 s | 1.33 → 1.44 | 426 passed | 0 |
| `ea7a538` | run3 | 検証 subagent | 0 | 104 s | 2.81 → 2.18 | 428 passed | 0 |

- **結論**: 現 HEAD `e11701db` で rc=0・ALL PASS (1 回)。1/6 の selftest は 428 passed / 0 failed、ASan UAF は 0 件。
- **#489 の扱い (修正後の判定)**: `4f303d4` (#622, #489 修正) を取り込んだ `e11701db` で、selftest 単体を 20 回連続実行して 20/20 PASS・ASan 0 件。修正前 (`1457db3` 系の src、#489 修正なし) では 1/6 に到達した有効 7 回中 2 回 (T1・R2) が ASan UAF で rc=1 だった。修正後は同 HEAD の selftest 20 回連続 + e2e 全体 1 回で発火 0 件。20 回の結果は修正前の発火率と比べて有意な差を示すが、1 回ごとの確率事象であるため「解消の証明」ではない。受入判断 (#489 の検収) は PM に任せる。
- 試行数: 1/6 に到達した有効試行は、修正前 7 回 (T1・T2・R1・R2・run1・run2・run3) で ASan UAF は 2 回 (T1・R2)。修正後 (`e11701db`) は selftest 単体 20 回 + e2e 全体 1 回で 0 回。
- 層ごとの結果 (`e11701db`、`e2e.sh` の標準出力より):

| 層 | 結果 (`e11701db`) |
|---|---|
| 1/6 selftest (ASan/UBSan) | 428 passed / 0 failed (ASan 0 件) |
| 1b/6 bpp golden | EXACT MATCH (16,000 px, 0 diff)。negctl 2/2 OK |
| 1c0/6 FreeType テキスト | text golden ALL PASS (negctl 4/4 OK)。native == wasm32 / wasm64 |
| 1d/6 NC golden | asserts 26 passed / 0 failed。EXACT MATCH (28,000 px, 0 diff)。negctl 3/3 OK |
| 2/6 native lift (PE→RetDec→gcc) | golden EXACT MATCH 0 / 64,000 px |
| 2b/6 reach / adapt | 11 passed / 28 passed |
| 1c/6 SIMD == scalar | 15,679 ケース不一致 0。故意欠陥 `GS_FAULT=1〜4` は 1,632 / 271 / 252 / 268 件で FAIL。v128 系命令 simd=1,074 / `-DGUI_NO_SIMD` 0 |
| 4b/6 GUI-13 ブラウザ text e2e | 8x8 回帰 0 px、negctl N1〜N5 全て拒否 (PASS) |
| 6/6 Chrome (固定 memory) | OffscreenCanvas readback・screenshot とも EXACT MATCH (0 px) |
| 6b/6 Chrome (ALLOW_MEMORY_GROWTH) | 同上 EXACT MATCH (0 px) |
| 6c/6 fail-fast | OK (EXIT 0xfa11、API 名を console に出力) |
| 6d/6 reach-log | OK: 36 APIs (reached=36 impl=36 stub=0) |
| 6e/6 sigprobe | signature mismatch=0 (陰性対照 177)。`unresolved-imports=0` は `wasm-objdump` 不在で空振り (#180) |
| 6f/6 present e2e | ALL PASS (load 2.76 → 2.70) |

### 2. wasm 全体 (shim の API 単位) の SIMD128 / scalar: `bash tools/gui/test/wbench.sh 5`

`e11701db` で 1 回 (rc=0, 20 s, load 1.91 → 2.67)。同一 `test/bench.c` を `-msimd128` / `-DGUI_NO_SIMD` で emcc ビルドし交互に 5 回ずつ (n=5, min–max ms/frame, 1920x1080, node v24.19.0)。最終 wasm の v128 系命令は simd=831 / scalar=0 (取り違えは exit 1)。`min 比` = scalar の最小 / simd の最小。

| API | scalar | simd128 | min 比 |
|---|---|---|---|
| BitBlt SRCCOPY mem→mem (memmove) | 2.97–4.00 | 3.00–3.70 | 0.99x |
| BitBlt SRCCOPY mem→window | 0.30–0.37 | 0.33–0.33 | 0.91x |
| BitBlt SRCINVERT (per-pixel) | 3.27–3.33 | 0.47–0.53 | 6.96x |
| StretchBlt 2x nearest | 1.60–1.63 | 0.57–0.60 | 2.81x |
| StretchDIBits 1:1 (per-pixel) | 1.20–1.27 | 0.43–0.53 | 2.79x |
| AlphaBlend per-pixel α (sca=128) | 14.77–14.87 | 3.23–3.50 | 4.57x |
| AlphaBlend 定数 α (sca=128) | 14.67–15.07 | 2.93–2.97 | 5.01x |
| BitBlt SRCPAINT (per-pixel) | 3.90–4.03 | 0.43–0.43 | 9.07x |
| StretchDIBits 24bpp 1:1 | 2.67–2.83 | 2.27–2.33 | 1.18x |
| StretchDIBits 8bpp 1:1 | 2.13–2.20 | 1.50–1.50 | 1.42x |
| BitBlt SRCCOPY from 24bpp DIB section | 2.07–2.27 | 2.37–2.50 | 0.87x |
| BitBlt SRCCOPY into 24bpp DIB section | 3.73–3.80 | 4.33–4.37 | 0.86x |
| FillRect solid | 0.40–0.43 | 0.27–0.30 | 1.48x |
| BitBlt → window + present (headless) | 0.30–0.37 | 0.33–0.37 | 0.91x |

- SRCCOPY・24bpp 先・DIB 源・present の行は SIMD の対象外か pull/push が支配的で、1.0x 付近 (範囲が重なる誤差内)。24bpp 先・24bpp DIB 源は 0.86x〜0.91x で SIMD が負けている。
- 1 回の測定のため、min 比の小数第 2 位は揺れる。AlphaBlend の値は実行ごとに 4.6x〜9.5x と揺れる (`b44ddcd` 時の 3.87x〜4.01x とは別の測定)。
- 画素一致は §10 と本付録 §1 の 1c/6 が担い、本 bench は時間のみ。
- **未取得**: Chrome 上の lift 済みアプリでの API 単位 frame time。`gui_app.c` は 320x200 の静的シーンで、e2e の bench は renderer 側 (変換 + putImageData) のみを測るため shim の時間を分離できない。実 FL (#174) 到達後に取る。

### 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正後 `e2e.sh` 全体の連続試行 (現在 1 回) | 1/6 の ASan UAF が全体 run で再発しないことは 1 回のみ確認 | #489 `[GUI-12]` (既存)・PM |
| `integ/sigprobe.sh` の `unresolved-imports` が `wasm-objdump` (WABT) 不在で空振り | 「未解決 import なし」の検査が無効 (`mismatch=0` と陰性対照は有効) | #180 (既存コメント) |
| Chrome 上の lift 済みアプリの API 単位 frame time | 未取得 | #181 → 実 FL (#174) 到達後 |

### 4. 再現

```
bash tools/gui/e2e.sh             # 全層 (e11701db: 188 s)。前提: x86_64-w64-mingw32-gcc、RetDec ([RETDEC])、emsdk ([EMSDK]; emcc を PATH に)、node_modules (pnpm install)
bash tools/gui/test/wbench.sh 5   # wasm SIMD/scalar の API 単位比較 (e11701db: 20 s)
bash tools/gui/test/selftest.sh   # 1/6 単体 (e11701db: 1 回約 13 s、20 回連続 20/20 PASS)
```
