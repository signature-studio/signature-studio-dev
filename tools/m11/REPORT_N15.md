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
