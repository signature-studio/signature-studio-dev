# M11 REPORT §16 (#490 [M11-N15]) の詳細
本体 `REPORT.md` §16 の付録 (250 行上限のため分割)。
## 16. #490 [M11-N15]: main HEAD の 4c3baa4 / faee5b6 状態の実測

起点 `6e5c8dac` (origin/main)。4 vCPU・load 0.4〜0.95・`m11_gen_ir2.sh` で IR を作成 (ldfix=applied, qstore=applied)。PE=`FL_WIN64_DIR` の block00031_PE.bin。

| 構成 | units_run | 停止 (通常起動) | survey ok/trap(oom)/miss/noproc/clobber | e2e 所要 | load |
|---|---|---|---|---|---|
| main HEAD (boot5 あり) | 53 | `memory access out of bounds` @ function_8c6530 | 870/25(1)/46/1/0 | 43.9 s (1 回目) / 48.3 s (2 回目) | 0.69〜0.95 |
| ネガコン: boot5 除去 (IR 再生成) | 52 | 同一関数 (function_8c6530) | 869/25(1)/47/1/0 | 48.3 s | 0.78 |

- 受入 1 (完走実測): 達成。main HEAD の m11_e2e.sh は exit 0。
- 受入 2 (二分): **未達**。faee5b6 の m11_win.c / m11_ov.c 部分を `git apply -R` で外そうとしたが、main の後続変更 (417b70 / 409470 / 410b10 系) と衝突し適用できなかった。退行の切り分けは未実施。main では退行が解消済みのため当面の実害はない。
- 受入 3 (kind 12): 達成 (main #496 で 416720 の間接 call 込みで転記済み, `m11_ov.c` case 12)。kind 12 を実行する unit の実測は未。
- 受入 4 (ネガコン): **部分**。boot5 除去で units_run 53→52、survey ok 870→869、miss 46→47。停止 trap の関数は同一のため「元の停止 (22 unit) に戻る」は成立しない。boot5 (25 関数) の寄与は 1 unit に留まる。
- 環境注記: emsdk の `cache/` が packer 所有で emcc が書けず、`sudo chown -R runner:runner /opt/emsdk/upstream/emscripten/cache` で解消 (CI 環境では要対応)。capstone/pefile は `pip install --user` で導入。

### #1141 [M11-N66] 再測定 (起点 96e608df = origin/main)

環境: Actions runner (4 vCPU・load 0.4〜1.1)。素材 `work-m11` を展開し IR 再生成経路で測定。PE は `fl-win64` の `extracted/block00031_PE.bin` (sha256 b2c64da4…) を使用。
注意: `work-m11` に `lift_pe.sha256` が無く、全再生成 (`m11_bounds.py`) は素材に無い `functions_dll.csv` (Ghidra 中間物) を要求して失敗した。そのため `lift_pe.sha256` に展開 PE の sha256 を手で書いて差分経路に入れた (測定入力を手で変えた限界)。
未解決 (起票先): 上の 2 件 (全再生成が `functions_dll.csv` を要求する問題・手書き `lift_pe.sha256` の差分経路) はいずれも #1141 のコメント https://github.com/signature-studio/signature-studio-dev/issues/1141#issuecomment-6155478121 で追跡する (新規起票なし・既存 issue への追記)。

| 構成 | units_run | 停止 | survey ok/trap/miss/noproc | e2e 所要 | IR sha256 |
|---|---|---|---|---|---|
| main 96e608df (baseline 1 回目) | 53 | `unreachable` @ function_8c5eb0 | 872/23/46/1 | 125 s (全再生成失敗後の初回・IR 再生成込み) | c9308c98… |
| main 96e608df (baseline 2 回目) | 53 | 同上 | 872/23/46/1 | 44 s | c9308c98… |
| ネガコン: boot5 除去 (m11_extra_ranges5.txt と boot5.lift.ll を退避) | 52 | 同上 | 870/24/47/1 | 78 s | 16d1bae6… |

- 受入 1 (4c3baa4 / faee5b6 の二分): **未達**。`git apply -R --check` で 4c3baa4 (m11_ov.c 467c40 / m11_gen_ir2.sh / m11_extra_ranges5.txt) と faee5b6 (m11_win.c / m11_ov.c 417b70・409470) の両方が衝突し適用不可を再確認。faee5b6 の寄与は未測定。boot5 除去 (4c3baa4 の一部) で units_run 53→52、survey ok 872→870 を実測。
- 受入 2 (kind 12 unit の実測): **未達**。baseline で `_CopyArray` 系の入口 unit 86 / 357 / 496 は survey で ok。ただし `m11_ov.c` の case 12 に stderr probe を入れて再ビルドしても、full survey の stderr に `[CA_KIND]`・`[K12HIT]` が 0 件 (survey_units.mjs は stderr を捕捉しない・単独 SV_ONLY は OOB で baseline と不整合)。kind 12 の通過は未実証。probe は作業ツリーから除去済み。
- 次の作業: (a) faee5b6 の寄与を hunk 単位で手動アブレーション、(b) survey 側で stderr を捕捉する手段 (または trace 出力) を入れてから kind 12 を確認。

### #1141 再実行 (run 2): faee5b6 寄与の単独アブレーション (測定 commit f3ffd7ba = origin/main)

起点 `f3ffd7ba` で `work-m11` を `tools/m11/work/` に展開 (gitignore)、fl-win64 の PE は `$RUNNER_TEMP/win64/extracted/block00031_PE.bin` (sha256 b2c64da4…)。`work/lift_pe.sha256` に PE の sha256 を手で書いて差分経路で測定 (前回と同じ限界)。load は各実行とも 0.3〜0.6。
アブレーションは **一時 gate (`#if !M11_ABL_*`) で 1 関数ずつ無効化** した (他は main のまま)。gate は測定後に作業ツリーから除去済みで、コードには残していない。

| 構成 | units_run | 停止 | survey ok/trap/miss/clobber | e2e 所要 | rc |
|---|---|---|---|---|---|
| baseline (f3ffd7ba) | 53 | `unreachable` @ function_8c5eb0 | 872/23/46/0 | 153 s | 0 |
| A: `function_417b70` (DynArraySetLength) を無効 | 50 | (未記録) | 422/26/492/1 | 39 s | 1 (SURVEY_OK 800 未満) |
| B: `function_409470` (ReallocMem) を無効 | 22 | OOB @ function_408040 <- 409470 <- 417b70 | 839/56/46/0 | 38 s | 0 |
| C: `SysAllocStringLen` (BSTR) を無効 | 22 | Halt0 経由の早期終了 | 871/24/46/0 | 47 s | 0 |

- 注意 1: 上の表は **1 つずつの単独無効化** であり、二分 (半分ずつ) ではない。`SysReAllocStringLen` / `SysStringLen` は C の gate に含めていない。
- 注意 2: 1 回目に gate を `-D` 無しで入れた試行は ov.o に強シンボルが残り無効化されていなかったため (nm で確認)、破棄して gate を `CF` 経由に直した。上表は gate が効いたことを nm で確認した後の値のみ。
- 読み取り: 417b70 と 409470 の override は、どちらを外しても units_run が大きく落ちる (53 → 50 / 22)。faee5b6 の 2 override が退行を抑えている側であり、4c3baa4 (boot5) の寄与 (前回の 53→52) より大きい。ただし「faee5b6 が退行を起こした」の実証ではなく、override を外すと lift 版 (RetDec・既知の D7 型欠陥) に戻って壊れる、という結果。4c3baa4 単独の無効化は未測定。
- 受入 2 (`_CopyArray` kind 12 の実行 unit): **今 run では未実施**。survey_units.mjs が stderr を捕捉しない問題は未解決のため、kind 12 の通過は未実証のまま。次は survey 側の trace 出力の追加 (子 issue #1511 [M11-N97] で追跡)。
- 全再生成 (`m11_bounds.py`) が要求する `functions_dll.csv` の問題は前回と同じく未解決 (#1141 のコメントで追跡)。
- 未測定 (#1141 残り): 4c3baa4 (boot5 / 467c40 間接 call) の単独無効化は前回の boot5 除去のみ。faee5b6 の `SysReAllocStringLen`・`SysStringLen` 単独の寄与は未測定。

### #1141 再実行 (run 3): 4c3baa4 の 467c40 override と BSTR 単独の無効化 (測定 commit cd83e84c = origin/main)

起点 `cd83e84c` (main)。`work-m11` を `tools/m11/work/` に展開、PE は `$RUNNER_TEMP/win64/extracted/block00031_PE.bin` (sha256 b2c64da4…)。`work/lift_pe.sha256` は PE の sha256 を手で書いた差分経路 (前回と同じ限界)。boot5 は本 run で RetDec lift 済み (`lift boot5 (RetDec): ok`)。load は各実行とも 0.6〜1.1。

| 構成 | units_run | 停止 | survey ok/trap/miss/clobber | e2e 所要 | rc |
|---|---|---|---|---|---|
| baseline (cd83e84c, gate 無し) | 53 | `unreachable` @ function_8c5eb0 | 872/23/46/0 | 155 s | 0 |
| gate 導入後・既定 (override 有効) | 53 | 同上 | 872/23/46/0 | 48 s | 0 |
| D: `function_467c40` (4c3baa4 の間接 call 復元) を無効 | 22 | Halt0 経由の早期終了 | 871/24/46/0 | 47 s | 0 |
| E: `SysReAllocStringLen` (faee5b6 の BSTR) を無効 | 53 | 同上 (baseline と同じ) | 872/23/46/0 | 48 s | 0 |
| F: `SysStringLen` (faee5b6 の BSTR) を無効 | 53 | 同上 (baseline と同じ) | 872/23/46/0 | 48 s | 0 |
| 復元後 (HEAD の既定) | 53 | 同上 | 872/23/46/0 | 49 s | 0 |

- gate の確認: D は `llvm-nm work/obj/ov.o` で `function_467c40` の定義が消えたことを確認。E/F は `win.o` で該当シンボルの定義が 0 件になったことを確認。
- 方式: 一時 gate (`#if !M11_ABL_*`) を `m11_ov.c` / `m11_win.c` に入れ、`m11_build.sh` の CF に `${M11_ABL_CF:-}` を一時的に足して 1 つずつ測定。測定後に `git restore` で全て戻し、`tools/m11` の差分は 0。
- 読み取り: 4c3baa4 の 467c40 間接 call 復元 (`function_467c40` override) が units_run 53 を支えている。これを外すと 22 unit で Halt0 に落ちる。
- faee5b6 の override のうち units_run に効くのは 3 点: `function_417b70` (run 2 A: 単独無効化で 50)・`function_409470` (run 2 B: 22)・`SysAllocStringLen` (run 2 C: 22)。`SysReAllocStringLen`・`SysStringLen` は単独では units_run 53 のまま (run 3 E/F で影響なし)。
- 注意: これらはいずれも「外すと lift 版 (RetDec・既知の D7 型欠陥) に戻って壊れる」結果であり、faee5b6 が退行を起こしたことの実証ではない。今回の D は 467c40 override を外す単独の変化。boot5 (25 関数の lift 追加) と 467c40 の組み合わせ分解はしていない。ov.o は gate 変更でキャッシュ無効化され再コンパイル済み。
- 受入 2 (`_CopyArray` kind 12) は今 run では未実施 (子 issue #1511 で扱う)。

### #1141 再実行 (run 4): boot5 と 467c40 の組み合わせ分解 (測定 commit 3d21715b = origin/main)

起点 `3d21715b` (origin/main) で worktree `ws-1141` を作成。`work-m11` を `tools/m11/work/` に展開 (アーカイブが `tools/m11/work/` を含んでいたため一段戻して配置)、PE は `$RUNNER_TEMP/win64/extracted/block00031_PE.bin` (sha256 b2c64da4…)。`work/lift_pe.sha256` は PE の sha256 を手で書いた差分経路 (前回までと同じ限界)。load は各実行とも 0.6〜1.0 程度。

| 構成 | IR sha256 (先頭 8) | units_run | 停止 | survey ok/trap/miss/clobber | e2e 所要 | rc |
|---|---|---|---|---|---|---|
| baseline (3d21715b, boot5 あり, gate 無し) | 6909f85d | 53 | `unreachable` @ function_8c5eb0 | 872/23/46/0 | 170 s | 0 |
| I: boot5 あり + `function_467c40` 無効 (boot5 を退避せず gate だけ入れた試行) | 6909f85d (baseline と同一) | 22 | Halt0 経由の早期終了 | 871/24/46/0 | 113 s | 0 |
| H: boot5 無し + `function_467c40` 無効 | b47a4d3a | 22 | Halt0 経由の早期終了 | 870/25/46/0 | 53 s | 0 |

- 未実施: 構成 G (boot5 無し・467c40 有効) は測っていない。復元後の baseline 再実行も未実施 (作業ツリーは `git restore` で main と一致を確認したのみ)。
- gate の確認: 467c40 gate は `#ifndef M11_ABL_467C40` を `m11_ov.c` に入れ、`m11_build.sh` の CF に `${M11_ABL_CF:-}` を一時的に足して有効化。`nm work/obj/ov.o` は本 run で `file format not recognized` となり確認できていない。構成 I の 871/24/46 が run 3 の D と一致したことを、gate が効いた根拠とする (前回 run 3 は `llvm-nm` で確認済み)。
- 構成 I の結果: `m11_e2e.sh` は `m11_extra_ranges5.txt` が有ると boot5 を再 lift するため、boot5 を外すには退避が必要。退避せずに gate だけ入れた試行が I。
- 読み取り: boot5 の有無は、467c40 が無効のとき units_run を変えない (22 → 22)。467c40 の間接 call 復元が units_run 53 を支える、という run 3 の結論を、boot5 を外した状態でも再確認できた。boot5 単独の影響 (467c40 有効時の 53 → 52 の変化) は、今 run では構成 G が未実施のため未確定。前回 PR #1362 の 96e608df での値 (53→52) とは起点が異なる。
- 未測定 (#1141 残り): 構成 G (boot5 除去・467c40 有効) の完走可否、4c3baa4 の残り部分 (boot5 と 467c40 以外の hunk)、`SysReAllocStringLen`・`SysStringLen` の組み合わせ。
- 作業ツリーの後始末: gate・退避・ビルド変更はすべて `git restore` で戻し、`tools/m11` の追跡ファイル差分は 0 (`m11_extra_ranges5.txt` は退避から復元済み)。

## 16. #490 [M11-N15]: main HEAD の 4c3baa4 / faee5b6 状態 (部分達成, 本体 REPORT.md から移動)
main `6e5c8dac` で通常起動・survey は完走 (53/942, survey ok 870)。ネガコン (boot5 除去) は 52/942 で「元の停止に戻る」は不成立。faee5b6 の二分は逆パッチが衝突し未成立。詳細は `REPORT_N15.md` §16。

### #1511 [M11-N97] survey の stderr 全行捕捉と _CopyArray kind 12 (416720) の到達確認

測定 commit `c22f8b6b` (コード変更の最後の commit。起点は `1e3ee7af` = main)。4 vCPU・load 0.5〜0.7 (各実行の前後で記録)。素材 `work-m11` を `tools/m11/work/` に展開し、`fl-win64` の PE (`$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`) で `m11_gen_ir2.sh` (45 s・ldfix applied) → `m11_build.sh` (26 s)。全再生成 (`m11_e2e.sh --full`) は行っていない (RetDec・Ghidra 中間物は不要)。

**変更点**: (a) `survey_units.mjs` に `SV_ERR_LOG=<file>` を追加し、非 trace の stderr を unit 番号付きで全行出す (既存の `rec.err` は unit あたり先頭 3 行のみ)。既定 OFF。(b) `m11_ov.c` の case 12 に `M11_INSTR_K12` (既定 0) の計測 probe `[K12HIT]`、`_CopyArray` 入口に `[CA_KIND]` を追加。`m11_build.sh` は `M11_INSTR_K12` を `-D` で渡し、stamp で `ov.o` を作り直す。

| 構成 | ok/miss/other/halt0/oob/noproc | 所要 | stderr 行 (unit 数) | `[K12HIT]` | `[CA_KIND]` |
|---|---|---|---|---|---|
| 変更前 (1e3ee7af 相当・同じ build) | 870/47/1/7/16/1 | 13 s | (`SV_ERR_LOG` 無し) | - | - |
| HEAD `c22f8b6b`・既定 (K12=0) | 870/47/1/7/16/1 | 13 s | 70 (31 unit) | 0 | 0 |
| HEAD・probe (K12=1) | 872/47/1/7/14/1 | 13 s | 86 (31 unit) | 0 | 16 (全件 kind=18) |

- 受入 1 (既定結果が変わらない): 達成。変更前と HEAD 既定で kind 分布は完全一致 (差分 0)。JSON は frames の `survey_units.mjs` 行番号が変わるだけで、units の kind は全 942 unit 一致。注: REPORT 上の旧基準「ok 872 / trap 23 / miss 46」は #1141 時点の値で、現 main の同一 build は 870/47 (boot5 除去等の既存差分。本 issue では変えていない)。
- 受入 2 (kind 12 の到達): **未到達**。probe 入り build で全 942 unit の survey を実行し、`[K12HIT]` は 0 件。`_CopyArray` の入口 (`function_416db0`) は 16 回 (unit 17 / 86 / 357 / 496 の各 4 回) で、全件 kind=18 (kind 12 の要素型が現れない)。boot 段階 (unit -1) の stderr は 2 行で `[CA_KIND]` は無し。
- **probe の副作用 (未解決)**: probe 入り build で unit 304 (`535bf2`→oob が ok) と unit 555 (同じく oob→ok) の kind が変わった。`[CA_KIND]`・`[K12HIT]` の出力経路 (`M11_TRACE`) は #495 の SP 退避で汚染を抑えているが、この 2 unit の差は説明できていない。計測の透過性は未確認のため、kind 12 が既定 build で別経路から到達している可能性は残る (既定 build からは直接観測できない)。
- 受入 3 (測定 commit・load・所要秒・stderr 件数): 上表に記載。

stderr 件数の注意: `rec.err` 由来の `err` は unit あたり 3 行で打ち切られるため、件数はこの表の `SV_ERR_LOG` 出力のみを使う。

再現:
```
cd tools/m11
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_PE=$FL_WIN64_DIR/extracted/block00031_PE.bin bash m11_gen_ir2.sh
FL_WIN64_DIR=... M11_PE=... bash m11_build.sh                  # 既定 (K12=0)
SV_ERR_LOG=work/s1511/err.txt node trap_triage/survey_units.mjs work/s1511/out.json
M11_INSTR_K12=1 bash m11_build.sh                              # 計測 probe 入り
```

### #1670 [M11-N114] _CopyArray kind 12 (416720) の到達経路と K12 probe の副作用切り分け (#1511 の残り)

測定 commit `5ff58a9e` (コード変更の最後の commit。起点 `7e665077` = main)。4 vCPU・load 0.53〜0.99 (各 build/survey の前後で `uptime` 記録)。素材 `fl-win64` (`$RUNNER_TEMP/fl-win64`) と `work-m11` を展開し、`m11_gen_ir2.sh` (51 s・rc 0・ldfix applied) → `m11_build.sh` (25 s)。survey は各 13 s。

**変更点**: `m11_build.sh` に `M11_TRACE_ISOLATE` (既定 1) を `-D` で渡し、stamp で `ov.o` を作り直す。`M11_TRACE_ISOLATE=0` で #495 の SP 退避を外した trace (ネガコン) を作れるようにした。既定値は従来と同一。

| 構成 (`5ff58a9e`) | ok/miss/other/halt0/oob/abort/noproc | stderr 行 | `[K12HIT]` | `[CA_KIND]` |
|---|---|---|---|---|
| iso1 K12=0 (既定) | 870/47/1/7/16/0/1 | 70 | 0 | 0 |
| iso0 K12=0 | 870/47/1/7/15/1/1 | 72 | 0 | 0 |
| iso1 K12=1 | 872/47/1/7/14/0/1 | 86 | 0 | 16 (全件 kind=18) |
| iso0 K12=1 | 872/47/1/7/14/0/1 | 86 | 0 | 16 (全件 kind=18) |

既定構成の数値は REPORT 上の #1511 節 (870/47/1/7/16/1, 70 行) と一致。

- **受入 2 (kind 12 の到達経路)**: **未特定**。全 4 構成で `[K12HIT]` は 0 件。`[CA_KIND]` は unit 17/86/357/496 の計 16 回のみで全件 kind=18。IR 上の `function_416db0` 呼出し元は 12 箇所 (`boot_final.ll` を `grep` で確認) だが、どの呼出しが kind 12 を渡すかは未確認 (呼出し元ごとの kind を確かめる probe は未実施)。boot 段階 (unit -1) の `[CA_KIND]` は 0 件。
- **受入 3 (probe の副作用)**: unit 304 と 555 は K12=1 で oob→ok に変わる (iso1 でも iso0 でも同じ)。isolation の有無は差を作らない (iso0 K12=1 = iso1 K12=1)。ただし 304 と 555 では `[CA_KIND]`・`[K12HIT]` が一度も出ていない (`_CopyArray` を呼ばない unit)。よって出力の汚染 (#495) では説明できず、probe 入り build の機械語差が原因と推定 (推定。未切り分け)。
- **trace isolation の効果 (ネガコン)**: `M11_TRACE_ISOLATE=0` で unit 555 だけが oob→abort (`unresolved function call: function_535c2e`)。unit 304 は変わらない。isolation は既定 build では 555 の結果を変えている。
- 注: 途中で wasm のコピーを取り違えて「iso0 と iso1 の wasm が同一」と誤読した。これは作業側の取り違えで build の不具合ではない。上表は各構成を build し直し、wasm の md5 が構成ごとに異なることを確認した結果。

stderr 件数は `SV_ERR_LOG` 出力の行数 (`wc -l`)。

**再現**:
```
cd tools/m11
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_PE=$FL_WIN64_DIR/extracted/block00031_PE.bin
bash m11_gen_ir2.sh
M11_TRACE_ISOLATE=0 M11_INSTR_K12=1 bash m11_build.sh     # 構成は変数で切替 (既定 1 / 0)
SV_ERR_LOG=work/s1670/err.txt node trap_triage/survey_units.mjs work/s1670/out.json
```

**鮮度**: `git diff 5ff58a9e HEAD -- tools/m11` は 0 行 (本節の追加のみ)。

### #1847 [M11-12] _CopyArray (416db0) の呼出し元 site 別計測 (#1670 の残り・測定 commit 365fc973)

起点 main `47ee8a17`。`work-m11` を `tools/m11/work/` に展開、PE は `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`。`m11_gen_ir2.sh` (45 s・ldfix applied) で IR を作り直した。load は測定前 0.27・測定後 0.73 (4 vCPU)。

**変更**: `m11_ov.c` の `[CA_KIND]` に `site` と `ti` を追加し、`count==0` の return より前に出す (`M11_INSTR_K12=1` のみ)。`m11_site_probe.py` を新規追加し、IR の `function_416db0` 呼出し直前に `store volatile i32 <site>, ptr @m11_site_cur` を入れる (site は IR 出現順 1..12)。既定 build は不変。

| 構成 | build | survey | ok/miss/other/halt0/oob/noproc | stderr 行 | K12HIT | CA_KIND (site / kind) |
|---|---|---|---|---|---|---|
| 既定 (K12=0, site 無し) | 20 s | 11 s | 870/47/1/7/16/1 | 70 | 0 | 0 |
| K12=1 + site probe | 20 s | 11 s | 872/47/1/7/14/1 | 86 | 0 | 16 (site=2 のみ・全件 kind=18) |

- 既定値は #1511 節 (870/47/1/7/16/1, 70 行) と一致。K12 build の値も #1670 (872/47/1/7/14, 86 行) と一致。
- **site 2 のみ実行**: 16 件はすべて site=2 (`function_416750` 内の `416db0` 呼出し)、`ti=0x1328` (kind 18)。unit は 17 / 86 / 357 / 496 の 4 つ (各 4 回)。
- **site 1・3〜12 は survey で未実行**: `[CA_KIND]` に出ない (`count==0` の呼出しも含めて 0 件)。kind 12 は到達せず。
- **probe 方式の注意**: 呼出しを挟む probe (`void m11_site_probe(i32)` を call) は survey を変えた (ok 872→829・halt0 7→57) ため不採用。global への volatile store 版は K12 probe 無しの結果と一致 (unit 304/555 を除く)。
- **副作用 (#1670 から継続)**: 既定 build と K12 build の差は unit 304 / 555 の oob→ok のみ (site probe 有無で差なし)。
- **静的到達 (上界・直接 call のみ)**: `m11_site_probe.py --reach` で survey 結果から entry VA (RVA + 0x400000) を起点に直接 call で辿った。site 2/3/6 は 82 unit、site 5 は 78 unit、site 1/7/8/9 は unit 895/898 のみ (halt0 unit)、site 4 は unit 501、site 10/11 は unit 17/492。上界であり、実際の到達 (survey) とは一致しない (例: site 2 は上界 82 unit に対し実行は 4 unit)。
- **受入 1 の判定**: kind 12 (`416720`) の到達経路は **未特定**。直接 call の上界だけでは site 1・4・7〜11 が届かない理由を示せない (実行時に呼出し元関数が動くかは未計測)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| site 1・4〜11 の未実行理由 (呼出し元関数の実行時到達を関数単位 probe で確認) | 受入 1・2 未達 | #1894 [M11-13] |
