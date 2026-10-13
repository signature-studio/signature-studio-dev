> **正本**: `tools/shimx/REPORT.md` §19 の要約。本ファイルは SHX-T6 (#179) の詳細 (本体 250 行上限のため分割移動)。

## 19. SHX-T6 (#179): winmm midi* の強定義置換 (win64 ABI 変換層 + backend 表)

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

- `exports.txt` / `data/sigs.json`: `test.sh` / `gen_sigs.py` が shimx ソースから再生成した結果。差分は `shimx_set_midi_backend` / `shimx_set_notify_hook` / `shimx_seh_*` 等の追加と、`midiOutShortMsg` の HANDLE (i64→i32) 統一。中身の削除は無い (並びだけ変わる)。
- `data/inventory.csv`: midi 18 行の `source` 列を `net.c` → `midi_conv.c` へ変更 (ソースの所在の記録のみ)。数値列は不変。
- `data/coverage.json`: `shimx_hooks` 59 → 70 (運用フックの追加分) のみ。`m11_closure` / `ott_api_resolved` は main の値を維持。
- `BACKLOG.md` / `inventory.md` / `data/inventory.csv` の残りの行: **コミットしていない**。`test.sh` 再生成は入力 (`work/ir_m11.json` 等の M11 IR) が無いと `m11_closure` を空にするため、main の値を維持した。M11 IR が揃った環境で再生成する。

### 19.6 `sig_test.sh` の期待値 (5 → 4)

`sig_test.sh` (a) の陰性対照は `midiOutShortMsg` の drift を数えていた。#179 で shimx 側を HANDLE (i32) に統一したため drift が消え、mismatch は 5 → 4。gate は drift の残る `acmMetrics` へ移した (ケース (h) も同様)。

### 19.7 検証 (HEAD は下記 commit で実行)

| 検証 | コマンド | 結果 | 所要 / 備考 |
|---|---|---|---|
| shimx 全体 (MT/ST・fail-fast 10 モード・M4 53/53・署名 mismatch 0・midi 単体テスト) | `bash tools/shimx/test.sh` | exit 0 | 49 s (本 run 実測) |
| `verify_ott` | 同上 (§7) | **SKIP** (`tools/m8/work/ott_m8.ll` / `tools/m6/work` が無い) | OTT 検証は未実施。素材 (`toolchain-retdec` / `work-m6-ott`) が要る |
| audio MIDI e2e | `bash tools/audio/e2e_midi.sh` | 4/4 PASS, exit 0 | 本 run 実測 (下記 HEAD) |

`verify_ott` の SKIP は既存挙動で、本変更の影響ではない。`test.sh` 全体 exit 0 は「OTT 検証を除く」を意味する。

### 19.8 範囲外・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 登録口 `flmidi_shimx_install()` の起動経路への配線と、shimx 経由の `midiOutGetNumDevs()` 結線確認 | 本 PR 時点では強定義は実行時に効かない | #37 (AU-14) |
| 実 FL (`fl-win64`) での winmm MIDI 結線の実機確認 | FL 実 e2e 未実施 | #37 (AU-14) |
| `shimx` と audio MIDI を同一 wasm に結合した統合 e2e | 本 run は shimx 単体 (模擬 backend) と audio 単体 (flm_midi 直) を分けて検証 | #37 (AU-14) |
| 実 Web MIDI・実デバイス | モック検証のみ (REPORT_MIDI §13-3) | #187 (AU-2) |
| `verify_ott` (OTT 素材での検証) | SKIP のまま | 素材の準備後に実施 (起票先は PM 判断) |
