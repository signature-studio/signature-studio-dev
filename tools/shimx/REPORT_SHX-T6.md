> **正本**: `tools/shimx/REPORT.md` §19 の要約。本ファイルは SHX-T6 (#179) の詳細 (本体 250 行上限のため分割移動)。

## 19. SHX-T6 (#179): winmm midi* の変換層 + backend 表 (強定義の配線は未達)

既知類型との関係: 該当なし (ランタイム shim の接続。lift 欠陥ではない)。依頼: PM 設計決定 1〜4 (#179 コメント)。

### 19.0 結論と未配線の範囲

- **変換層 (shimx 側) は実装済み**: weak な `midi*` 20 関数が win64 MIDIHDR (112B) を native (48B) へ変換し、関数表 `shimx_midi_vtbl` へ委譲する。表は `shimx_set_midi_backend` で登録する。未登録時は従来どおり 0 台。
- **未配線 (次 PR)**: audio 側の登録口 `flmidi_shimx_install()` (`tools/audio/src/flmidi_shimx.c`) は定義のみで、本番の起動経路 (`winstubs_init` / `shimx_init` 後) からも `tools/audio/e2e_midi.sh` からも呼んでいない。そのため本 PR の時点では、実行時に表は登録されず `midi*` は 0 台のままである。「強定義: 達成」とは書かない。
- 結線の検証 (表を登録した状態で shimx 経由の `midiOutGetNumDevs()` が audio 側の値を返すこと) は次 PR で行う。起票先は #37 (AU-14)。

### 19.1 構成

| ファイル | 役割 |
|---|---|
| `src/midi_backend.h` | 関数表 `shimx_midi_vtbl` と native 幅 `shx_midihdr_nat` (48B)。emscripten 非依存 |
| `src/midi_conv.c` | weak な `midi*` 20 関数。guest win64 ABI を変換し表へ委譲。未登録時は従来どおり 0 台 |
| `src/net.c` | `midiIn/OutGetErrorTextW` のみ残置。midi 本体の weak スタブは削除 |
| `src/shimx.h` | `shimx_set_midi_backend` 宣言 (struct タグ前方宣言) |
| `tools/audio/src/flmidi_shimx.c` | audio 側の登録口。`flm_midi*` を表へ束ねる。**未配線** (§19.0) |

shimx は `emscripten.h` に依存しない。`flmidi*.c` は `tools/audio/src` に置いたまま (ビルド依存を shimx へ波及させない)。

### 19.2 win64 ABI 変換 (方向と対象)

guest 側の MIDIHDR は win64 レイアウト (8B ポインタ・`pack(1)`・112B)。`flm_midihdr_t` (wasm ネイティブ・48B) へ変換する。
寸法は mingw-w64 の `mmsystem.h` で確認 (`_Static_assert`: `sizeof(MIDIHDR)==112`, `lpNext` offset 28)。

| 構造体 | guest (win64) | native (wasm) | 方向 |
|---|---|---|---|
| MIDIHDR 全体 | 112B | 48B | copy-in (Prepare/AddBuffer/LongMsg 前) → backend → copy-out |
| `lpData` | 8B ポインタ | 4B | 下位 32bit を copy-in (wasm 線形メモリは共有) |
| `dwBufferLength` / `dwOffset` | 4B | 4B | copy-in のみ |
| `dwBytesRecorded` | 4B | 4B | copy-in → backend が書込み → copy-out |
| `dwFlags` | 4B | 4B | copy-in → backend が DONE/INQUEUE を立てる → copy-out |
| `dwUser` | 8B | 4B | 下位 32bit を copy-in |
| `lpNext` / `reserved` / `dwReserved` | 8B | 4B | copy-in しない (shimx は未使用) |
| 完了通知 p1 (MIM_LONGDATA / MOM_DONE) | native hdr | — | copy-out 後、p1 を guest アドレスへ戻して callback へ渡す |
| MIDIINCAPSW / MIDIOUTCAPSW | 76B / 84B | 同一 | **素通し** (ポインタを含まず、レイアウト一致を確認) |

mirror は guest ヘッダと 1:1 (guest アドレスで引く)。Prepare で確保、Unprepare 成功で解放。
未 Prepare のヘッダへの AddBuffer/LongMsg は `MIDIERR_UNPREPARED (64)`。

### 19.3 コールバック invoke

完了通知の `midi_dispatch` (`shimx_set_midi_backend` 登録時に `set_cb_invoke` で backend へ渡す) は `cb` が実 C 関数ポインタ (< intptr_limit) なら直接呼び、guest VA なら `shimx_cbtrans_get_invoke()` (SHX-T2 #178 と同じ invoke 契約) へ落とす。`cb==0` (CALLBACK_NULL) は通知しない。

### 19.4 timeBeginPeriod (方針 3 行)

- 解像度の要求は **無視する (no-op のまま)**。`timer.c` の weak 既定 (0 を返す) を変更しない。
- 理由: Web 側のタイマー (AudioWorklet サンプルクロック / `performance.now`) は固定で、winmm の周期要求に応じて変えられない。
- 要求を受けても Web の精度は変わらないため、偽の成功を返すより現状の no-op を明示する。

### 19.5 生成物の扱い (SHX-T6 で変わったもの)

- `exports.txt` / `data/sigs.json`: `test.sh` / `gen_sigs.py` が shimx ソースから再生成した結果。差分は `shimx_set_midi_backend` / `shimx_set_notify_hook` / `shimx_seh_*` 等の追加と、`midiOutShortMsg` の HANDLE (i64→i32) 統一。中身の削除は無い (並びだけ変わる)。`shimx_set_trace_file` の行も同じ再生成で入った (main の `shimx.h` に宣言済みで、main の `exports.txt` が古かったための追随。SHX-T12 の変更であり SHX-T6 の変更ではない)。
- `data/inventory.csv`: midi 18 行の `source` 列を `net.c` → `midi_conv.c` へ変更 (ソースの所在の記録のみ)。数値列は不変。
- `data/coverage.json`: `shimx_hooks` 68 → 69 (`shimx_set_midi_backend` の 1 件のみ) のみ。`m11_closure` / `ott_api_resolved` は main の値を維持。
- `BACKLOG.md` / `inventory.md` / `data/inventory.csv` の残りの行: **コミットしていない**。`test.sh` 再生成は入力 (`work/ir_m11.json` 等の M11 IR) が無いと `m11_closure` を空にするため、main の値を維持した。M11 IR が揃った環境で再生成する。

### 19.6 `sig_test.sh` の期待値 (5 → 4)

`sig_test.sh` (a) の陰性対照は `midiOutShortMsg` の drift を数えていた。#179 で shimx 側を HANDLE (i32) に統一したため drift が消え、mismatch は 5 → 4。gate は drift の残る `acmMetrics` へ移した (ケース (h) も同様)。

`midiOutShortMsg` の第 1 引数は `HANDLE` (i32) に統一した (旧 `uint64_t` 側と RetDec の i64 declare の不一致を解消)。wasm32 では HANDLE が 4B のため、i64 で受ける呼出元は shimx 内に無い (`grep -rn midiOutShortMsg tools/shimx/src` は定義 `midi_conv.c` と宣言 `shimx_stubs.h` のみ)。

### 19.7 検証 (HEAD は下記 commit で実行)

| 検証 | コマンド | 結果 | 所要 / 備考 |
|---|---|---|---|
| shimx 全体 (MT/ST・fail-fast 10 モード・M4 53/53・署名 mismatch 0・midi 単体テスト) | `bash tools/shimx/test.sh` | exit 0 (MT/ST PASS・fail-fast 10・M4 MT/ST PASS・sig_test ALL PASS・mismatch 4 (a) / 0 (b)) | 43 s (HEAD 80bc25d6・load 0.88) |
| `verify_ott` | 同上 (§7) | **SKIP** (`tools/m8/work/ott_m8.ll` / `tools/m6/work` が無い) | OTT 検証は未実施。素材 (`toolchain-retdec` / `work-m6-ott`) が要る |
| audio MIDI e2e (audio 単体。shimx 変更はビルド対象外) | `bash tools/audio/e2e_midi.sh` | 4/4 PASS, exit 0 | 69 s (HEAD 80bc25d6・load 0.33) |

注: `test.sh` は実行中に `BACKLOG.md` / `inventory.md` / `data/coverage.json` / `data/inventory.csv` を M11 入力欠落の状態で再生成する。検証後はこれらを main の内容へ戻してある (コミットに含めない)。

e2e 内訳: `midi_all` 54/54 (2,801 ms) / `negctl_drop_one_short_msg` 62,500 ms / `negctl_flip_sysex_bit` 1,892 ms / `worker_webmidi_probe` PASS (記録のみ)。
注: `e2e_midi.sh` は shimx をビルドしないため、この PASS は audio 側の回帰確認に限られる。shimx と audio の結合は未検証 (§19.8)。

`verify_ott` の SKIP は既存挙動で、本変更の影響ではない。`test.sh` 全体 exit 0 は「OTT 検証を除く」を意味する。

### 19.8 範囲外・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 登録口 `flmidi_shimx_install()` の起動経路への配線と、shimx 経由の `midiOutGetNumDevs()` 結線確認 | 本 PR 時点では強定義は実行時に効かない | #37 (AU-14) |
| 実 FL (`fl-win64`) での winmm MIDI 結線の実機確認 | FL 実 e2e 未実施 | #37 (AU-14) |
| `shimx` と audio MIDI を同一 wasm に結合した統合 e2e | 本 run は shimx 単体 (模擬 backend) と audio 単体 (flm_midi 直) を分けて検証 | #37 (AU-14) |
| 実 Web MIDI・実デバイス | モック検証のみ (REPORT_MIDI §13-3) | #37 (AU-14) |
| `verify_ott` (OTT 素材での検証) | SKIP のまま | 素材の準備後に実施 (起票先は PM 判断) |

### 19.9 M11 closure への配線 (#179 run #6, `build.sh --midi`)

`tools/m11/shimx_link/build.sh --midi` (opt-in) で audio の `flmidi*.c` を M11 closure に入れ、`sx_midi_boot.c` の constructor で `flmidi_shimx_install()` を呼ぶ。既定 variant は不変。

| 項目 | 実測 (HEAD 上、foreground) |
|---|---|
| `build.sh --midi` | rc 0 / 8.2 s / `OK plain_failfast_midi` |
| `build.sh` (既定) | rc 0 / `OK plain_failfast` (同 HEAD で再実行。時間は未計測) |
| `node midi_e2e.mjs m11_sx_plain_failfast_midi.cjs` | 3/3 PASS / 0.38 s。`sx_midi_probe_numdevs(3)` = 3 (表経由で n_out が返る。未登録の weak は常に 0) |
| `signature mismatch` | 1 件 (`midiOutShortMsg` i64 vs i32)。既定 variant でも 1 件 = 本変更由来ではない (既知) |

- 残件: この closure は M11 の検査用 wasm で、本番の FL 経路 (`tools/startup`・実 FL・headless Chrome の `midiOutGetNumDevs` 結線) は未配線・未検証。`Closes #179` の条件は未達。起票先 #37 (AU-14)。
- `midiOutShortMsg` の signature mismatch (i64 呼出 vs i32 定義) は本変更で解消していない。shimx の `outShortMsg` 引数幅の確認が必要 (起票先 #37)。

### 19.10 winstubs 結線 closure への配線 (#179 run #15)

- `build.sh --ws --midi` (tools/startup/winstubs 結線あり) でも `flmidi_shimx_install()` が constructor で走り、`midi_e2e.mjs` 3/3 PASS。`ws_e2e.mjs` の BOOT 基準 (init 18 / units 17) と G03/G05/G12 は `--midi` の有無で不変。
- 実測と修正 (旧 main の全 variant が `undefined exported symbol: _sxt_count` で link 失敗していた件を含む) は `tools/m11/shimx_link/REPORT.md` §11。
- 残件 (未達): 本番 FL 経路・headless Chrome での `midiOutGetNumDevs` 結線、`midiOutShortMsg` の引数幅 → #37 (AU-14)。
- #179 の範囲縮小: #179 本文の「作業」を達成範囲 (midi* 強定義・timeBeginPeriod の no-op 方針 = §19.4) に縮め、本 PR は `Closes #179`。§19.9 の「`Closes #179` の条件は未達」は縮小前 (run #6) の記録として残す。
