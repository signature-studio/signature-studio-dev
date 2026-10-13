# REPORT 付録 — B: gui-shim §9 / §10 全文

> 正本は [REPORT.md](REPORT.md)。`REPORT.md` の 250 行上限のため §9 (GUI-4 #180) と §10 (GUI-5 #181) を無変更で分割移動した (#183 / PR #605)。節番号は REPORT.md と共通。

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

## 10. GUI-5 (#181): 24/8/4/1bpp DIB・mono DDB と wasm SIMD128 行カーネル
既知類型との関係: lift 欠陥ではなく shim の意味論 (`docs/DEFECTS.md` D1a〜D16 に該当なし)。ただし shim 自身の silent 誤りを 1 件発見 (下記「発見」)。検証起点: 実装 `dd7be3e`、本節の数値は `9cff72c` のクリーン tree での実測 (src/test は最終 HEAD と同一で、以降の commit は REPORT・DOC_MAP のみ; `gui_gdi.c` は `dd7be3e` と同一)。

### 結論
- **機能欠落 (スコープ 1) は FL 非依存の範囲で解消**: `CreateDIBSection` の 1/4/8/24bpp (app から見えるネイティブ形式 `nat` と内部 BGRA shadow を pull/push で同期; 仕様 [PROTOCOL.md §8](PROTOCOL.md))・`CreateBitmap` の mono(1bpp)/24/32bpp・`StretchDIBits`/`SetDIBitsToDevice`/`SetDIBits`/`CreateDIBitmap`/`LoadBitmapW` の 1/4/8/24/32bpp 源・`GetDIBits` の 1/4/8/24/32bpp 出力・`GetDIBColorTable`/`SetDIBColorTable` (IMPORTS: STUB→IMPL, 実装 270→272)・mono↔color 転送の bk/text 色写像・`MERGEPAINT`。未対応は理由付き fail-fast (16bpp DIB / DIB_PAL_COLORS / 圧縮 / `CreateBitmap` 4,8,16bpp の初期 bits)。
- **SIMD 化 (スコープ 2)**: `src/gui_simd.h` の行カーネル (ROP 15 種・AlphaBlend 定数/per-pixel alpha・不透明化コピー・2x 水平拡大) を wasm SIMD128 と scalar 参照で持ち、`BitBlt`/`StretchBlt`/`StretchDIBits`/`AlphaBlend` が使う。拡縮は x 写像を転送ごとに 1 回計算 (画素ごとの 64bit 除算を排除)。`lift/gui_wasm.sh` は既定 `-msimd128` (`GUI_NO_SIMD=1` で scalar)。
- **受入条件は未達 → PR は `Refs #181`**: (a) `bash tools/gui/e2e.sh` の ALL PASS は runner に RetDec (`toolchain-retdec`) が無く PE lift 層 (2/6・3/6・4/6・6/6〜6d) を実行できず**未確認**、(b) issue の保留理由 (FLEngine が実際に要求する bpp/ROP を GUI-3 #174 の到達ログで確定) は未充足、(c) Chrome 上で SIMD 版 wasm 全体 (lift 済みアプリ込み) を走らせていない (SIMD は kernel 単位で node 検証)。

### 検証 (全て `9cff72c` のクリーン tree、runner 4 CPU、`uptime` load 0.5〜1.4)
| 層 | 結果 | 陰性対照 |
|---|---|---|
| native `selftest` (ASan/UBSan) | **378 passed / 0 failed** (319 → 378: +59 assertion)。各 bpp の native↔shadow 往復 (24bpp 行 4B 境界・bottom-up/top-down・8bpp 最近傍/重複色 index 保持/SetDIBColorTable・4bpp nibble・1bpp MSB 先頭)・各 bpp 源の StretchDIBits・GetDIBits/SetDIBits・mono 色写像・fail-fast 5 件 | fail-fast 5 件は `SIGABRT` + API 名/理由の文字列を検査 (出力を EOF まで読む) |
| 行カーネル版 == 画素単位参照 (`gdi_set_ref_blit`) | ROP 15 種 × 幾何 (1:1・2x・任意比・水平/垂直反転) × クリップ (なし/矩形/穴/複数穴) × 同一サーフェス重複: **4,500 ケース (うち同一サーフェス 642) で不一致 0**。各 ROP 300 ケース。同一サーフェスは「転送元を事前コピーした別サーフェスから転送した結果」とも一致 | 別 ROP・別オフセットで実行した結果は参照と不一致 (90 プローブ中 76 で検出) |
| AlphaBlend 独立オラクル (テスト内に直書き `(x+127)/255` 丸め) | 60 ランダムケース (定数 α/per-pixel α・1:1/拡縮・端のはみ出し) で不一致 0。`gs_div255(x)==(x+127)/255` を x∈[0,65025] 全件確認 | sca=101 の結果を sca=100 のオラクルと比較 → 不一致を検出 (+ 同条件 sca=100 は一致の陽性対照) |
| **golden** (`bash tools/gui/test/bpp_golden.sh`): 24/8/4/1bpp StretchDIBits + 24/8bpp DIB section (native 直書き + GDI FillRect/LineTo → BitBlt) + mono + SRCINVERT 2x + AlphaBlend の 160×100 シーンを独立 Python オラクル `golden/gen_golden_bpp.py` (shim と共有するのはパターン式のみ) と比較 | **16,000 px 差 0 (EXACT MATCH)** | 期待値を 1 画素壊す → 不一致で拒否 / shim 側に故意の欠陥 (パレット index 2 の色差し替え) → **40 px 不一致で拒否** (どちらかが通ると script が exit 1) |
| wasm SIMD128 (`bash tools/gui/test/simd_e2e.sh`, emcc 6.0.12 + node v22.23.3) | SIMD == scalar: ROP 15 種 × 長さ 0..70 × アライメント 0..3、α 全 256 値 × 2 方式、不透明化コピー・2x 拡大の端数、1080p 1 行 (1920 px): **15,679 ケース不一致 0**。`gui_gdi.c` を `-msimd128` で wasm 化すると v128 系命令 1,020 / `-DGUI_NO_SIMD` で 0 (SIMD 経路が実際に入る) | SIMD 無効ビルドの simd_test は exit 2 で拒否 (scalar 同士の比較で PASS しない) / 故意の欠陥 4 種 (`-DGS_FAULT=1..4`: div255 丸め・SRCINVERT→OR・shuffle 誤り・OR 落ち) は全て FAIL (不一致 1,632 / 271 / 252 / 268) |
| 既存層 | `reach_test` 11 passed・`adapt_test` 28 passed・改名 selftest 378 passed (`test/reach_test.sh`)、`tsc -p tools/gui/tsconfig.json` rc 0、`sigprobe` signature mismatch=0 (陰性対照 177)、present e2e (`PRESENT_SKIP_BENCH=1`) 7 pass / 0 fail ALL PASS (18.8 s) | — |
| **未実行** | `bash tools/gui/e2e.sh` の PE lift 層 (RetDec 不在)。`e2e.sh` に 1b/6 (bpp golden)・1c/6 (SIMD) を追加済みだが全体の ALL PASS は未確認 | — |
- **origin/main (`d1ff878`; #172 shimx・#118 等) との merge 後 `04dd71e`**: `selftest` 406 passed / 0 failed (3 回連続; main 側の `selftest_fd.inc` +28 を含む)・`bpp_golden` EXACT MATCH 16,000 px・`simd_e2e` ALL PASS・`reach_test` 11/28 passed・改名 selftest 406 passed・`tsc` rc 0 を再確認。
- 再現 1 コマンド: `bash tools/gui/test/selftest.sh` / `bash tools/gui/test/bpp_golden.sh` / `bash tools/gui/test/simd_e2e.sh` (bench は `BENCH=0` で省略。上記 3 本 + reach_test の合計 44.0 s, load 1.05)。
- **既存の不安定 (本変更と無関係)**: native `selftest` は ASan で `gui_headless.c:blit_surf` の heap-use-after-free で 20 回中 4 回 (20%) exit 1 (全て同一スタック; §9 の #489)。それ以外の失敗は 0。

### 性能 (1080p, 参考値; 実 FL 負荷・実ブラウザは未測)
native `-O2` gcc 13 (`bash tools/gui/test/bench.sh 5 [旧 tools/gui のパス]`; 前 = `17b7777` の src に同じ bench.c を適用, 後 = 最終; 各 n=5 の min–max ms/frame, load 0.5〜0.6; native は wasm SIMD が使えないため行ループ化・除算排除の効果のみ):
| API | 前 | 後 | min 比 |
|---|---|---|---|
| BitBlt SRCINVERT | 7.17–7.30 | 2.60–2.67 | 2.76x |
| BitBlt SRCPAINT | 7.17–7.30 | 2.63–2.87 | 2.73x |
| StretchBlt 2x nearest | 7.20–7.83 | 1.90–1.97 | 3.79x |
| StretchDIBits 32bpp 1:1 | 7.20–7.63 | 0.70–0.73 | 10.29x |
| AlphaBlend per-pixel α | 18.97–19.13 | 14.73–15.17 | 1.29x |
| AlphaBlend 定数 α | 18.13–18.80 | 15.77–16.07 | 1.15x |
| StretchDIBits 24bpp 1:1 / 8bpp 1:1 | fail-fast | 2.10–2.13 / 1.40–1.43 | — |
| BitBlt SRCCOPY 24bpp DIB section → 32bpp / 逆向き | fail-fast | 1.90–2.20 / 3.57–4.37 | — |

wasm 行カーネル (node, 各 n=5 の min–max ms/frame; scalar = `-msimd128` なしの同一ソース):
| カーネル | scalar | SIMD128 | min 比 |
|---|---|---|---|
| ROP SRCINVERT | 2.122–2.466 | 0.751–0.892 | 2.83x |
| ROP PATPAINT | 2.149–2.193 | 0.772–1.078 | 2.78x |
| AlphaBlend 定数 α | 12.745–12.838 | 2.942–3.309 | 4.33x |
| AlphaBlend per-pixel α | 18.476–18.745 | 4.260–4.321 | 4.34x |
| StretchDIBits 1:1 (不透明化コピー) | 1.550–1.754 | 0.627–0.661 | 2.47x |
| StretchBlt 2x の水平拡大行 | 1.301–1.430 | 0.566–0.583 | 2.30x |
- 数え方: 行カーネルだけの時間 (clip・xmap・pull/push・dirty は含まない; 全 API の wasm 計測は Chrome 上の lift 済みアプリが要るため未実施)。AlphaBlend の native 改善が小さい (1.15〜1.29x) のは native に SIMD 経路が無く整数演算が支配的なため。
- 24bpp 以下の DIB section は GDI 操作ごとに pull/push (矩形限定) が入る分、32bpp より遅い (BitBlt 先が 24bpp で 3.57–4.37 ms)。

### 発見・限界
- **発見 (shim の silent 誤り・本 PR で修正)**: 同一サーフェス BitBlt でクリップが複数矩形のとき、旧実装は先行矩形の書込みを後続矩形が転送元として読む (穴あきクリップで画素が源と異なる; 旧画素単位実装で 642 ケース中 32 件を再現)。本 PR は転送元矩形の事前コピーで修正。`docs/DEFECTS.md` 形式の行案: 症状 = スクロール/コピーで穴の周りの画素が壊れる / 根本原因 = クリップ矩形ごとに全行を処理し先行矩形の結果を源として読む / 検出信号 = 事前コピー転送との画素比較 / 修復 = 源矩形のスナップショット (DEFECTS.md の直接編集は PM 判断)。
- 近似: mono への color 書込み (輝度 ≥128 を白)、`GetDIBits` の ≤8bpp 既定色表 (決定論的な 1bpp 黒白/4bpp VGA16/8bpp 3-3-2; 実 Windows の DDB パレットとは異なる)、≤8bpp への書込みは最近傍 (距離関数は RGB 二乗距離で、実 Windows との照合は未実施)。

### 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `bash tools/gui/e2e.sh` 全体 ALL PASS の確認 (RetDec 不在で PE lift 層が未実行) | 完了条件 (e2e ALL PASS 維持) 未確認 → `Refs #181` | #181 に `oc_artifacts: toolchain-emsdk toolchain-retdec` で再実行を依頼 (mingw-w64 は apt `gcc-mingw-w64-x86-64` で入った) |
| 実 FLEngine が要求する bpp/ROP の確定 (GUI-3 #174 の到達ログ待ち)・16bpp DIB・DIB_PAL_COLORS・`CreateBitmap` 4/8/16bpp の初期 bits・RLE/JPEG/PNG 圧縮 DIB | 実 FL が要求したら fail-fast で止まる (理由付き) | #174 到達後に #181 へ追記 |
| Chrome 上の SIMD 版 wasm 全体 (lift 済みアプリ込み) の frame time | wasm の API 単位の前後比較が未取得 (kernel 単位のみ) | #181 (RetDec 付き再実行で `gui_wasm.sh` 既定の `-msimd128` ビルドを実測) |
| mono / パレットの色写像の実 Windows との照合 (近似) | 色が実機と数階調ずれる可能性 | #181 (実機比較はユーザ依頼候補) |
| native selftest の ASan UAF (20 回中 4 回) | `e2e.sh` 1/6 が約 20% で FAIL | #489 `[GUI-12]` (既存) |
| `integ/sigprobe.sh` の `unresolved-imports=0` が `wasm-objdump` 不在で空振り (今回も `command not found`) | 未解決 import なし確認が無効 | #180 (既存コメント) |
