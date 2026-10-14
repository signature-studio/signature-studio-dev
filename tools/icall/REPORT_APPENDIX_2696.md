# 付録: icall #2696 (ICALL-82) — dsm の data 区分に実コードを含む closure 関数の実測

> 親: #2674 (ICALL-79)。受入 1 (`0x180da4030` の修復) と受入 3 (修復前後の sweep 比較) は本 PR では未達で、子 **#2708 (ICALL-83)** に移した。本 PR は受入 2 (実測と定義) だけを完了単位とする。
> 既知類型との関係 (`docs/DEFECTS.md`): **該当なし**。関数終端の fall-through 先の実コードが RetDec で data 区分になり IR から脱落する形は、D3 (store 消失)・D1b (jcc 先の dead code 削除) とは別。新規候補の類型は §5 (候補・未確定)。
> 前版 (dump 解析の欠損あり) からの訂正: 前版の A 8 件・B 63 件、MIN_RUN=1000 の対照 (A 0 / B 0) は、dump の後半 8 B 欠損による数値で、根拠にしない。

## 1. 結論

- closure 131 関数 (`work/rt_freshair-core/map.json` の `func_map`) のうち、dsm に関数行がある 130 件で、定義 A は **候補 13 → 実コード候補 11 件**、定義 B は **候補 124 → 95 件** (A ⊂ B)。
- **negative control で判定が 0 にならない。** 既知の非コード入力 (data 区分を乱数・並べ替えに差し替えたもの) でも、A は 1〜8 / 13、B は 26〜52 / 124 が通る (§3.3)。zero・0xCC 埋めでは 0 件。よって A 11 件・B 95 件は**実コードの件数ではなく候補の件数**。類型として確定させるには実行比較 (`fa_cmp`) が要る。
- A 11 件の先頭命令は 10 件が `mov qword ptr [rsp+d], r64`、1 件 (`0x180da5f20`) が `mov qword ptr [rax-0x20], rbx`。route の IR (`after.0.restored.ll`) の `!insn.addr` には 11 / 11 件とも先頭アドレスが無い (別経路の検算)。
- 修復は未着手。前回 PR で測定した base sweep は **54 / 66 / 9 / 2** (bit 一致 / native crash・timeout / wasm のみ err / 値の不一致)。route の経路は測定 commit から差分 0 (§7)。

## 2. 定義と測定条件

| 項目 | 内容 |
|---|---|
| 入力 | `work/rt_freshair-core/before.0.drc.dsm` (RetDec 逆アセンブル)・`map.json` の `func_map` (131 キー)・`after.0.restored.ll` (IR 検算) |
| dump の読み取り | 16 B 行は 8 B 目の後が二重空白 (`0f  10`)。`DUMP_RE` は行末 (` \|` または tab) まで全バイトを取る。dsm の `0x` 行で解析できないものは 1 件 (`0x182319000:   ??`、未ダンプ)。decode 対象の区間に欠けたバイトがあれば error で止まる (黙って詰めない)。実行で error は出ていない (未ダンプ行はどの decode 区間にも入らない) |
| 関数区間 | dsm の `; function: NAME at S -- E` 行の `[S, E)`。closure 131 のうち dsm に関数行が無いのは 1 件 (`0x18100beb0`・5 B の断片)。この関数は数えず、対象は **130** |
| decode | capstone (x86-64)。線形 decode は decode 不能な命令で止まる (`(bad)` は出さない)。よって decode 結果は正常 decode できる先頭の連続 |
| 定義 A (候補) | 区間 `[S, E)` の直後 (`A == E`) に data 区分 `[E, B)` がある (**A 候補 13**)。E 直前の最後の命令が `ret` / `jmp` / `ud2` / `hlt` / `int3` なら候補外 (脱落ではない)。data 区分の先頭から **8 命令以上が連続して decode** でき、先頭 16 B に `00 00` と `cc` が無いもの |
| 定義 B (上限の候補) | 区間の先頭 S から次の関数行の開始 N までの data 区分 `[A, B)` (**B 候補 124 関数**) のうち、線形 decode が **8 命令以上続き、その中に ret / call / j\* を 1 つ以上含む** もの。境界の条件は A より緩い |
| 検算 | A 候補の先頭アドレスが route IR に `!insn.addr` 付きで載っているか (`ir_has_start`) |
| スクリプト | `tools/icall/diff/data_code_count.py` (`--control` で negative control)。出力 `work/icall_data_code/data_code_count*.json` |

## 3. 実測 (測定 commit `3dfa5bc6`・HEAD と同一の出力)

### 3.1 件数

| 項目 | 値 |
|---|--:|
| 対象 (dsm に関数行がある closure 関数) | 130 |
| A 候補 (判定前) | 13 |
| A 判定 (実コード候補) | 11 |
| B 候補 (判定前) | 124 |
| B 判定 (実コード候補・上限) | 95 |
| A ∪ B | 95 |
| A の先頭アドレスが route IR に無い | 11 / 11 |

### 3.2 定義 A の 11 件

| 関数 | data 区分 | data 先頭命令 | 関数の線形 decode 末尾 (E の直前) | route IR に先頭無し |
|---|---|---|---|:-:|
| `0x1803b5500` | `0x1803b550f–0x1803b5b60` | `mov qword ptr [rsp+0x30], rdi` | `je` | ✓ |
| `0x1803de190` | `0x1803de1b7–0x1803de310` | `mov qword ptr [rsp+0x40], rsi` | `je` | ✓ |
| `0x18040c950` | `0x18040c9c7–0x18043bef0` | `mov qword ptr [rsp+0x38], rsi` | `je` | ✓ |
| `0x180829930` | `0x18082993a–0x180829c20` | `mov qword ptr [rsp+0x30], rbx` | `sub rsp, 0x20` | ✓ |
| `0x180829c20` | `0x180829c37–0x180848140` | `mov qword ptr [rsp+0x40], rbx` | `je` | ✓ |
| `0x180c97f20` | `0x180c97f3c–0x180c98240` | `mov qword ptr [rsp+0x50], rbx` | `je` | ✓ |
| `0x180c98240` | `0x180c98256–0x180c99430` | `mov qword ptr [rsp+0x40], rdi` | `je` | ✓ |
| `0x180c99430` (前版の未検出) | `0x180c9946a–0x180c9d700` | `mov qword ptr [rsp+0x20], r15` | `je` | ✓ |
| `0x180da4030` | `0x180da4081–0x180da41a0` | `mov qword ptr [rsp+0x20], rbp` | `xor eax, eax` | ✓ |
| `0x180da5f20` (前版の未検出) | `0x180da5f51–0x180da6720` | `mov qword ptr [rax-0x20], rbx` | `je` | ✓ |
| `0x180da6720` (前版の未検出) | `0x180da67cc–0x180da68c0` | `mov qword ptr [rsp+0x50], rsi` | `jle` | ✓ |

- 11 件とも、関数の線形 decode の最後の命令が E でちょうど終わる。末尾が条件 jump (`je`/`jle`) が 9 件、`sub rsp, 0x20` が 1 件 (`0x180829930`)、`xor eax, eax` が 1 件 (`0x180da4030`)。
- 先頭命令は 10 件が `mov qword ptr [rsp+d], r64` (フレーム退避 store)。`frame_slot_restore.py` (ICALL-77) が扱う store と同じ形だが、restore の効果は測っていない (§6)。
- `0x180da4030` の data 区分は `0x180da4081` 以降に `movups`・`lock cmpxchg` のループを含む。IR (`after.0.restored.ll` の `function_180da4030`) では `xor eax,eax` (0x180da407f) のブロックが直接 `ret i64 %24` で終わり、0x180da4081 以降が無い。

### 3.3 negative control (非コード入力)

data 区分 (dsm の全 307 区間) の bytes だけを差し替え、判定を通す。関数本体の線形 decode は元のバイトのまま (A の末尾判定が動かないように)。乱数・並べ替えは seed 固定。

| 対照 | A 判定 (候補 13) | B 判定 (候補 124) |
|---|--:|--:|
| 実データ (none) | 11 | 95 |
| zero (00 埋め) | 0 | 0 |
| cc (CC 埋め) | 0 | 0 |
| random (乱数・seed 1 / 2 / 3) | 4 / 6 / 8 | 26 / 28 / 26 |
| shuffle (区間内の並べ替え・seed 1 / 2 / 3) | 6 / 1 / 4 | 46 / 38 / 52 |

- zero・cc で 0 になるのは、判定の構造による (A は `00 00`・`cc` を除外し、B は ret/call/j を含まない)。退化した入力なので、判定の強さの証拠にはならない。
- **乱数・並べ替えの入力 (非コードと分かっている入力) でも A は 1〜8 件、B は 26〜52 件が通る。** つまり判定は非コードを確実には除けない。実データの A 11 / 13 は乱数の最大 8 より多いが、13 件 × 3 seed の範囲では有意とは言えない。B 95 / 124 は非コードの 21〜42% に対し 77% で、高いが上限見積りのままである。
- 前版の `MIN_RUN=1000` の対照 (A 0 / B 0) は dump の欠損による 0 で、根拠にしない (撤回)。

## 4. fa_cmp と fa_sweep (base = `FA_FRAME_SLOT` 未設定・前回 PR の測定)

| コマンド | 結果 | 所要 | load (開始→終了) |
|---|---|--:|---|
| `python3 tools/icall/diff/fa_cmp.py 180da4030 --n 8` | match 0 / mismatch 8 (native `0000000000000000`、wasm `c000c5300342457c` ほか) | 未計時 | 0.44 (前回 PR の測定) |
| `bash tools/icall/diff/fa_sweep.sh 8 60` (base) | **bit 一致 54 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 2** (計 131) | 70.1 s | 0.44 → 0.83 |

- 前回 PR で `d32e3a32` と `6aa8a94d` の worktree で測定し、`sweep.jsonl` が `cmp` で完全一致した。
- 本 fix では再実行していない (route・fa_cmp・fa_sweep の経路は測定 commit から差分 0。§7)。再実行は子 #2708 の検証で行う。
- ICALL-78 付録 (`REPORT_APPENDIX_2508.md` §3.4) の base 値 53 / 66 / 9 / 3 とは 1 件異なる (値の不一致 3 → 2)。差の 1 件は特定していない。ICALL-78 で報告した `0x1803dee20` の揺れ (#2302 で追跡) と同種の可能性がある (未確認)。
- 受入 3 (修復前後で他の判定が変わらない) は修復を入れていないため測れない。子 #2708 で行う。

## 5. 新規類型の候補 (DEFECTS.md 形式・未確定・PM 判断)

| 項目 | 内容 |
|---|---|
| 症状 | 関数の dsm 区間の直後 (fall-through 先) に実コードがあるのに RetDec が data 区分にし、IR に載らない疑い。`0x180da4030` では route の wasm 出力が native と異なる (native xmm0 = 0、wasm = 入力) |
| 根本原因 | 未確定。RetDec が関数の終端を fall-through 先の前で切っている疑い。`xor eax,eax` 直後の 0x180da407f で切れる例は確認したが、他の候補の終端命令の形は未分類 |
| 観測 | 定義 A の候補 11 件 (13 件中)。先頭命令は 10 件が `mov qword ptr [rsp+d], r64`、1 件が `mov qword ptr [rax-0x20], rbx`。IR の `!insn.addr` に先頭が無い 11 / 11 |
| 注意 | negative control で、非コードの入力も A 1〜8 件が通る (§3.3)。候補の中に偽陽性がある。実行比較 (fa_cmp) 以外では実コードと確定できない |
| 検出信号 | dsm で関数行の `E` と data 行の `A == E` が一致し、data 先頭から 8 命令以上 decode でき、`00 00`・`cc` を含まない (偽陽性を含む) |
| 修復 | 未実装 (子 #2708 の候補 1〜3)。修復の是非は受入 1 と 3 で判定する |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1: `0x180da4030` の 0x180da4081–0x180da4176 を IR に載せる修復 | silent miscompile (前回 fa_cmp 8/8 mismatch) | 子 #2708 (ICALL-83) |
| 受入 3: 修復前後の sweep 比較 (base 54/66/9/2 を基準) | 修復の影響範囲が未確定 | 子 #2708 (ICALL-83) |
| A 候補 11 件のうち `0x180da4030` 以外 10 件の判定 (修復対象か、偽陽性か) | wasm 出力は未検証 (fa_cmp は未実施) | 子 #2708 (ICALL-83) |
| B 候補 95 件の個別確認 (実コードか jump table・定数か) | 定義 B は上限見積りで、非コード対照でも 26〜52 件が通る | 本 PR の未解決表 (PM 判断。個別の追跡は子を増やさない) |
| A 候補の先頭 store と ICALL-77 の `frame_slot_restore.py` の関係 (11 件中 10 件が同じ形) | restore pass が A 候補に効くかは未測定 | 本 PR の未解決表 (事実の記録。子 #2708 の検証で扱う) |
| 既存 sweep の base 値の 1 件差 (53/66/9/3 → 54/66/9/2) | 比較の基準が揺れる | #2302 (既存の揺れ追跡。本 PR は 1 件差を記録のみ) |

## 7. 測定 commit と差分

- data 区分の測定 commit: `3dfa5bc6` (`data_code_count.py` の最後のコード変更)。前版の測定 commit `0ab44c27` は dump 欠損のまま。`git diff 3dfa5bc6 HEAD -- tools/icall/diff/data_code_count.py` の出力は空。
- route・sweep の測定 commit: `6aa8a94d` (origin/main)。`git diff 6aa8a94d HEAD -- tools/icall/fa_route_build.sh tools/icall/ir_*.py tools/icall/frame_slot_restore.py tools/icall/vex_gen.py tools/icall/rt tools/icall/diff/fa_cmp.py tools/icall/diff/fa_sweep.sh tools/m2 tools/m5 tools/m11 tools/ott tools/targets/freshair tools/liftlib --stat` の出力は**空** (経路差分 0)。
- `fa_va_sha.py` (`tools/icall/diff/`) は、`*.sh`・`*.py` の中では自身の docstring 以外から参照されない (`grep -rln fa_va_sha tools --include=*.sh --include=*.py` は `fa_va_sha.py` のみ)。`REPORT_APPENDIX_2675.md` は md として名前に言及する。
- 本 PR のコード commit は `0ab44c27` (測定用スクリプトの追加) と `3dfa5bc6` (dump 解析と欠損検出・negative control の修正)。どちらも route の入力ではない。

## 8. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C . tools/icall/work/rt_freshair-core/before.0.drc.dsm tools/icall/work/rt_freshair-core/after.0.restored.ll tools/icall/work/rt_freshair-core/map.json
python3 tools/icall/diff/data_code_count.py                      # 期待: A 候補 13・判定 11 / B 候補 124・判定 95 / A_start_absent 11
for c in "zero 0" "cc 0" "random 1" "shuffle 1"; do set -- $c; python3 tools/icall/diff/data_code_count.py --control $1 --seed $2 | head -1; done   # negative control
bash tools/ott/native/build.sh                                    # fa_cmp に必要 (1.6 s)
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"   # plugins-freshair が無いときの代替 (REPORT_APPENDIX_2508 §5)
bash tools/icall/fa_route_build.sh                               # base route (5 s)
python3 tools/icall/diff/fa_cmp.py 180da4030 --n 8               # 期待: match 0 / mismatch 8 (修復前)
bash tools/icall/diff/fa_sweep.sh 8 60                           # 期待 (base): 最終行の集計 54 / 66 / 9 / 2 (前回 70.1 s)
```
