# #2402 (LD-112): fix_ld108 の本番配線と、通常 build の wasm での実測

親: #2316 (LD-108、PR #2397)。既知類型との関係: DEFECTS D20 (`docs/DEFECTS.md`)。

**判定: 達成 (issue の範囲を縮めた)**。配線・ir_conditions / IR diff・通常 build の wasm での実測・survey 突合・`%arg1` assert・DEFECTS 更新は達成。受入条件 4 の ok 絶対値は、869 と 870 の差を IR の出所 (同梱 IR と再生成 IR の差) まで特定した。**ただし 5872 行のどの変更が差を生むかは未特定で、136 は本 run で再現せず原因は未特定**。「136 の原因特定」と「869/870 差の変更の特定」は issue の受入条件から外した (§5・§8)。

測定 commit: `7f5524b6` (main 取り込み後の HEAD。コードを変えた最後の commit)。`ldfix_509_e2e.sh`・`ld108_e2e.sh` を同 commit で実測した (§9)。`git diff 7f5524b6 HEAD -- tools/m11 ':(exclude)tools/m11/ldfix/REPORT_2402.md'` の出力は 0 行。取り込み前の `3de663ee` と `28d10d58` の値は §7・§9 に残す。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| `fix_ld108.py` を `m11_gen_ir2.sh` の ldfix 直後 (`--bind` の前) に常設。想定と違う IR は fail-closed | **達成** (§2) |
| `ir_conditions.json` の記録 (ldfix・qstore・PE) と `ir_sha256` が `m11_cond.py --check` で一致。組込み前後で変わるのは 41a670 の 1 関数だけ (`diff`) | **達成** (§3) |
| 通常の `m11_build.sh` で作った wasm を `dyn_ld108.mjs` で直接呼び、head が修復後の期待値と一致 | **達成** (§4)。修復前 0x3333 FAIL → 修復後 0x2222 PASS |
| survey 942 unit の組込み前後の突合で ok 退行 0。ok 絶対値の差 (869 / 870) の原因を特定 | **一部達成**。退行 0 (§4)。869 と 870 の差は IR の出所 (同梱 IR と再生成 IR の差) まで特定 (§5)。どの変更が差を生むかは未特定 (§8)。136 型は再現せず原因未特定のため範囲から外した (§8) |
| `%arg1` が `function_41a670` の第 1 仮引数 (型 `i64`) と一致することの assert | **達成** (§2・NC1) |
| `docs/DEFECTS.md` D20 の「修復」欄を本番配線済みの記述へ | **達成** (結論 1 行 + リンク。測定値は書かない) |

## 2. 配線

- `m11_gen_ir2.sh`: ldfix の直後 (`ldfix=applied` の枝の中、`m11_cond.py --bind` の前) で `ldfix/fix_ld108.py` を適用し、`ld108=applied` を記録する。`set -e` の下で、assert で止まると `ld108=applied` は記録されず `--bind` にも到達しない。`fix_ld108.py` は `work/boot_final.ld108.ll` に書いてから `mv` するため、`work/boot_final.ll` は ldfix 後・fix_ld108 前の IR のまま残る。`--reset` で消えた `ir_sha256` は戻らないので、`m11_build.sh` は `ld108=not-applied` を見て rc 2 で拒否する (`--reset` に `ld108=not-applied` を足した)。`M11_LDFIX=0` の枝は fix_ld108 を適用しない (ldfix 前の IR を取る A/B 用で、build は `ldfix=disabled` の明示 opt-in を要する枝のため)。
- `M11_FIX_LD108=0`: 修復前の IR を明示的に取る A/B 用。`ld108=disabled` を記録する。
- `m11_build.sh`: `ldfix=applied` の IR は `ld108=applied` の記録を要求する。`ld108=disabled` は `M11_ALLOW_LD108_DISABLED=1` のときだけ build する (`M11_ALLOW_LDFIX_DISABLED` と同じ作り)。記録が無い IR (配線前に作った IR) は rc 2 で拒否する。
- `fix_ld108.py`: `define` 行から第 1 仮引数を読み、`i64 %arg1` でなければ assert で止める。既存の assert (store 行が 1 件ずつ・ブロックの存在・関数が 1 件) は維持した。

## 3. ir_conditions と IR diff

`ld108_e2e.sh` の 1/6 (`M11_FIX_LD108=0 bash m11_gen_ir2.sh` と `bash m11_gen_ir2.sh`)。

| | ldfix | qstore | ld108 | PE | ir_sha256 (先頭 16 桁) | `m11_cond.py --check` |
|---|---|---|---|---|---|---|
| 修復前 | applied | not-applied | disabled | 同じ | `08c7b6462d9fac38` | 一致 |
| 修復後 | applied | not-applied | applied | 同じ | `7c653b0f217d2842` | 一致 |
| 修復後・build 後 | applied | applied | applied | 同じ | `f199b896d756478f` | 一致 |

`m11_build.sh` は qstore・alloca・guard699・fix912 で IR を書き換え、その都度 `--bind` で指紋を更新する。build 後の `--check` が一致することで、配線が指紋の連鎖を壊さないことを確認した。修復前の指紋は、配線前の `m11_gen_ir2.sh` (commit `53d1bb77`) が作った IR の指紋 (`08c7b6462d9fac38…`) とバイト一致した (`M11_FIX_LD108=0` は従来の出力と同一)。

`diff pre.ll post.ll` (全文):

```
125488,125489c125488,125491
<   store i64 %2, ptr inttoptr (i64 16404608 to ptr), align 8
<   store i64 %2, ptr %rax.0.reg2mem
---
>   %ldfx108p = inttoptr i64 %arg1 to ptr
>   %ldfx108 = load i64, ptr %ldfx108p, align 8
>   store i64 %ldfx108, ptr inttoptr (i64 16404608 to ptr), align 8
>   store i64 %ldfx108, ptr %rax.0.reg2mem
```

変更行は 6 行 (削除 2・追加 4)。別算法の検算 `ld108_irdiff.py` (IR を関数単位と関数外に分けて文字列比較): 差のある関数は `function_41a670` の 1 件 (pre 7422・post 7422 の `define`)、関数外の本文は一致 (判定 PASS)。

## 4. 通常 build の wasm と survey

`m11_gen_ir2.sh` → `m11_build.sh` (環境変数の上書き無し) で作った wasm に対する測定。`dyn_ld108.mjs` は head=N・N.next([N+0])=0x2222・N.child([N+8])=0x3333 で `function_41a670(N)` を直接呼ぶ。

| 項目 | 修復前 (`M11_FIX_LD108=0`) | 修復後 (本番経路) |
|---|---|---|
| 41a670 の head (期待 0x2222) | 0x3333 FAIL | **0x2222 PASS** |
| `audit_lsf_disp.py` の SUSPECT (既定 = 変位形 + movs・lea 列挙) | 1 (41a670) | 0 (なし) |
| `audit_lsf_disp.py --no-strmov` (#2316 時点の列挙) | 4 (41a670 6677a0 d237e0 de1da0) | 3 (6677a0 d237e0 de1da0) |
| survey 942 unit | ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1 | 同じ |

既定の検出器で、修復後 IR の `audit_lsf.py` の `SUSPECT_DISP_VAS` は空になる (#2402 スレッドの提案の確認)。`--no-strmov` の残る 3 件は `movs`・`lea` 経由の誤検出で、REPORT_2396 §3 で突合済み (未解決ではない)。既定の 41a670 の 1 件は修復で消える。測定は §9。

`survey_diff.py` の突合: ok 退行 unit 0、kind 以外を含む差分 unit 0、icall sites・targets の総数差 0。survey の差が 0 であることは、41a670 の修復が survey の結果を変えないことを示すだけで、survey が head 解除の分岐を通るかは未確認 (§8)。分岐の効果を示す証拠は直接呼びだけである。

## 5. ok 絶対値 (136 / 869 / 870) の原因

REPORT_2316 §4 は「build 条件 (`ir_conditions.json` の記録) の差による」と推定していたが、実測は異なる。同じ survey (`trap_triage/survey_units.mjs`、942 unit) を、入力だけ変えて測った。

| 入力 | 結果 | 回数 |
|---|---|---|
| work-m11 に同梱の `boot_final.ll` (旧世代。`ldfix=disabled` を記録した build と `ldfix=applied` を記録した build の両方) | ok 869 / oob 15 / abort 2 / halt0 7 / miss 47 / other 1 / noproc 1 | 4 (作業ディレクトリが使用済み 2・展開直後のコピー 2。いずれも 869) |
| `m11_gen_ir2.sh` で再生成した IR (本番経路) | ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1 | 9 (通常条件 7、CPU 競合 1、node 24.21.0 1。下記) |
| REPORT_2316 §4 の ok 136 / oob 8 / miss 797 / halt0 1 | — | 0 |

- **869 と 870 の差は IR の出所による**: 旧 `ld108_e2e.sh` は work-m11 同梱の `boot_final.ll` をそのまま build に使い、同梱 IR は現在の `m11_gen_ir2.sh` の出力と 5872 行が異なる (`diff | grep -c '^[<>]'`。`ldfx` を含む行は 3335 対 3433)。`ir_conditions.json` の記録 (`ldfix=disabled` / `applied`) は build を通すか拒否するかを決めるだけで IR も wasm も変えない (旧 e2e の pre = `ldfix=disabled` 記録と post = `ldfix=applied` 記録 + fix_ld108 は survey が一致)。**5872 行のうちどの変更が ok・oob・abort の差を生むかは未分解**。
- **新 `ld108_e2e.sh` は本番経路 (`m11_gen_ir2.sh`) で IR を作る**ため、条件が通常の build と揃い、基準値 870 と一致した。同梱の `boot_final.ll` には依存しなくなった。
- **136 は再現せず、原因は未特定**。同形 (ok 136 / oob 8 / miss 797 / halt0 1) の値は REPORT_1274 §5 の 1 回目にも単発で出ている。本 run は次の要因を変えて測り、全て ok 870 (または同梱 IR で 869) だった: 作業ディレクトリの状態 (使用済み / 展開直後)、IR の出所、`ir_conditions` の記録、node 22.23.3 と node 24.21.0、1 CPU に busy loop 6 本を載せた CPU 競合 (survey 81.3 秒、通常 13 秒台)。したがって build 条件 (`ir_conditions`)・node の版・CPU 負荷は 136 の原因ではない。
- 再発時に突き合わせられるよう、`ld108_e2e.sh` に (1) 実行環境の記録 (node・python・nproc・MemAvailable・load)、(2) survey が miss 過多 (miss > 200。通常 47、136 型は 797) のとき FAIL する検査を足した。

## 6. ネガティブコントロール (`ld108_e2e.sh` 6/6)

| ID | 操作 | 結果 |
|---|---|---|
| NC1 | `function_41a670` の第 1 仮引数を `i32 %arg1` に書き換えた IR を `fix_ld108.py` に渡す | assert で停止 (`第 1 仮引数が i64 %arg1 でない: 'i32 %arg1'`) |
| NC2 | 適用済みの IR (`ldfx108` を含む) に二重適用 | assert で停止 (`store 行が想定と違う`) |
| NC3 | 記録どおりの build 後 IR は `--check` 一致 (対照)。同じ IR に 1 行書き足すと | 対照は一致、書き足すと不一致 (rc 1) |
| NC4 | `ld108=disabled` の IR を `M11_ALLOW_LD108_DISABLED` 無しで `m11_build.sh` に渡す | rc 2 で拒否 (`ld108=applied の記録無し`) |
| NC5 (手動。e2e 非組込み) | ok 136 / oob 8 / miss 797 / halt0 1 の合成 survey JSON (942 件) を miss 過多検査に渡す | `SURVEY_ANOMALY` で rc 1 |

## 7. 再現・実測

```
FL_WIN64_DIR=<fl-win64 の展開先> bash tools/m11/ldfix/ld108_e2e.sh
```

前提: `tools/m11/work` に work-m11 の展開、[EMSDK] (`docs/REFERENCES.md`)、Python の `capstone`・`pefile`。終了時に `work/boot_final*.ll` と `ir_conditions.json` を元に戻す。

実測 (測定 commit `28d10d58`、foreground 1 回): rc 0、`LD108_E2E_SUMMARY fail=0` (PASS 14 検査)、real 3 分 26.207 秒 (206.2 秒)、load average (1 分) 0.16 (開始) → 0.97 (終了)、node v22.23.3・python 3.14.8・nproc 4・MemAvailable 14404 MiB。ir_sha256・survey・直接呼びの値は §3・§4 と一致した。

main 取り込み前の run も同じ値だった (ir_sha256 3 種・survey 870 / 870・直接呼び): commit `16447b9b` で real 211.7 秒・`fail=0` (load 1.64 → 1.02)、commit `9cc0b4e4` (検査 2 件の追加前) で 208.7 秒・`fail=0`。取り込みで入った main 側のコード差分は `M11_INSTR_60A270` (既定 0 の計測 knob)・`m11_ov.c`・`m11_post.py` で、既定値の経路は変わらない。

記録時点の値 (`28d10d58` の時点で、当時の HEAD から測った): `git diff 28d10d58 HEAD -- tools/m11 ':(exclude)tools/m11/ldfix/REPORT_2402.md'` の出力は 0 行 (REPORT 以外のコード差分なし)。その後の main 取り込み (`d2fe925a`・`7f5524b6`) で `tools/m11` に差分が入ったため、REPORT 更新前の head `f87d27a7` で同じ式の出力は 2795 行で、0 行ではない。現在の検証範囲は §9 の列挙で示す。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ok 136 型 (miss 797) の発生条件。本 run は再現せず、検査と環境記録を足した | 再発すると survey の値が基準から外れる | 本表のみ (再現待ちの追跡のため子 issue は起票しない)。再発したら `ld108_e2e.sh` の環境記録と `SURVEY_ANOMALY` の出力を添えて新規に起票する |
| 同梱 `boot_final.ll` と再生成 IR の 5872 行差のうち、ok 869 と 870 の差 (oob 15→16、abort 2→0) を生む変更の特定 | 旧 IR の値を基準にした過去 REPORT の絶対値は 870 と一致しない | 同上 (測定の基準は再生成 IR に統一済み) |
| survey の差が 0 (survey が 41a670 の head 解除の分岐を通るかは未確認)。効果の証拠は wasm 直接呼びだけ | 実機経路での効果は未確認 | 本表のみ (survey の経路確認は再測定にあたる) |
| `666a60` のループ内 store (`store i64 %29`) の修復 | 同型の誤りが残る (REPORT_735 §1.2・REPORT_509 §1) | #2447 (LD-115。親: #2402)。#1091 は CLOSED のため付け替えた。#2316 は 41a670 の修復が受入条件で範囲外 |

## 9. 再測定 (指摘 round 2 への対応。測定 commit `7f5524b6`)

測定 commit `7f5524b6` (main 取り込み後の HEAD) で、foreground 1 回ずつ実測した。main の取り込みで `tools/m11` に 20 ファイル・1400 行の差分が入ったため (`d2fe925a` からの差分)、取り込み後の HEAD で測り直した (WORKFLOW §6)。`d2fe925a` 時点の実測 (`6b13fb26` の worktree) も同じ値だった。所要時間は `time` で計測した。§4 の `--no-strmov` の行は `d2fe925a` (コード同一の `6b13fb26`) で測った値で、`7f5524b6` では再測定していない (既定の引数の 2/6 は `7f5524b6` でも §4 の既定の値と一致)。

| 検査 | rc | 結果 |
|---|---|---|
| `FL_WIN64_DIR=<fl-win64> EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash tools/m11/ldfix/ldfix_509_e2e.sh` | 0 | 6/7 build 成功 (修復前 = `ldfix=disabled` + `M11_ALLOW_LDFIX_DISABLED=1`、修復後 = `ldfix=applied` + `ld108=disabled` + `M11_ALLOW_LD108_DISABLED=1`)。survey: 修復前 ok 868 / oob 17 / halt0 8 / miss 47 / other 1 / noproc 1、修復後 ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1、ok 退行 0 (`survey_diff.py`。遷移は halt0 → ok 1 ほか)。kind 以外も含めた差分 unit 14 (修復で出力が変わる unit)。`reach_509.sh` は 26 関数を計装し、41a670 は 7 unit から到達。7/7 `DYN_SUMMARY after_fail=0/5`、5 関数すべて修復前 FAIL → 修復後 PASS。real 6 分 44.410 秒 |
| `FL_WIN64_DIR=<fl-win64> bash tools/m11/ldfix/ld108_e2e.sh` | 0 | `LD108_E2E_SUMMARY fail=0` (PASS 15 検査)。IR の差は 41a670 の 1 関数 (`ld108_irdiff.py` PASS)。修復前 FAIL (0x3333) → 修復後 PASS (0x2222)。survey 修復前後 ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1、ok 退行 0、kind 以外の差分 0、icall sites・targets の差 0。NC1〜NC4 PASS。audit の値は §4。real 3 分 24.865 秒。環境 (開始時): node v22.23.3 / python 3.14.8 / nproc 4 / MemAvailable 14458 MiB / load 0.23 0.61 0.59 |

- **6/7 の ld108 の扱い (指摘 blocking 1)**: `ldfix_509_e2e.sh` は `fix_ld108.py` を適用しない。REPORT_1290 の測定条件 (ldfix のみ) を保つため、修復後経路で `ld108=disabled` を明示し、build に `M11_ALLOW_LD108_DISABLED=1` を付けた (スクリプト冒頭と同じ)。
- **reach の rc (指摘の付随)**: `9b74f4c2` の `ldfix_509_e2e.sh` は `EMSDK_ENV` が無いと 6/7 の reach だけが失敗し、rc 0 のままだった。`3de663ee` で `EMSDK_ENV` を必須にし、`reach_509.sh` の失敗を `FAIL=1` に反映した。上の rc 0 は reach 成功後の値。
- 参考 (取り込み前 `3de663ee`): 同じ 2 本が rc 0。509 real 5 分 20.894 秒、ld108 real 3 分 23.637 秒。
- 測定後のコード差分 (`git diff 7f5524b6 HEAD -- tools/m11 ':(exclude)tools/m11/ldfix/REPORT_2402.md'`) は 0 行 (測定 commit 以降は REPORT_2402 のみ変更)。
- **e2e が実行するファイル (指摘 round 4 の (a))**。`ld108_e2e.sh`・`ldfix_509_e2e.sh` の推移閉包 67 件。静的解析で、スクリプト内の呼び出し・python の import・シェルのファイル名参照を辿り、文字列中のファイル名 (エラーメッセージ等) も含めた過大評価。`m11_lift.sh`・`m11_e2e.sh` が入るのは `m11_build.sh` の `echo` 内のメッセージ文字列からだけで、e2e はどちらも実行しない。

```
tools/m11/alloca/m11_alloca.py  tools/m11/fix912/m11_fix912.py  tools/m11/guard699/m11_guard699.py  tools/m11/lb_base.py
tools/m11/lb_check.py  tools/m11/ldfix/audit_lsf.py  tools/m11/ldfix/audit_lsf_disp.py  tools/m11/ldfix/audit_lsf_ssa.py
tools/m11/ldfix/audit_lsf_ssa_e2e.sh  tools/m11/ldfix/audit_undefload.py  tools/m11/ldfix/dyn_509.mjs  tools/m11/ldfix/dyn_ld108.mjs
tools/m11/ldfix/dyn_xcheck.py  tools/m11/ldfix/fix_ld108.py  tools/m11/ldfix/ld108_e2e.sh  tools/m11/ldfix/ld108_irdiff.py
tools/m11/ldfix/ldfix.py  tools/m11/ldfix/ldfix_509_e2e.sh  tools/m11/ldfix/ldfix_img.py  tools/m11/ldfix/ldframe.py
tools/m11/ldfix/ldmach.py  tools/m11/ldfix/ldmach_img.py  tools/m11/ldfix/negctl_510.sh  tools/m11/ldfix/reach_509.sh
tools/m11/ldfix/reach_survey.mjs  tools/m11/ldfix/spill_classify_1161.py  tools/m11/ldfix/tally_510.py  tools/m11/ldfix/window_recount.py
tools/m11/m11_argrecover.py  tools/m11/m11_asmfix.py  tools/m11/m11_bounds.py  tools/m11/m11_build.sh
tools/m11/m11_cond.py  tools/m11/m11_data_gen.py  tools/m11/m11_e2e.sh  tools/m11/m11_gen_ir2.sh
tools/m11/m11_genstubs.py  tools/m11/m11_icall_audit.py  tools/m11/m11_image_gen.py  tools/m11/m11_judge.py
tools/m11/m11_lift.sh  tools/m11/m11_lift_all.sh  tools/m11/m11_merge.py  tools/m11/m11_ov.c
tools/m11/m11_passes.py  tools/m11/m11_post.py  tools/m11/m11_postjs.py  tools/m11/m11_ptrcheck.mjs
tools/m11/m11_rt.c  tools/m11/m11_run.mjs  tools/m11/m11_scan.py  tools/m11/m11_simd2.py
tools/m11/m11_survey.mjs  tools/m11/m11_tail.py  tools/m11/m11_wasmnames.py  tools/m11/m11_win.c
tools/m11/msimd11_core.h  tools/m11/qstore/m11_qstore.py  tools/m11/trap_triage/survey_diff.py  tools/m11/trap_triage/survey_units.mjs
tools/shared/env.sh  tools/shared/lift/libkio/ir_normalize.py  tools/shim/src/failfast.c  tools/shim/src/file.c
tools/shim/src/heap.c  tools/shim/src/sync.c  tools/shim/src/timer.c
```

- 列挙に対する差分 (指摘 round 4 の (b)): `git diff d2fe925a HEAD -- <上の 67 件>` は 0 行。`git diff 7f5524b6 HEAD -- <67 件>` も 0 行。したがって `d2fe925a` で測った値 (§4 の `--no-strmov` 行など) は HEAD に当てはまる。
- 列挙の外 (指摘 round 4 の (c)): `git diff d2fe925a 7f5524b6 -- tools ':(exclude)*.md'` で変わった 17 ファイルは全て列挙の外。内訳は `tools/liftlib/liftlib/passes/base.py`・`tools/m5/ir5_patch.py` の `normalize()` (uselistorder 除去、#1664)、`tools/m11/ldfix/retdec2019_gv_2405.sh` と patch、`tools/m11/shimx_link/*`、`tools/m11/trap_triage/*_2408.*`・`watch_store_682.py`、`tools/m11/test_a7_uselistorder.py`、`tools/pm/worker_url`。e2e の経路には入らない: (i) e2e の経路に `ir5_patch.py` を呼ぶ箇所は無い (tools/m11 で呼ぶのは `m11_lift.sh` だけ。e2e は work-m11 の `boot*.lift.ll` を入力にし lift を再実行しない)。(ii) `liftlib` を読むのは `test_a7_uselistorder.py` だけ。(iii) `ldfix.py`・`m11_passes.py` の `ir5_patch` の語は説明文・コメントで、import は `lb_base`・`ldmach`・`ldframe` のみ。
- 測定は `7f5524b6` で行い、`7f5524b6` 以降の md 以外の `tools` 差分は 0 行 (`git diff 7f5524b6 HEAD -- tools ':(exclude)*.md'`)。よって再測定は不要 (WORKFLOW §6)。
