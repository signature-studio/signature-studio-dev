# gui REPORT 付録 — §9 GUI-4 (#180) 全文・§14 GUI-6 (#182) 全文

REPORT.md の 250 行上限のため §9 を無変更で分割移動 (#489 の §12 追加時)。本体: [REPORT.md](REPORT.md)。

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


## 14. GUI-6 (#182): 入力品質 (キー配列 / IME / タッチ・ジェスチャ / Pointer Lock・ClipCursor)
既知類型との関係: lift 欠陥ではなく shim/host の意味論 (`docs/DEFECTS.md` D1a〜D16 に該当なし)。検証起点: 実装コミットは `8dd9457`、本 run の差分 (B2・推奨修正) は後続コミット (下記の数値はコミット済み tree で実測)。

### 結論
- **FL 非依存で CDP 再現できる範囲を実装し e2e 済み。受入条件は未達 → PR は `Refs #182`** (理由は「範囲外・未達」: `bash tools/gui/e2e.sh` 全体の ALL PASS は RetDec 不在で PE lift 層が走らず未確認、WM_POINTER*、実機確認)。
- **キー配列**: 入力 `GUI_IN_KEY_*` の flags に host が set 1 スキャンコード/extended を載せ (`SCAN_BY_CODE`)、shim が現配列で scancode→VK を引く (`kbd_layout_vk`)。`GUI_IN_LAYOUT` で US(0x0409)/DE(0x0407)/FR(0x040C) を切替え、`MapVirtualKeyW` (VK↔VSC/VSC→VK/VK→CHAR)・`ToUnicode`/`ToAscii` (Shift/Caps/AltGr=Ctrl+Alt)・`GetKeyboardLayout`/`GetKeyboardLayoutNameW`/`LoadKeyboardLayoutW` (未対応 KLID は 0 で失敗)/`ActivateKeyboardLayout` が配列に従う。host は Keyboard API の `getLayoutMap` から自動推定 (`layoutFromMap`)。
- **IME**: 隠し textarea の composition イベント → `GUI_IN_IME` (4 UTF-16/レコードで連結) → `WM_IME_STARTCOMPOSITION`/`WM_IME_COMPOSITION` (GCS_COMPSTR|GCS_CURSORPOS / GCS_RESULTSTR)/`WM_IME_ENDCOMPOSITION`。imm32 は `ImmGetContext`/`ReleaseContext`/`GetCompositionStringW`/`SetCompositionWindow`/`SetCandidateWindow` (位置を host へ `GUI_CMD_IME_POS`)/`Get/SetOpenStatus`/`Get/SetConversionStatus`/`NotifyIME`/`IsIME`/`AssociateContextEx` を実装 (計 12 名)。このうち FL の import 表 (IMPORTS.md) で STUB→IMPL になったのは 7 名 (`ImmAssociateContextEx`・`ImmGetContext`・`ImmGetConversionStatus`・`ImmReleaseContext`・`ImmSetConversionStatus`・`ImmSetOpenStatus`・`ImmIsIME`)。残り 5 名 (`ImmGetCompositionStringW`・`ImmSetCompositionWindow`・`ImmSetCandidateWindow`・`ImmNotifyIME`・`ImmGetOpenStatus`) は FL の import 表に無く、IMPORTS.md 上は変化しない。composition 中の入力から WM_CHAR は合成しない。
- **タッチ**: `PointerEvent(pointerType=touch)` → `GUI_IN_TOUCH`。`RegisterTouchWindow` 済み窓へ `WM_TOUCH` (`GetTouchInputInfo` = Win64 TOUCHINPUT 48B)、未登録窓は primary 接触をマウスへ昇格。`SetGestureConfig` (MS 仕様の符号化: `{dwID=GID, dwWant=GC_*, dwBlock}`。`{0, GC_ALLGESTURES, 0}` = 全ジェスチャ有効、`{GID_ZOOM=3, GC_ZOOM=1, 0}` = ZOOM のみ) で許可した GID_ZOOM (2 本指距離) を `WM_GESTURE` (`GetGestureInfo` = Win64 GESTUREINFO 56B) で配送。GID_PAN (1 本指移動) も実装しているが、**selftest / e2e に検査が無く未検証**。
- **Pointer Lock / ClipCursor**: 「カーソル非表示 (`ShowCursor(FALSE)`) かつ capture 中またはボタン押下中」に `GUI_CMD_POINTER_LOCK` で host へ `requestPointerLock` を要求 (要求の発行は selftest で push 数 1/1/0 を検査)。ロック中 host は `movementX/Y` を `cursor_x/y` へ積算 (ClipCursor 矩形へ clamp)。`SetCursorPos` は ClipCursor 矩形へ clamp、`GetClipCursor` は矩形を返す。
- **ブラウザ既定動作の変更 (限定済み)**: `RegisterTouchWindow` が 1 回以上成功すると shim が `GUI_CMD_TOUCH_WINDOWS` (w2 = 登録窓数) を送り、host (`src/runtime/gui.ts` の `touchwin`) は GUI canvas の `touch-action` を `none` にする。タッチを宣言していない GUI では `auto` のまま (ブラウザ既定のパン/ズームは変わらない)。canvas は 1 枚のため「窓ごと」ではなく「タッチ対応の窓が 1 つでもあるとき」の単位で限定している。実測は `tools/gui/input/e2e.sh` の `touch-action` 検査 (`none`)。
- プロトコル追加は enum 値のみ (`GuiShared` のオフセットは不変・`_Static_assert` 更新なし)。`gui_proto.h` ↔ `gui_proto.ts` を同時更新。
- FL の GUI import 面: 実装済み 280 → 292 (`IMPORTS.md` は `gen_api.py` が再生成)。IMPORTS.md の STUB→IMPL は 12 行 (imm32 7 + touch/gesture 5)。

### 検証 (4 vCPU runner、検証起点 `8dd9457`、実測時 load 0.8〜1.1)

- **HEAD `0b71ab1` の実測 (B2 修正後)**: `bash tools/gui/e2e.sh` 全体 **ALL PASS** (exit 0, real 1m36.108s; native selftest 493 passed / 0 failed、reach_test 11 / adapt_test 28 passed、6/6・6b/6・6c/6・6d/6・6e/6・6f/6 PASS、6g/6 入力 ALL PASS)。`tools/gui/input/e2e.sh` ALL PASS (in_pushed=41 in_dropped=0 in_consumed=41, real 3.773 s)。`tools/gui/input/negctl.sh` 12 件すべて検出・検出漏れ 0 (real 2 分 34.430 秒)。以下の表は旧検証起点 `8dd9457` のもの。
| 層 | 結果 |
|---|---|
| native `bash tools/gui/test/selftest.sh` (ASan/UBSan, `8dd9457`) | **492 passed / 0 failed** (既存 426 + GUI-6 の 66 assertion; `test/selftest_gui6.inc`)。DE/FR/US 配列・AltGr・IME 分割再構成・タッチ/ジェスチャ・ClipCursor・Pointer Lock 要求の push 数 (1/1/0)・DE/FR の MAPVK 英字大文字化を含む。所要 real 13.06 s |
| Chrome e2e `bash tools/gui/input/e2e.sh` (CDP `Input.dispatchKeyEvent` / `imeSetComposition` / `insertText` / `dispatchTouchEvent` / `dispatchMouseEvent`, `8dd9457`) | **ALL PASS (21 検査 / 0 FAIL)**。入力リング `in_pushed=41 in_dropped=0 in_consumed=41` (drop 0)。計測: 内部 1.5 s (load 1.12)、real 13.03 s (wasm 再ビルド込み)。ゲストは `input/input_app.c` を emcc で直接 wasm 化 (RetDec 不要) |
| 既存層 (`8dd9457` で再実測, load 0.8〜0.96) | `reach_test` 11 + `adapt_test` 28 passed (15.4 s)、`bpp_golden` EXACT MATCH 16,000 px・ネガコン 2/2 OK (6.4 s)、`simd_e2e` ALL PASS (14.3 s)、`present/e2e.sh` (`PRESENT_SKIP_BENCH=1`) 7 pass / 0 fail (10.0 s)、`check_p1_tests` 51 APIs / 51 実装・テスト付き (0.14 s) |
- ネガティブコントロール (下の「ネガコン実測」): `bash tools/gui/input/negctl.sh` (壊したコピーを `build/negctl` に作りリポジトリのソースは変更しない。変異が効かなければ「broken control」として未検出扱い)。
- 数え方: selftest の passed は `CHK` 成立数 (assertion)。Chrome e2e の検査は `ck()` 行数。

### ネガコン実測 (`bash tools/gui/input/negctl.sh`, 検証起点 `8dd9457`)
| 変異 (ソース 1 箇所を壊す) | 検出した層 | 結果 (passed / failed、または FAIL 件数) |
|---|---|---|
| nc1 物理キー → 現配列 VK 変換 (`kbd_layout_vk`) を無効化 | selftest | 492 passed / **1 failed** → 検出 |
| nc2 DE の Z/Y の配置を入替 | selftest | 488 passed / **5 failed** → 検出 |
| nc3 AltGr (Ctrl+Alt) の文字表を無視 | selftest | 490 passed / **3 failed** → 検出 |
| nc4 WM_IME_COMPOSITION の結果送信フラグを GCS_COMPSTR に変更 | selftest | 490 passed / **3 failed** → 検出 |
| nc5 ZOOM の接触数補正 (離す接触を数えない) を削除 | selftest | 492 passed / **1 failed** → 検出 |
| nc6 ClipCursor の clamp を無効化 | selftest | 492 passed / **1 failed** → 検出 |
| nc7 MAPVK_VK_TO_CHAR の英字大文字化を削除 (本 PR の B4 修正の逆) | selftest | 490 passed / **3 failed** → 検出 |
| nc8 POINTER_LOCK 要求の push を削除 (本 PR の B5 検査の対象) | selftest | 492 passed / **1 failed** → 検出 |
| host-1 KEY の scancode を flags から落とす (gui.ts) | Chrome e2e | exit 1 / **6 FAIL** → 検出 |
| host-2 IME update の送信を落とす (gui.ts) | Chrome e2e | exit 1 / **1 FAIL** → 検出 |
| host-3 touch 分岐を無効化 (touch→mouse 昇格が効かない) (gui.ts) | Chrome e2e | exit 1 / **6 FAIL** → 検出 |
| host-4 Pointer Lock 要求の発行を落とす (gui.ts) | Chrome e2e | exit 1 / **1 FAIL** → 検出 |

- 結果: shim 8 件 + host 4 件 = **12 件すべて検出、検出漏れ 0** (`[negctl] 合計 検出漏れ: 0`, exit 0)。所要 real 2 分 34.66 秒 (user 1 分 18.27 秒)。各変異は壊したコピー (`build/negctl`) で実行し、ソースは変更していない。

### 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
`bash tools/gui/e2e.sh` 全体は `0b71ab1` で ALL PASS (exit 0, real 1m36.108s; PE lift 層 2/6〜6g/6 を含む)。範囲外の残りは下記の行。
| WM_POINTER* / RegisterPointerInputTarget 系 (FL の import に無い) と慣性ジェスチャ (GID_PAN の GF_INERTIA)・GID_ROTATE/TWOFINGERTAP/PRESSANDTAP | issue スコープ「タッチ → WM_POINTER*」の一部が未実装 | #182 (実到達ログ: #174 で FL が呼ぶと確定したら) |
| GID_PAN (1 本指移動の WM_GESTURE) は実装のみで selftest / e2e に検査が無い | パン操作の回帰を検知できない | #182 (テスト追加は次の作業。PM 判断: 今回の PR で足すか) |
| 配列は US/DE/FR のみ・dead key・IME 配列・実 Windows の KBD テーブルとの照合なし (表は公開仕様から手作成)。Caps の数字行 shift-lock 近似 | 他配列では US 相当に落ちる。表の誤りは実機でしか見つからない | #182 (日本語 JIS/実機確認はユーザ依頼候補; 着手時に具体依頼を起票) |
| 実機確認 (OS の日本語 IME・実タッチ端末・実 Pointer Lock 成立) は未実施。headless Chrome では Pointer Lock は要求呼出回数と `movementX` 積算のみ検証 (ロック成立は `locked` を直接設定して代用) | 実環境での成立可否・IME 候補ウィンドウ位置が未確認 | #182 (ユーザ依頼: 実機 Chrome での手動確認) |
| `touch-action` は RegisterTouchWindow 済み窓がある場合のみ `none` (限定済み; 上記「ブラウザ既定動作」) | タッチ非対応の GUI では従来どおり | 解消 (本 PR) |
| `tools/gui/integ/sigprobe.sh` の未解決 import 検査は `wasm-objdump` (wabt) 不在で空振り (`|| true` により `unresolved-imports=0` を無検査で通す。main 既存) | 「未解決 import なし」の確認が無効 (`signature mismatch` の検査は有効) | #182 にコメント (runner に wabt を足す、または不在時に fail させる) |
| IME 属性/文節 (GCS_COMPATTR/COMPCLAUSE) と変換候補リスト (ImmGetCandidateList) は未提供 | FL が使えば fail-fast ではなく空を返す | #174 到達ログ後に #182 |
| WM_CHAR 合成は host (gui.ts `key()`) のまま (pump 側 TranslateMessage は未変更) | #103 の補足にある pump 側合成との統合は未決 | #121 (RT-3: 入力 producer 結線) と合わせて決定 |
| 既存: native selftest の ASan UAF flake | `e2e.sh` 1/6 が時々 FAIL | #489 (既存) |

### 再現
```
bash tools/gui/test/selftest.sh        # native 492 assertion
bash tools/gui/input/e2e.sh            # Chrome + CDP 入力 (tsc → emcc → headless Chrome)
bash tools/gui/input/negctl.sh         # ネガコン (shim 8 + host 4; 合計 real 2 分 34 秒)
```
