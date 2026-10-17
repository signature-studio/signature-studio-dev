# flp #5650 (PY-5377): 0x128f9e0 の名前を実行時観測で採る (select 後処理の命中)

親: #5615 (PY-5374 の分割元) / 前提: #5649 (wine64 + gdb の attach)・#5614 (probe 群)。受入: `0x128f9e0` の名前 (`tools/python/REPORT_PY388.md` §6)。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| `0x128f9e0` の名前を実行時観測で確定 | **未確認** (呼出し元 `0x12e3a60` の命中を取れず。名前は未確定) | §3 |

## 2. 実行 (測定 commit: `4ba2a4d3c` に未 commit の probe を載せた状態で実施。commit 後の内容は `a16a3d38c` と同一)

- コード差分の確認: `git diff 4ba2a4d3c a16a3d38c -- tools/flp` = 新規 2 ファイルの追加のみ (`s12_select_post_probe.sh`・`REPORT_APPENDIX_5650.md`)。
- 測定値の出典: 以下の数値は初回実行の報告からの転記。ログ (`$RUNNER_TEMP/s12_gdb_session.txt`) と load・時刻の記録は、後続の run に残っていない。
- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 8.98 s)。
- インストール木: `bash tools/flp/s1_wine_probe.sh` (real 2 m 13.6 s・rc=124 = GUI 継続・`MSGBOX_OnInit=0`・`native-load=0`)。
- 観測: `WAIT=120 bash tools/flp/s12_select_post_probe.sh` (real 2 m 1.2 s・`gdb rc=124`・dll_base `0x7a730000`)。
  - `0x12e3a60` (select 後処理): 命中 **0 件**。
  - `0x128f9e0`: 命中 **5 件**。いずれも `rdx=0`。戻り先 (runtime → VA。VA = runtime − dll_base + 0x400000) は `0x7b58369f`→`0x125369f`・`0x7b68856e`→`0x135856e`・`0x7b5ce87b`→`0x129e87b`・`0x7b506c11`→`0x11d6c11` (`0x7b58369f` は 2 回)。`0x12e3a60` 経由の戻り先は 1 件も無い。
  - 観測 log: `$RUNNER_TEMP/s12_gdb_session.txt` (commit 対象外・後続 run に残らず)。

## 3. 結論

- `0x12e3a60` は attach 後 120 s の観測で命中 0 (attach より前に呼ばれた分は見えていない)。`0x128f9e0` へ `id ≠ 0` で渡る経路は、この観測では確認できなかった。
- よって `0x128f9e0` の呼出し元で実値 (`id`) を採る目的は未達。名前は「未確認」のまま (R7 ④)。推測で埋めない。
- 命中させるには GUI で track select 操作を発火させる必要がある。既存の drive probe (`tools/flp/s6001_drive_probe.sh`・#6001) がその操作を行うかは本 run では未確認。確認は別作業 (#5650 の範囲外)。

## 4. 製品 KPI (起動)

動かしていない。FLEngine 起動の dispatch 数・通過 unit 数・最初のウィンドウの有無は計測していない (本 probe は gdb による関数の命中の記録のみ)。
