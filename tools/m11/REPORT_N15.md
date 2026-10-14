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

## 16. #490 [M11-N15]: main HEAD の 4c3baa4 / faee5b6 状態 (部分達成, 本体 REPORT.md から移動)
main `6e5c8dac` で通常起動・survey は完走 (53/942, survey ok 870)。ネガコン (boot5 除去) は 52/942 で「元の停止に戻る」は不成立。faee5b6 の二分は逆パッチが衝突し未成立。詳細は `REPORT_N15.md` §16。
