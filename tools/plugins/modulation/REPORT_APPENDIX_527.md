# modulation 付録 (#527 PLG-F5-2 engine gate)

本体 `REPORT.md` の §4 (engine 4 本) の到達性 gate。判定は `engine_judge.py` (exit code 化)。

## I. engine 到達性 gate (受入 1 の exit code 化)

- 判定: `engine_judge.py <outdir>` (`engine_lift.sh` の出力 `summary.csv` と `engine_name_gap.py` の名前照合)。
  - 合格: `lift_rc == 0` かつ `erc3 == 0` かつ define 無し range (名前照合後) が 0 件 (0 B)。exit 0。
  - 不合格: 上記のどれかが欠ける。exit 1。
  - 入力不正 (summary.csv の欠落・列数・非整数、名前照合の失敗)。exit 2。
- 出力行には `stub=` (未実装 helper 数) を必ず併記する。stub を含む `emcc -c` 通過は正しさを示さない (bit-exact は #197 で未検証)。
- ネガティブコントロール: `engine_judge.py --selftest` (合成入力 8 ケース、全て期待 exit と理由文字列を確認)。

### I.1 NC (selftest、HEAD の commit で実行)

| ケース | 期待 exit | 実測 exit | 理由の文字列 |
|---|--:|--:|---|
| 無改変 (good) | 0 | 0 | PASS |
| `lift_rc=1` | 1 | 1 | `lift_rc=1` |
| `erc3=1` | 1 | 1 | `emcc_c_rc(erc3)=1` |
| `function_2000` の define を除去 (名前照合で解決不可) | 1 | 1 | `define 無し range 1 件` |
| 同名 `entry_point` の欠落 range 2 件 (define 1 件) | 1 | 1 | `define 無し range 2 件` |
| 列数不足 (16 → 15 列) | 2 | 2 | `列数` |
| 非整数 (`x`) | 2 | 2 | `整数` |
| summary.csv 無し | 2 | 2 | `summary.csv` |

`selftest: OK` (exit 0)。

### I.2 実測 (4 本、`engine_lift.sh <block> 300` の順次実行、`engine_judge.py` で判定)

- 測定値の正本は `REPORT.md` §4 の表 (lift_rc・define 数・未実装 helper・erc3)。ここには持たない。
- 判定結果 (前 run の記録。本 PR では未再現): 4 本とも `define 無し (名前照合後)` 0 件 (0 B)、judge PASS (exit 0)。REPORT.md §4 の「4 本すべて `emcc -c` rc 0」も同じ前 run の記録。
  - 名前照合の内訳 (define 無し 2 件の解決先): 18977 `dispatch` + `entry_point` / 19143 `DispatchToEngine` + `entry_point` / 19266 `VSTPluginMain` + `entry_point` / 19268 `entry_point` + `VSTPluginMain`。
- 測定 commit: origin/main 2b99366a の上に `engine_judge.py` を追加した worktree (`ws-527`)。lift 本体は未変更。

#### I.2.1 生データの所在 (未取得の項目)

本 run では 4 本の lift を再実行できない (`toolchain-retdec`・`toolchain-emsdk`・`work-liftlib`・`work-fw-stage1` 未取得。`/opt/emsdk` 無し)。上記の判定結果は前 run の記録で、本 PR では再現していない。

| 項目 | 状態 |
|---|---|
| `summary.csv` の 4 行 (`engine_lift.sh` の出力) | 未取得 (`work/` は gitignore。raw が残っていない) |
| `engine_name_gap.py` の出力 4 行 (`named,rest,rest_bytes,unresolved`) | 未取得 (同上) |
| 測定の run 日時・終了時 loadavg・並列数 | 未記録 (順次実行。loadavg は取っていない) |
| 測定 commit の `git rev-parse` 確認 | 本 run では `ws-527` を確認できず未確認 |

上の 4 項目が揃うまで、「名前照合で 4 本とも define 無し 0」は実測として扱わない。
- 注意: この gate は到達性のみ。stub (未実装 helper) を含み、bit-exact は未検証 (#197・#534・#779)。
- 受入 1 の残り: judge 相当の exit code gate は本 PR で追加。bit-exact は #197 依存のため未達。

## J. 殻の動的ロード呼出の静的特定 (受入 5 の残り)

対象 4 殻 (18978 / 19144 / 19265 / 19267、fl-win64 の `extracted/` を pefile + capstone で解析)。スクリプトは `engine_shell_gpa.py`。

- KERNEL32 の import thunk (`jmp qword ptr [rip+…]`) を経由する呼出を列挙。thunk は殻ごとに求め直す (アドレスは殻で異なる)。
- `LoadLibraryExW` の呼出は 4 本とも 1 箇所 (FS 0x415b7b / HC・VC・VP 0x4158ab)。`LoadLibraryW` は 4 本とも 9 箇所、`LoadLibraryA` は 1 箇所。
- `GetProcAddress` の呼出は 4 本とも 10 箇所。そのうち `GetLogicalProcessorInformation` / `GetThreadPreferredUILanguages` / `GetLongPathNameW` など 6 箇所は引数の文字列を取れた (エンジン関係ではない)。残り 4 箇所は引数が中継関数 (FS 0x41d450 は KERNEL32 の `GetProcAddress` import thunk、0x418350 など。VC 0x41d1a0 / 0x4180d0 なども同様に中継) 経由で、文字列を静的に取れていない。中継関数のアドレスは `engine_shell_gpa.py` の出力には含まれず、出典 (手作業の逆アセンブルか否か) は未記録のため、未検証の値として扱う。
- 殻内の engine export 名は UTF-16 で入る (ASCII は無し)。FS: `dispatch` 0x2dda92、HC: `DispatchToEngine` 0x2e9722、VC / VP: `VSTPluginMain` 0x2d9dd8 / 0x2db668。engine 名 `Engine_x64.dll` (FS, 0x1a2b58) / `engine_x64.dll` (HC 0x2e9704, VC 0x2e9da4, VP 0x2ecfc4)。
- 結論 (推定): 殻は `LoadLibraryExW` を 1 箇所で呼び (スクリプトで確認)、その引数が `engine_x64.dll` であること (推定。LoadLibraryExW 行の引数は未取得)、`GetProcAddress` のラッパー経由で export 名を引く、という構造と推定する。ラッパーに渡る引数の実値 (どの export 名を引くか) と、VST2 engine の `VSTPluginMain` 呼出箇所は未了。受入 5 は未達のまま #527 に残す。

## K. 殻の engine 名参照と呼出経路 (受入 5 の続き、`engine_shell_entry.py`)

測定 commit: `c5627440` (コード差分の最終 commit)。`git diff c5627440 HEAD -- tools/plugins/modulation/` の出力: 空 (差分 0)。
用語: 「thunk」= KERNEL32 の import thunk (`jmp [rip+…]`)、「ラッパー」= thunk を呼ぶ関数 (§J と統一)。

測定: `python3 modulation/engine_shell_entry.py <block_PE.bin>` (fl-win64 extracted の殻 4 本、静的のみ)。

| 殻 | engine 名の lea 参照 (VA) | 直後の call 先 (ラッパー) | 所見 |
|--:|---|---|---|
| 18978 (FS) | `Engine_x64.dll` 0x6de5b3 → `0x4106d0` / `dispatch` 0x6de5df → `0x41d460` | `0x41d460` (ラッパー) → `0x41d450` (`GetProcAddress` の thunk) | 同一関数内で DLL 名を `0x4106d0` に渡し (呼出先の同定は未了)、続けて `dispatch` を `0x41d460` 経由で解決 |
| 19144 (HC) | `engine_x64.dll` 0x6ea244 → `0x410400` / `DispatchToEngine` 0x6ea270 → `0x41d1e0` | `0x41d1e0` (ラッパー) → `0x41d1d0` (`GetProcAddress` の thunk) | FS と同型 |
| 19265 (VC) | `engine_x64.dll` 0x6ea7ff → `0x410400` | 名前 `VSTPluginMain` の lea 参照は本スクリプトでは見つからず | 未確定 |
| 19267 (VP) | `engine_x64.dll` 0x6eda1f → `0x410400` | 同上 | 未確定 |

- FS・HC は「DLL 名 → ラッパー」の直後に export 名を解決する形で、殻が engine を動的ロードして名前で関数を引く推定と整合する (静的な推定。ラッパーの内部で `GetProcAddress` が実際に呼ばれることは未確認)。
- VC・VP は `VSTPluginMain` の文字列の直接参照が見つからない。VST 系の名前は別経路 (間接・連結・別の文字列表現) の可能性があり、未解析。
- 殻の `GetProcAddress` 10 箇所のうち、ラッパー経由の 4 箇所 (今回検証した FS の呼出 `0x41d48e` / `0x41d4b9` を含む) の引数の実値はこれで取れていない。上記の名前参照は、その呼出の一部に対応する。
