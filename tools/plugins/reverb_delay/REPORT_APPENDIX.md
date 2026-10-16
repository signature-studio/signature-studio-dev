# reverb_delay REPORT 付録 (#523 PLG-F4-2 追補)

本体 `REPORT.md` の §12 に続く節。 250 行上限のため分割して置く。

## 13. #523 追補 (2026-10-13 · 測定起点 HEAD 986e7415 · 再測定)

- **測定起点**: main **986e7415** (§13 の測定はこの HEAD で行った。 本 PR は docs のみで engine コードは変更していない)。 `REPORT.md` §12 の起点 97f28539 は E6 修正 (b5372ec3) の親で、作業ブランチ `523-plg-f4-2-engine-lift` の起点。 両者は祖先関係 (97f28539 → 986e7415) にある。
- **素材の確認 (本 PR の fix run、2026-10-13 17:54 UTC)**: `$HOME/artifacts` には `fl-win64.tar.zst` (2.3 GB) のみ実在。 `toolchain-retdec` / `toolchain-emsdk` / `work-*` / `plugins-ott` は確認時点で不在。 したがって本 run では e2e・engine lift を再実行できず、 下表の数値は再現していない。 §13 の測定時に上記素材が揃っていたかは、 PR 本文の記録以外に確認できない。
- **run の別**: 19165 の測定は §12 (15:37:59–15:48:22 UTC、wall 10 分 23 秒、summary.csv 行あり) と §13 (wall 6 分 42 秒) の 2 回として記録されている。 条件 (IPPCODE 除外 + AVX 系 78 除外) は同じで、 wall が一致しないため同一 run の再掲ではないと判断した。 §13 の run の開始時刻は記録していない。 各 run は 1 回のみ。
- engine の正しさは示さない (到達性のみ)。 負荷 (load) は測定していない。

| engine | 条件 | lift rc | define | f80 関数 | `emcc -c` rc | lift 秒 (PR 本文) | wall (PR 本文) |
|---|---|--:|--:|--:|--:|--:|--:|
| 19165 Multiband Delay | IPPCODE 除外 + AVX 系 78 除外 (`avx_bad_ranges.py`) | 0 | 2,608 | 6 | **139 (segfault)** | 391 | 6 分 42 秒 |
| 19165 同上 | 同 + `PLUG_F80_LOWER=1` | 0 | 2,608 | 0 | **1** | 416 | 6 分 57 秒 |
| 19000 Delay 3 | `PLUG_F80_LOWER=1` (全 3,632 関数) | 0 | 4,107 | 0 | **0** | 未記録 | 2 分 7 秒 |

- 秒の列は PR 本文の値のみ。 旧版の付録は表見出しを「秒 (lift+emcc)」としていたが、本文の lift 時間 (391 s) と wall の内訳は記録になく、wall を正とする。

- **19165 segfault の位置**: `emcc` は `function_1800ceec0` の WebAssembly 命令選択 (DAG combine の `visitSTORE`) で落ちる。 同関数は x86_fp80 を含む (`final.ll` の f80 関数 6 本のうち 1 本)。 `PLUG_F80_LOWER=1` で f80 を外すと segfault は消える。
- **19165 の次の類型 (f80 lowering 後)**: `e.final.ll:273362: invalid cast opcode for cast from 'double' to 'i80'`。 `p0c/f80_lower.py` は `bitcast x86_fp80 to i80` (f80 のビット列を読む命令) を double に置換するが、`bitcast double to i80` を残す。 f80 のビット操作を扱えないことが原因と推定。 この類型は共有鎖 (`p0c/f80_lower.py`) の修正が必要で、T0/T1 の退行確認 (#523 受入条件 2) を伴うため、本 run では未修正。 **新類型 E7 (f80 ビット操作の lowering 漏れ)** として記録。 **§14 で改訂 (推定)**: 上流の lift 側の型誤りが本体の可能性が高い。 対処の順序は §14 を参照。
- **19000 の f80 lowering**: `PLUG_F80_LOWER=1` は f64 化で精度を落とす (53 bit 仮数)。 19000 の f80 関数 (`function_1800bcb00` ほか) の精度影響は未検証。 既定 (`PLUG_F80_LOWER=0`) では `emcc -c` が rc 1 のまま (REPORT §12 の既存結果)。
- 19165 の segfault の起点 (`function_1800ceec0`) と f80 6 本の内訳は測定時の `work/reverb_delay/engine19165_noipp_nobad/` (gitignore) に残したが、 本 runner の `work/` には存在しない。 再現手順は下記。

### 再現手順

```
source tools/plugins/reverb_delay/env.sh
python3 tools/plugins/reverb_delay/avx_bad_ranges.py 19165 > work/reverb_delay/bad19165.out
ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges $PWD/work/reverb_delay/bad19165.out" \
  ENGINE_TAG=_noipp_nobad bash tools/plugins/reverb_delay/engine_lift.sh 19165 1200
PLUG_F80_LOWER=1 bash tools/plugins/reverb_delay/engine_lift.sh 19000 800
```

注: `--exclude-ranges` には絶対パスを渡す (`engine_lift.sh` が `tools/plugins` へ cd するため相対パスは解決されない)。 再現には `fl-win64` に加えて `toolchain-retdec` / `toolchain-emsdk` が要る。

### 受入条件への対応 (#523)

1. 19000 は `PLUG_F80_LOWER=1` で `emcc -c` rc 0 (到達性のみ・精度未検証)。 19165 は未達 (E7)。 既定 (f80 lowering 無し) では両方未達。
2. 共有鎖 (`p0c/f80_lower.py`) は未変更のため退行確認は不要だが、E7 の修正時に必要。 未実施。
3. IPPCODE の扱い: 未決 (#38 [IPP-10] と PM 判断)。
4. LoadLibrary 結合解析: 未実施。

## 14. #523 E7 の切り分け (2026-10-13 · コード変更なし · 未再現)

- **位置付け**: §13 の E7 記述を本節で改訂する (診断は下記の推定を採る)。 測定値・rc・再現手順は §13 が正本。 本節は未再現の転記で、再測定はしていない。
- **IR 位置 (未再現・転記)**: `e.final.ll` の `function_1800ceec0` 内、ブロック `dec_label_pc_1800ceffe` の `bitcast x86_fp80 %12 to i80` → `trunc i80 to i64` → `inttoptr` (行 273381・273392 付近)、`sext i32 to i80` → `bitcast i80 to x86_fp80` (行 273480・273633 付近)。 行番号は f80 lowering 前基準。 別経路の同型は行 348058 以降。 `%12` は `load x86_fp80, x86_fp80* %11`、`%11 = bitcast ptr %rcx to x86_fp80*` と記録されているが、IR 抜粋は未確認。
- **推定原因 (推定)**: `%11` のポインタ型が f80 と推定されたのは lift 側 (RetDec の型推定) の誤りの可能性が高い。 整数スロットを f80 として読んでいるなら、`bitcast` 以前に型が違う。 `p0c/f80_lower.py` の通常モード (`token_lower`) は `x86_fp80`→`double` の型名置換と f80 定数・intrinsic 名の変換を行うが、`bitcast` 命令を書き換える規則を持たない。 そのため `bitcast x86_fp80 to i80` が `bitcast double to i80` になり、i80 を含む規則が無いまま残る。 これは `f80_lower.py` のコードを読んだうえの推定で、実行による確認はしていない。
- **対処方針 (未実施)**: (a) lift 側の型修復で `%11` の load を `i64` に差し替える (先に試す)。 (b) `f80_lower.py` に i80 ビット列の規則を足す (共有鎖のため T0/T1 退行確認が必要)。
- **残りの類型 (転記・未再現)**: 同 IR で `do not know how to soften fp_extend` と `no libcall available for fp_round with type f80` が出る (`f80_lower` 無し時と記録)。 E7 を消しても f80 の libcall が残るため、19165 が `emcc -c` rc 0 になるには E7 の修正に加えて f80 の扱いを決める必要がある。

## 15. #523 E7 の engine-local 修復の試行 (2026-10-13 · 実測 · 負の結果)

- **HEAD**: `80c32a06` (origin/main 起点の作業ブランチ。 測定コードは共有鎖を含めて未変更)。
- **再現 (lift + emcc, `ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges <78 件>" ENGINE_TAG=_noipp_nobad engine_lift.sh 19165 900`)**: summary `19165,2000,0,2608,6,241,139,0,139,612,2,445,0,608,2606`。 lift rc 0 / define 2,608 / f80 6 / `emcc -c` rc **139** (segfault) / wall 10 分 28 秒 / load 1.15 (5 分平均 0.99)。 §13 の 2 回目 (6 分 42 秒) と一致し、E7 の `invalid cast` は既定の経路では出ない (segfault が先に出る)。
- **試行 (engine-local)**: `e.final.ll` の x87 `load x86_fp80` (26 箇所) を `load i80` + `bitcast i80 to x86_fp80` に置換して `emcc -c` を再実行した。 結果は **rc 139 (segfault)** のまま。 IR 構文は有効になり、`do not know how to soften fp_extend` / `no libcall available for sint_to_fp with type f80` が出た。 置換は 7 秒で終わる再実行で、lift の再実行は不要。
- **判断**: segfault は `load` の型だけでは消えない。 §14 の推定 (E7 = 型誤り) は、少なくとも単独では成立しなかった。 残る経路は (a) f80 の libcall 不足 (`fp_extend` / `sint_to_fp` / `fp_round`) の共有鎖での扱い、(b) `function_1800ceec0` の DAG combine の segfault。 いずれも共有鎖 (`p0c/f80_lower.py` / lift) の変更になり、T0/T1 の退行確認 (#523 受入条件 2) が必要。 engine-local の試行は本節で打ち切り、修正コードは commit しない。

## 16. #523 segfault の切り分け (2026-10-13 · 実測 · 診断のみ · コード変更なし)

- **HEAD**: `13bdc5fe` (origin/main)。 測定入力は §15 と同じ `80c32a06` 系の engine lift 出力 (lift 側の差分 0。 `git diff 512c53ab 13bdc5fe -- tools/plugins/reverb_delay tools/plugins/lift tools/plugins/p0c` は空)。
- **再現 (19165, IPPCODE 除外 + AVX 系 78 除外)**: summary `19165,2000,0,2608,6,148,139,0,139,601,...`。 lift rc 0 / define 2,608 / f80 6 / `emcc -c` **rc 139**。 §15 と define・f80・rc が一致。 unimpl helper は 148 (§15 の 241 とは不一致。 未切り分け)。 601 は lift 段の秒数 (`engine_lift.sh` の `t1-t0`)。
- **スタック上限は原因でない**: `ulimit -s unlimited` でも rc 139。 クラッシュは `WebAssembly Instruction Selection` 中の `DAGCombiner::visitSTORE` (LLVM の DAG combine)。
- **落ちる関数は 2 つ**: 関数単位でスタブ化 (`unreachable` 置換・診断専用・コミットせず) して `emcc -c` を再実行したところ、`function_1800ceec0` (f80 参照 859 箇所) を外すと次は `function_1801439a0` (f80 参照 879 箇所) で落ち、両方を外すと segfault は消えた (rc 1)。 いずれも x87 を大量に含む。
- **両スタブ外し後の残り (ferror-limit=0)**: `emcc -c` rc 1 / error 296 件。 内訳は `no libcall available for fmul with type f80` 134、`fadd` 116、`do not know how to soften fp_extend` 22、`fp_round` 19、`sint_to_fp` 4、`frem` 1。 segfault 以外の未解決はすべて f80 の libcall 不足。
- **判断**: 19165 の `emcc -c` rc 0 の前提は「f80 の扱い」の 1 点に集約される。 f80 を f64 に下げる (`PLUG_F80_LOWER=1`) と segfault は消えた (§13 で 19165 rc 1 = E7)。 一方で E7 の型誤り推定は §15 で単独では成立しなかった。 次の判断は PM 側で、(a) f80 を持つ関数の扱い (精度を落とす lowering か、関数単位の除外か)、(b) x87 を含む 2 関数の DAG combine 回避 (LLVM 側・wasm backend の回避策) のどちらを取るか。
- **注意**: スタブ版の wasm は生成していない (関数を消すため miscompile)。 本節の数値は到達性の診断であり、engine の正しさは示さない。

- **注 (2026-10-15)**: 本節の「f80 6」は `engine_lift.sh` の summary 第 5 列 (旧判定: チャンク全体で `x86_fp80` を見る) の値で、`0x1801e12fc` を誤って含む。 本体基準の値は 19165 で 5 本 (§17)。 rc と define の値は変わらない。

## 17. #523 f80 関数の関数単位除外による部分集合の `emcc -c` (2026-10-15 · 実測 · 到達性のみ)

- **測定 commit**: `81aafb874` (main `5b1f9dffc` を取り込んだ merge commit。 コードを変えた最後の commit。 `engine_f80_stub.py` は関数名を解釈できないとき exit≠0 で止まり、`engine_f80_subset.sh` は stub 失敗時に古い TSV を読まずに止まる)。 旧測定 commit `6a9893ac0` からの code 差分は 17 files (`git diff --stat 6a9893ac0 81aafb874 -- tools/plugins/lift tools/plugins/p0c tools/plugins/reverb_delay`。 内訳と既定経路での扱いは下の注)。 f80 段の 6 files は差分 0 (`git diff 6a9893ac0 81aafb874 -- tools/plugins/reverb_delay/engine_f80_stub.py tools/plugins/reverb_delay/engine_f80_subset.sh tools/plugins/reverb_delay/engine_f80_gate.sh tools/plugins/reverb_delay/engine_f80_nc.sh tools/plugins/reverb_delay/engine_lift.sh tools/plugins/reverb_delay/env.sh` は空)。 lift 鎖は `git diff 42357b73e 6a9893ac0 -- tools/plugins/lift tools/plugins/p0c tools/plugins/reverb_delay/engine_lift.sh` が空で、差分は main 取り込み (81aafb874) で入った。 そのため両 engine を 81aafb874 で再測定した (下表・下の実測値)。 `git diff 81aafb874 HEAD -- tools/plugins/reverb_delay/*.py tools/plugins/reverb_delay/*.sh tools/plugins/lift tools/plugins/p0c` は空 (以降の commit は `.md` のみ)。
- **方法**: `engine_f80_stub.py` が `e.fixcmp.ll` の `x86_fp80` を含む関数の定義を `declare` に置換する (判定は `define` から対応する `}` までの本体に限る)。 除外は関数単位で、名前・VA・理由を `f80_excluded.tsv` に記録する。 `engine_f80_subset.sh` が部分集合を `emcc -c` し、`engine_f80_gate.sh` が gate を判定する。 gate: rc 0 かつ define 数が除外数だけ減る かつ 除外集合 = 本体に f80 を含む define 集合 (stub と別算法の awk で求める) かつ 部分集合の本体 f80 = 0。 NC は実 IR で `engine_f80_nc.sh <e.fixcmp.ll の絶対パス> <OUT>` を回す。 base (無改変) は PASS、nc1 (件数を保って非 f80 関数を除外名に入れる) と nc2 (除外を 1 件減らす) は FAIL を要求する。
- **素材**: `$ARTIFACTS_DIR` に `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` が実在することを確認した (2026-10-15 の run)。 `env.sh` が `fl-win64` の PE を展開。 RetDec は [RETDEC] の `retdec-decompiler` (v5.0)、emcc は [EMSDK] (6.0.12。 `docs/REFERENCES.md` の pin と一致) を使った。 toolchain の tarball は展開していない (runner に既存の `/opt` 配置を使用)。

| engine | 条件 | lift rc | define | f80 関数 (本体基準) | NC: 無改変 `emcc -c` | 部分集合 `emcc -c` | 部分集合 define | gate |
|---|---|--:|--:|--:|--:|--:|--:|---|
| 19000 Delay 3 | 全 3,632 関数 (IPPCODE 対象外) | 0 | 4,107 | 1 | 1 | **0** | 4,106 | PASS |
| 19165 Multiband Delay | IPPCODE 除外 + AVX 系 78 除外 (`avx_bad_ranges.py` の 78 範囲) | 0 | 2,608 | 5 | 139 (segfault) | **0** | 2,603 | PASS |

- **除外 VA**: 19000 は `0x1800bcb00` の 1 本。 19165 は `0x18006fea0` / `0x1800ceec0` / `0x1801434a0` / `0x1801439a0` / `0x1801dbbe0` の 5 本。 segfault の 2 関数 (`0x1800ceec0`・`0x1801439a0`) は除外集合に含まれる。
- **旧 stub との差**: 旧 stub (`b2fc00a71`) は 19165 で f80 6 本・define 2,602 を出した。 6 本目の `0x1801e12fc` は本体に `x86_fp80` を持たず、後続の `declare` の `x86_fp80` で誤除外されていた。 旧 stub の表はこの誤除外を含むため、本節の値で置き換えた。
- **部分集合の残存 `x86_fp80`** (`grep -n 'x86_fp80' e.sub.ll`): 19000 は 0 行。 19165 は 2 行で、`declare void @__frontend_reg_store.fpr(i3, x86_fp80)` と `declare x86_fp80 @__frontend_reg_load.fpr(i3)` (いずれも define の外)。 呼出は両 engine とも 0 件 (`grep -c 'call.*__frontend_reg_\(load\|store\)' e.sub.ll` → 0)。
- **実 IR の NC** (`engine_f80_nc.sh`。 出力行をそのまま転記):

```
19000 base f80_excluded=1,define_full=4107,define_sub=4106,f80_body_full=1,f80_body_sub=0,excl_set_eq_f80_body=same,emcc_c_rc=0,gate=PASS
19000 nc1  f80_excluded=1,define_full=4107,define_sub=4106,f80_body_full=1,f80_body_sub=0,excl_set_eq_f80_body=diff,emcc_c_rc=0,gate=FAIL   (除外名: "?CreateEngine@@YAPEAUAEffect@@P6A_JPEAU1@HH_JPEAXM@Z@Z")
19000 nc2  f80_excluded=0,define_full=4107,define_sub=4106,f80_body_full=1,f80_body_sub=0,excl_set_eq_f80_body=diff,emcc_c_rc=0,gate=FAIL
19165 base f80_excluded=5,define_full=2608,define_sub=2603,f80_body_full=5,f80_body_sub=0,excl_set_eq_f80_body=same,emcc_c_rc=0,gate=PASS
19165 nc1  f80_excluded=5,define_full=2608,define_sub=2603,f80_body_full=5,f80_body_sub=0,excl_set_eq_f80_body=diff,emcc_c_rc=0,gate=FAIL   (除外名: VSTPluginMain)
19165 nc2  f80_excluded=4,define_full=2608,define_sub=2603,f80_body_full=5,f80_body_sub=0,excl_set_eq_f80_body=diff,emcc_c_rc=0,gate=FAIL
```

- **実測時間と負荷** (81aafb874 の run。 19000 は 02:29:52–02:32:46 UTC、19165 は 02:33:12–02:44:03 UTC): 19000 は lift 167 s (summary 第 10 列)・wall 2 分 50 秒・部分集合 (stub・emcc・gate) sec=2。 19165 は lift 634 s・wall 10 分 49 秒・部分集合 sec=10。 負荷は uptime の 1 分平均で、19000 の lift 終了時 0.98、19165 の lift 終了時 1.07 (nproc 4)。 測定 commit `6a9893ac0` の run は lift 126 s・457 s で、今回は両方とも長い (原因は未確認)。 rc・define・f80・unimpl helper (17・136)・gate の値は前回と一致。
- **summary の列の注記**: `engine_lift.sh` の summary 第 5 列 (f80) は旧判定 (`re.split` のチャンク全体で `x86_fp80` を見る) で、19165 で 6 を出す (本体基準は 5)。 §7・§12・§15・§16 の「f80 6」は同じ判定の値。 第 6 列 (unimpl helper) は `e.simd.log` の最初の `unimplemented N`。 本 commit の run では 19000 = 17、19165 = 136。 #523 本文の 93 は REPORT §7 の表から転記された値で、測定 commit と構成の記録が無い。 §16 の 148 と §15 の 241 も別の測定で、切り分けは未了 (#3447 受入 5)。

- **6a9893ac0 → 81aafb874 の 17 files と既定経路での扱い** (静的確認。 呼出元は `grep -rn` で確認):
  - `lift/lift_ranges.sh` (+5)・`lift/passes/m11_simd2.py` (+5/−1)・`lift/passes/SOURCES.txt` (+1): `PLUG_COMIS_FLAGS=1` (既定 0) のときだけ動く opt-in。 未設定では旧出力と同じ。
  - `lift/passes/comis_flags.py`・`lift/passes/test_comis_flags.py` (新規): 上記 opt-in からだけ呼ばれる (test は既定経路外)。
  - `p0c/k80_argfix.py`: `lift/passes/fix_xmm_args.py` 経由でだけ呼ばれ、同 pass は `PLUG_XMMARG=1` (既定 0) のときだけ `lift_ranges.sh` から実行される。
  - `p0c/p0c4_abi_e2e.py`・`p0c/ucomi_ret_check.py` (新規)・`p0c/k80_unmeasured.py` (新規): p0c の e2e と単独の計測。 lift 経路から呼ばれない。
  - `p0c/REPORT.md`・`p0c/REPORT_APPENDIX_H.md`・`p0c/REPORT_APPENDIX_I.md`・`reverb_delay/REPORT.md`・`reverb_delay/REPORT_APPENDIX.md`・`reverb_delay/REPORT_APPENDIX_3445.md`: 文書。
  - `reverb_delay/ipp_callers.py`・`reverb_delay/shell_bind.py` (新規): 単独の静的解析道具。 engine 段の script から呼ばれない。
  - 既定経路の出力は変わらないと静的に判断した。 ただし lift 鎖の変更を含むため、測定は 81aafb874 で取り直した。

### 受入条件への対応 (#523・本節)

1. 19000 は `0x1800bcb00` の 1 本、19165 は 5 本を関数単位で除外して `emcc -c` rc 0 (到達性のみ)。 gate と実 IR の NC を付けた。 除外した f80 関数の lift は #3447。 無改変の `emcc -c` は 19000 が rc 1、19165 が rc 139。
2. 共有鎖 (`lift/`・`p0c/`) は変えていないため、T0/T1 の退行確認は要らない。 共有鎖を変える場合は #3447 で実施する。
3. IPPCODE の扱い: #3445 ([PLG-F4-3])。
4. LoadLibrary 結合解析: #3446 ([PLG-F4-4])。

- 19165 の部分集合は、IPPCODE 272 関数と AVX 系 78 関数を前段で除いた 2,000 関数 (`ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges …"`) を lift した IR から、さらに f80 5 本を除いたもの。 define 2,608 には range 内部に切り出された define (§7 の 608) を含む。 78 関数 (E5) は本 PR の部分集合に入っていない (未 lift。 起票先は #3447 の受入 4)。
- **注意**: 除外した関数は外部宣言になるため、部分集合の挙動は元の engine と無関係。 正しさ・精度・f80 の扱いは未検証 (到達性のみ)。 19000 の既存 `PLUG_F80_LOWER=1` (精度低下あり) とは別経路。
- **再現手順** (`source tools/plugins/reverb_delay/env.sh` の後):

```
bash tools/plugins/reverb_delay/engine_lift.sh 19000 800
EMSDK_ENV="$EMSDK_DIR/emsdk_env.sh" bash tools/plugins/reverb_delay/engine_f80_subset.sh 19000
bash tools/plugins/reverb_delay/engine_f80_nc.sh "$PWD/tools/plugins/work/reverb_delay/engine19000/e.fixcmp.ll" "$PWD/tools/plugins/work/reverb_delay/nc19000"
python3 tools/plugins/reverb_delay/avx_bad_ranges.py 19165 > "$PWD/tools/plugins/work/reverb_delay/bad19165.out"
ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges $PWD/tools/plugins/work/reverb_delay/bad19165.out" ENGINE_TAG=_noipp_nobad bash tools/plugins/reverb_delay/engine_lift.sh 19165 900
ENGINE_TAG=_noipp_nobad EMSDK_ENV="$EMSDK_DIR/emsdk_env.sh" bash tools/plugins/reverb_delay/engine_f80_subset.sh 19165
bash tools/plugins/reverb_delay/engine_f80_nc.sh "$PWD/tools/plugins/work/reverb_delay/engine19165_noipp_nobad/e.fixcmp.ll" "$PWD/tools/plugins/work/reverb_delay/nc19165"
```

注: `--exclude-ranges` には絶対パスを渡す (`engine_lift.sh` が `tools/plugins` へ cd するため)。 `EMSDK_DIR` は [EMSDK] の展開先。 再現には `fl-win64`・`toolchain-retdec`・`toolchain-emsdk` が要る。

## 18. #3446 (PLG-F4-4) 殻 ↔ engine DLL の結合方式 (2026-10-15 · 静的解析 · 測定 commit 1a72e7dbf)

- **既知類型との関係**: 該当なし (逆アセンブル・PE 解析のみ。 lift 鎖・IR は変更していない)。 測定は `tools/plugins/reverb_delay/shell_bind.py` (本節で追加。 gate 付き)。
- **素材**: `fl-win64` のみ (`$RUNNER_TEMP/fl-win64/extracted/block{18999,19000,19164,19165}_PE.bin`)。 engine の正しさや実行時の挙動は見ていない (範囲外)。
- **再現**: `FL_WIN64_DIR=<展開先> python3 tools/plugins/reverb_delay/shell_bind.py 18999 19000` (Delay 3) と `... 19164 19165` (Multiband Delay)。 両方とも rc 0・判定 `OK`。 NC: `--engine-name Nope_x64.dll` で rc 1・判定 `FAIL ['load', 'entry']` (経路と間接呼出が見つからないと落ちる)。

### 18-1. 結論 (先出し)

1. **結合方式は LoadLibrary + GetProcAddress (名前引き) で、殻が engine を読み込む。** engine 側から殻への関数ポインタ渡しは無い。 殻が自分の audioMaster コールバックの関数ポインタを engine の入口に渡し、engine が返す `AEffect*` を殻が保持する (VST2 の入口形)。
2. **入口の名前は 26 通りの候補表を総当たりする。** 殻は `VstPluginMain` / `VSTPluginMain` / `main` / `maiN` … (大文字小文字の違いを含む 26 件、Delphi UnicodeString) を順に `GetProcAddress` し、最初に成功した名前を使う。 両 engine では大文字小文字を区別した最初の一致が `VSTPluginMain` (表の 2 番目)。
3. **engine の入口は両 engine で別物**: Delay 3 engine (19000) の `VSTPluginMain` (RVA 0xe9a0) は `jmp ?CreateEngine` (RVA 0xe830) の trampoline。 Multiband Delay engine (19165) の `VSTPluginMain` (RVA 0x1d77f0) は本体 (`push rbx` で始まる)。 19165 の export は `VSTPluginMain` / `main` のみ。
4. **呼出境界 (殻 → engine)**: 入口は引数 1 つ (rcx = 殻のコールバック)、戻り値 rax = `AEffect*`。 殻は `AEffect*` を自分の object の `+0x9b4` に保存し、以後 `call [rax+8]` (AEffect.dispatcher、64-bit VST2 の配置) で呼ぶ。 dispatcher の初回呼出は `edx=0` (effOpen)・`r8=0`・`r9=0`・`[rsp+0x20]=NULL`・`[rsp+0x28]=0.0f`。

### 18-2. 殻の import と読込系 API の呼出位置 (shell_bind.py [1])

| 殻 | thunk (`jmp [IAT]`) の呼出位置 | 件数 |
|---|---|--:|
| 18999 Delay 3 | LoadLibraryW 0x44077b ほか 8 箇所 / LoadLibraryA 0x418cf1 / LoadLibraryExW 0x4158ab / GetProcAddress 10 箇所 | W 9・A 1・ExW 1・Gpa 10 |
| 19164 Multiband Delay | LoadLibraryW 0x4407db ほか 8 箇所 / LoadLibraryA 0x418cf1 / LoadLibraryExW 0x4158ab / GetProcAddress 10 箇所 | W 9・A 1・ExW 1・Gpa 10 |

- 殻の IAT には `kernel32!LoadLibraryA` / `LoadLibraryW` / `LoadLibraryExW` / `GetProcAddress` / `FreeLibrary` / `GetModuleHandleW` が並ぶ。 engine 経路の `LoadLibraryW` 呼出は 1 箇所 (下の経路)。 他の呼出はそれぞれ別の DLL (FL 本体側の API 解決) で、本節の対象外。

### 18-3. engine 名 → LoadLibraryW の経路 (shell_bind.py [2])

| 殻 | engine 名の UnicodeString | 参照 (`lea`, 1 箇所) | 直接 call で LoadLibraryW へ届く経路 |
|---|---|---|---|
| 18999 | `engine_x64.dll` (VA 0x6e9b44、長さ 14) | 0x6e999f (関数 0x6e9940) | 0x6e9940 → 0x6dcb80 → 0x440750 → `call LoadLibraryW` @0x44077b |
| 19164 | `Engine_x64.dll` (VA 0x6e6504、長さ 14) | 0x6e632f (関数 0x6e62d0) | 0x6e62d0 → 0x6d59b0 → 0x4407b0 → `call LoadLibraryW` @0x4407db |

- 0x440750 (18999 側) は、引数 `edx=0x8000` を `SetErrorMode` 相当 (0x41d520) で設定し、その間に `LoadLibraryW` を呼ぶ wrapper (0x41d520 の同定と 0x8000 = SEM_NOOPENFILEERRORBOX は SDK の定数からの推定)。 19164 側の 0x4407b0 も同形と推定 (未確認)。
- **未確定 → 解決 (§18-7)**: `LoadLibraryW` の引数は `obj+0x2a6` (18999 では 0x6dd0fe / 0x6dd0f0 で `UnicodeString` に複写)。 `+0x2a6` を指す直接の書込み命令は無く、0x6d43fc の `rep movsq` (呼出元フレームのレコードの丸ごと複写) で埋まる。 書込元と読み込まれる DLL 名は §18-7 に記録。

### 18-4. 候補表と解決名 (shell_bind.py [3][4])

- 候補表: 18999 は 26 件 (VA 0x73c468–0x73c530、8 バイト間隔、`.data` のポインタ配列)、19164 は 26 件 (VA 0x73b7f8–0x73b8c0)。 順序は両殻で同じ: `VstPluginMain, VSTPluginMain, main, maiN, maIn, maIN, mAin, mAiN, mAIn, mAIN, Main, MaiN, MaIn, MaIN, MAin, MAiN, MAIn, MAIN, vstpluginmain, VSTPluginMain, VSTPluginmain, VSTpluginmain, VSTpluginMain, vstPluginMain, vstPluginmain, vstpluginMain`。
- 候補表を参照する関数: 18999 0x6dc2d0 (`lea rbx,[rip+…]` で表の先頭 0x73c468 を参照)、19164 0x6d5100 (表の先頭 0x73b7f8 付近)。 いずれも直接 call 2 段の先で `GetProcAddress` の thunk を呼ぶ (18999: 0x6dc2a0 → 0x41d1b0 の 0x41d1de、19164: 0x41d1d0 の 0x41d1fe)。 wrapper (0x41d1b0 / 0x41d1d0) は、第 2 引数の上位 16 bit が 0 なら序数として直接渡し、そうでなければ文字列を変換してから渡す (変換関数の同定は未了)。
- 18999 では 0x6dc2d0 の呼出元は仮想メソッド (0x6dff80、vtable 上の位置 0x6db200 を `.text` 内で確認) で、0x6dff80 が明示名 (r8) を先に試し、失敗時に 0x6dc2d0 の総当たりへ回る。 19164 の仮想メソッド経由の呼出は未確認。
- 解決名: 両 engine の export と大文字小文字を区別して照合すると、最初の一致は `VSTPluginMain` (表の 2 番目)。 `VstPluginMain` (表の 1 番目) は両 engine に無い。

### 18-5. 呼出境界の実測 (shell_bind.py [5][6])

| 項目 | 18999 (Delay 3) | 19164 (Multiband Delay) |
|---|---|---|
| 入口の呼出 (解決した FARPROC) | 0x6dd3d5 `call [rbp+0x338]` (関数 0x6dcb80) | 0x6d6205 `call [rbp+0x338]` (関数 0x6d59b0) |
| 引数 (rcx) | `lea rcx,[rip-0x18d5]` → 0x6dbb00 (殻のコールバック) | `lea rcx,[rip-0x18d5]` → 0x6d4930 (殻のコールバック) |
| 戻り値 | rax → 0x6dd3e2 `mov [rcx+0x9b4], rax` | rax → 0x6d6212 `mov [rcx+0x9b4], rax` |
| コールバックの先頭 | `push` 6 個・`mov [rbp+0x30],rcx` … (rcx=effect、edx=opcode、r8d=index、r9=value、残りはスタック。 0x6dbb0f〜0x6dbb1a) | 同形 (0x6d4930 から push 6 個・`sub rsp,0x78`) |
| dispatcher 呼出 | 0x6dd6e9 `call [rax+8]` (rcx=`[obj+0x9b4]`、edx=0、r8=0、r9=0、`[rsp+0x20]`=0、`[rsp+0x28]`=0.0f) | 0x6d6519 `call [rax+8]` (同じ設定) |
| engine 側の入口 (shell_bind.py [6]) | `VSTPluginMain` = `jmp ?CreateEngine` (RVA 0xe9a0 → 0xe830)。 `CreateEngine` の引数型は `AEffect* (*)(audioMasterCallback)` (export 名のマングリングから) | `VSTPluginMain` = 本体 (RVA 0x1d77f0、`push rbx`)。 `CreateEngine` の export は無い |

- 呼出規約は Win64 (rcx/rdx/r8/r9 + スタック)。 戻り値は rax。 engine → 殻の方向の呼出 (engine が殻のコールバックを呼ぶ箇所) は本節で測っていない (範囲外)。
- `[rax+8]` が dispatcher であることは、VST2 SDK の 64-bit `AEffect` 配置 (magic: int32、dispatcher: offset 8) からの推定。 配置の実測はしていない。

### 18-6. 検証・限界

- 検証範囲: 殻と engine の PE 上の静的な呼出関係、export 名の照合、呼出の引数準備の静的読取り。 範囲外: 実行 (Wine 等での起動)、engine の正しさ、wasm へのリンク (#201 の出口条件側)。
- NC (ネガティブコントロール): 存在しない engine 名 `Nope_x64.dll` で経路と間接呼出の判定が落ちる (`FAIL ['load', 'entry']`、rc 1)。
- 鮮度: 測定 commit 1a72e7dbf。 以後の差分は本節の文書のみ (`git diff 1a72e7dbf HEAD -- tools/plugins/reverb_delay/shell_bind.py` の出力は 0 行)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 殻 DLL のフォルダ (`dir`) の実行時の値。 DLL 名 (`engine_x64.dll` / `Engine_x64.dll`) は §18-7 で確定 | 完全な読込パスは実行時にしか決まらない | #201 の差分試験 (出口条件 3)。 確認方法: Wine で `WINEDEBUG=+loaddll` を付けて殻を読み込ませ、engine の読込パスを記録 (未実施) |
| `obj` (0x6dcb80 の self) の実行時の値。 静的には `.text` 内の定数を指す (§18-7) | 書込先 `obj+0x98` の object が実行時に書込み可能かは未確認 | 同上 (実行時 trace で `obj+0x2a6` の内容を記録) |
| 殻 ↔ engine の実行時検証 (dispatcher 呼出の戻り値、コールバックの実際の引数) なし | ABI は静的推定 | #201 の差分試験 (出口条件 3) |
| 19164 の名前走査の仮想メソッド経由の呼出元 (18999 の 0x6dff80 相当) 未確認 | 19164 の解決経路の一部 | 同上 (本 PR の範囲外) |
| engine → 殻の呼出 (engine が殻のコールバックを呼ぶ箇所) の ABI 未測定 | 双方向の境界の一部 | #523 系 (PLG-F4-2、engine の lift 側) |

### 18-7. obj+0x2a6 の書込元と LoadLibraryW の実引数 (#3625 · 静的解析 · 測定 commit 69ddd3081)

- **結論**: `LoadLibraryW` の引数 `obj+0x2a6` は、呼出元のフレームにある 0x644 バイトのレコード R を `obj+0x98` へ丸ごと複写した結果で、`R+0x20e` (呼出元の `[rbp+0x26a]`) が入る。 書込元は殻の `rep movsq` (18999 0x6d43fc、19164 0x6cd22c)。 `R+0x20e` の中身は `dir + "engine_x64.dll"` (19164 は `Engine_x64.dll`) で、`dir` は殻 DLL 自身のフォルダ。 **読み込まれる DLL 名は両殻で確定**。 フォルダ部分の実値は静的には決まらない (§18-6 の未解決)。
- **素材・再現**: `fl-win64` のみ (`block18999` / `19000` / `19164` / `19165`)。 各段は `FL_WIN64_DIR=<展開先> python3 tools/plugins/reverb_delay/loadpath_trace.py <block> fn <VA>` で出す (`refs` / `disp` / `calls` / `bytes` も同じ)。 `shell_bind.py 18999 19000` と `19164 19165` は HEAD (69ddd3081) で rc 0・判定 `OK` (19164 は 13.7 秒)。

| 段 | 18999 (Delay 3) | 19164 (Multiband Delay) |
|---|---|---|
| (a) 呼出元のレコード R (0x644 B) の確保 | 0x6e9940: `lea rcx,[rbp+0x5c]`・`mov edx,0x644`・`call [rax]` (0x6e9978〜0x6e9988) | 0x6e62d0: 0x6e6308〜0x6e6318 (同形) |
| (b) engine 名の連結 | `lea r8` 0x6e999f → 0x6e9b44 `engine_x64.dll` → `call 0x410400` (`_UStrCat`) → `[rbp+0x38]` | 0x6e632f → 0x6e6504 `Engine_x64.dll` → `call 0x410400` → `[rbp+0x38]` |
| (c) `R+0x20e` (= `[rbp+0x26a]`) への複写 | 0x6e99ab `lea rcx,[rbp+0x26a]` → `call 0x432860` (`r8=0x104`) | 0x6e633b `lea rcx,[rbp+0x26a]` → `call 0x432880` (`r8=0x104`) |
| (d) 殻本体の呼出 (`r9 = R`) | 0x6e9a26 `lea r9,[rbp+0x5c]` → `call 0x6dcb80` (0x6e9a3c) | 0x6e63b6 `lea r9,[rbp+0x5c]` → `call 0x6d59b0` (0x6e63cc) |
| (e) `obj` への複写 (**書込元**) | 0x6dccbb `call 0x6d42a0` → 0x6d43f0 `lea rdi,[rax+0x98]`・0x6d43f7 `ecx=0xc8`・0x6d43fc `rep movsq`・0x6d43ff `movsd` (計 0x644 B) | 0x6d5aeb `call 0x6cd0d0` → 0x6cd220 `lea rdi,[rax+0x98]`・0x6cd22c `rep movsq`・0x6cd22f `movsd` |
| (f) `LoadLibraryW` へ | 0x6dd0fe `lea rdx,[obj+0x2a6]` → 0x6dd11c `call 0x440750` → 0x44077b `call LoadLibraryW` | 0x6d5f2e `lea rdx,[obj+0x2a6]` → 0x6d5f4c `call 0x4407b0` → 0x4407db `call LoadLibraryW` |

- **オフセットの対応**: `0x26a − 0x5c = 0x20e`、`0x98 + 0x20e = 0x2a6`。 `0x644 = 0xc8 × 8 + 4`。 (e) は R を先頭から全部複写するので、R のどの領域も `obj+0x98` 以降へ同じ位置で写る。
- **`dir` の作り方 (両殻同形)**: 18999 では `GetModuleFileNameW([0x745298], …, 0x104)` (0x6d16bc〜0x6d16cd) → `0x4100d0` (WCHAR → UStr) → `0x4324a0` (`ExtractFilePath`: `0x441380` が末尾から区切り集合を検索し、`Copy(s,1,pos+1)` で末尾の `\` を残す) → `0x40edb0` で変数 `0x74f538` へ代入。 19164 は 0x6ca4d0 で同形。 区切り集合は 32 バイトの bitmap (0x4324e4 / 0x432504) で、ビット 92 (`\`) と 58 (`:`) だけが立つ。
- **HInstance `[0x745298]`**: 両殻で同じ RTL の DllEntry `0x418a10` が `r9d == 1` (DLL_PROCESS_ATTACH) のとき `r8` (= `hinstDLL`) を保存する (0x418a39)。 呼出元 0x6ed490 (DllMain 相当) が `rcx` → `r8`・`edx` → `r9d` に載せ替えて呼んでいることを確認済み。 よって `GetModuleFileNameW` は殻 DLL 自身の絶対パスを返す。
- **連結と打切り**: `0x410400` は左辺の後ろに右辺を複写する (`dest + len×2`) `_UStrCat`。 `0x432860` / `0x432880` は `0x4327c0` / `0x4327e0` で cap (260 WCHAR) まで複写して NUL 終端する。 殻 DLL のフォルダ長が 246 WCHAR 以上だと末尾の `engine_x64.dll` が切れる (限界)。
- **`obj` の実体は静的に未確定**: 18999 の `obj` (0x6dcb80 の rcx) は `mov rcx,[0x6dad80]` (0x6e9a12) で読み、その値 `0x6dae48` は `.text` 内 (セクションフラグ 0x60000020 = 読み取り専用) の表を指す。 実行時にそれが書込み可能な object かは確認できない。 ただし (e)(f) の鎖は全て `obj` 相対 (`obj+0x98+0x20e`) なので、`obj` の値によらず「`obj+0x2a6` = `R+0x20e`」は成り立つ。
- **検証範囲**: 静的な逆アセンブルのみ。 実行 (Wine 等) はしていない。 `dir` の実値、`obj` の実値、LoadLibraryW の成否は範囲外。
- **測定 commit と差分**: 測定は 69ddd3081 (`loadpath_trace.py` を追加した commit)。 `git diff 69ddd3081 HEAD -- tools/plugins/reverb_delay/shell_bind.py tools/plugins/reverb_delay/loadpath_trace.py` の出力は 0 行。

## 19. #5039 (PLG-F4-8) f80 → f64 lowering の既定化と 19000 / 19165 の全件 `emcc -c` (2026-10-16 · 実測 · 到達性のみ)

- **測定 commit**: `3376c8471` (`engine_lift.sh` の既定を `PLUG_F80_LOWER=1` にした commit。 コードを変えた最後の commit)。 起点は main `36cb9906b` (E7 修正 #5858 取り込み済み)。
- **方式**: `p0c/f80_lower.py` による x86_fp80 → f64 lowering (D28 と同系列。 `docs/DECISIONS.md`)。 **精度**: f80 の 64 bit 仮数を 53 bit に下げる。 native x87 とビット一致しない。 この精度差は gate の外の記録であり、正しさは未検証 (到達性のみ)。
- **変更**: `tools/plugins/reverb_delay/engine_lift.sh` で `PLUG_F80_LOWER` を既定 1 にした (従来は未設定で 0)。 dynamics / distortion と同じ既定。 `PLUG_F80_LOWER=0` を明示すれば従来の経路 (19000 rc 1、19165 は E7 / segfault) に戻る。
- **素材**: `fl-win64` / `toolchain-retdec` (`/opt/retdec`) / `toolchain-emsdk` (`/opt/emsdk`) を使用。

| engine | 条件 | lift rc | define | f80 関数 (本体基準) | `emcc -c` rc | lift 秒 | gate (`engine_f80_subset.sh`) |
|---|---|--:|--:|--:|--:|--:|---|
| 19000 Delay 3 | 全 3,632 関数 (既定 `PLUG_F80_LOWER=1`) | 0 | 4,107 | 0 | **0** | 105 | PASS (除外 0) |
| 19165 Multiband Delay | IPPCODE 除外 + AVX 系 78 除外 (既定 `PLUG_F80_LOWER=1`) | 0 | 2,608 | 0 | **0** | 374 | PASS (除外 0) |

- **除外 (受入 1 の「除外理由と VA」)**: 19165 は IPPCODE 272 関数 (`--exclude IPPCODE`。 扱いは #3445) と AVX 系 78 関数 (`avx_bad_ranges.py 19165` の 78 範囲。 理由は E5 = AVX2/AVX-512 命令の変換未実装。 起票先は #3447 受入 4 / #5040)。 19000 は除外なし。 78 範囲の VA 一覧は同スクリプトの出力で再生成できる (本 REPORT には転記しない)。
- **unimpl helper (受入 5 の一部)**: 本 commit の既定経路の実測は 19000 = 17、19165 = 136 (`summary.csv` 第 6 列)。 §15 の 241・§16 の 148 は別の測定構成の値で、構成差はまだ切り分けていない。 受入 5 は未完。
- **未達**: 受入 3 (精度影響) は未測定。 19000 の `function_1800bcb00` で `PLUG_F80_LOWER=0` / `=1` の出力差を見る必要がある。 19165 の 78 関数の lift (受入 4 相当) は #3447 / 子 PLG-F4-9。
