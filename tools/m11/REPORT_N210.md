# M11-N210 (#4747): function_40c650 の署名変更で unit 149・158 が退行する要因の切り分け

親: #3678 / #2902 / #3642。受入条件 1 (機構の特定) の REPORT。受入条件 2 (退行しない形の survey 差 0) は #4748 (N211)。

結論 (作成時の記録に基づく。本 run で再確認していない): 退行は、呼出し側 16 site が新しい `f64` 枠へ渡す **実値** (`movsd` / `cvtss2sd` 由来) で起きる可能性が高い (ctlB 退行・ctlC 無退行の作成時の対比)。ctlB・ctlC は生成器の再現性が未解決のため、本 run では再生成できていない (子 #4809)。
ただし wasm 側の機構 (なぜ実値で 149・158 の結果が変わるか) は未特定。caller `function_660050` / `function_668290` の frame 読みの差が候補 (未実測)。

## 測定 (測定 commit 4bb58c852・同一 IR 上の A/B)

測定 commit は `4bb58c852` (variant の生成器 `m11_sigfix40c_ab.py` を追加した commit)。基準の比較対象として `5ec59116d` (origin/main の直前) を書く。`5ec59116d` には生成器が無いので、variant の生成と測定はどちらも `4bb58c852` 以降のコードで行う。

IR: `cd tools/m11 && FL_WIN64_DIR=<展開先> bash m11_gen_ir2.sh` (34 秒・rc 0)。survey は `node m11_survey.mjs` (6.6 秒)。

### 入力 (only40c) の作り方

既定の `fix_xmm_args.py` は `NO_CONV = {'function_40c650'}` のため 40c650 を変換しない (既定版の出力: `skipped: call_arity_mismatch(sites=1, params=0, cause=xmm:16)`)。only40c の入力は、`NO_CONV` を空にした一時コピー (リポジトリ外・`/tmp`) で変換して得た。実行した手順:

```
# NO_CONV = {'function_40c650'} を NO_CONV = set() にした一時コピーを使い、HERE だけを元の passes/ に向ける
python3 fxa_nc.py work/boot_final.ll only40c_full.ll --pe <PE> --report nc_report.json   # 実測 49.5 秒
```

結果: `fixed` に `function_40c650` (params `['double %in.xmm0']`)。呼出し 16 site は `double %xmmcv.N.f` の実値を渡す。

### 生成器の再現 (未解決)

`m11_sigfix40c_ab.py` は `work/boot_final.ll` (素材) から直接は動かない。確認したこと:

- 素材の `boot_final.ll` では `function_40c650` は `define i128 @function_40c650()` (引数なし)・呼出し 16 site は `call i64 @function_40c650(i128 %x)`。生成器の `CALL_RE` / `BODY_OLD` とは一致しない。
- 上の only40c の入力 (`fix_xmm_args.py` の出力) を生成器に渡すと `callee body not found` で終了する。`BODY_OLD` の文字列が 4 回出現し「ちょうど 1 回」の判定に落ちるため。
- ctlC.ll・only40c.ll・ctlB.ll の**生成は本 run では再現していない**。そのため「手作り版との cmp 一致」の記録は無い (手作り版の場所も特定していない)。
- 上の表の variant 数値は作成時の記録。生成器からの再生成と、手作り版との cmp は本 run では確認していない。

よって生成器の再現性は未解決 (下表)。

| 変種 | 構成 | ok / noproc / miss / trap / clobber | 基準との unit 差 |
|---|---|---|---|
| base | `M11_XMM_ARGS=0` | 873 / 1 / 47 / 21 / 0 | (基準。#3642 の 873/1/47/21/0 と一致) |
| 既定変換 | `M11_XMM_ARGS=1` (NO_CONV = 40c650) | 873 / 1 / 47 / 21 / 0 | 差 0 |
| 全変換 | `NO_CONV` 空 (47 callee) | 872 / 1 / 47 / 20 / 2 | 149 trap→clobber、158 ok→clobber (差はこの 2 件のみ) |
| only40c | 40c650 だけ変換 (`(i32,f64)`、実値を渡す) | 872 / 1 / 47 / 20 / 2 | **149 trap→clobber、158 ok→clobber** |
| ctlB | only40c と同じ変換。callee 本体は入力を 0 固定 (呼出し側は実値) | 872 / 1 / 47 / 20 / 2 | **149・158 が同じく退行** |
| ctlC | 呼出し 16 site を `0.0` にする。callee 本体は入力を読む | 873 / 1 / 47 / 21 / 0 | **差 0** |
| sigzero | 呼出し 16 site を `0.0` にし、callee 本体も 0 固定 | 873 / 1 / 47 / 21 / 0 | **差 0** |

判定: 作成時の記録では、退行は「呼出し側が `f64` 枠に渡す実値」で起きたように見える (ctlB 退行・ctlC 無退行の対比)。ただし ctlB・ctlC・sigzero は本 run で再生成も再測定もしていないため、この対比は本 run では確認されていない。実値で退行する可能性が高い、という程度に留める。

## wasm レベルの差 (baseline vs only40c、`wasm-dis` 実測)

- `function_40c650`: `(func (param i32))` → `(func (param i32) (param f64))` (export 1929 → 同じ)。`m11_tr_function_40c650` (`$8696`) は両者で `(i64×8) → i64` のまま。
- 呼出し側 (例: `function_660050` 内 `$3943`): baseline は sret 用に `(i32.add (local.get $0) (i32.const 16))` を渡すのみ。変換版は sret が `+192` になり、f64 用に `(i64.load offset=208)` / `offset=216` を読んで `f64.reinterpret_i64` で渡す (`wasm-dis` の該当 site の比較。他 site の一覧は未確認)。
- 呼出し側の関数: `$3943`=`function_660050`、`$4036`=`function_668290` (survey 149・158 の trap/ok 経路上)。
- 関数 table: 両者とも 7430 要素。`call_indirect` 0 件。table 経由の差は無い。

## 実行時 (unit 149・158 の trap/ok スタック)

- baseline 149: `RuntimeError: memory access out of bounds` (`function_412e40`(idx 77) ← `653660`/`6539e0`/`664190`/`664260` ← `m11_tr_function_664260`)。
- only40c 149: 同じ OOB が `function_407a50`(idx 1873) → `409410` → `412c20` → `414ad0` → `414bb0` → `652500` → `653660` → `6539e0` → `664190` → `664260` の経路で起きる。baseline とは経路が違う (baseline は `412e40` から)。40c650 の戻り値の使い方が変わったことの裏付けだが、呼出し元との対応は未確認。
- baseline 158: `ok` (戻り 1)。only40c 158: `clobber` (`RuntimeError`)。158 の経路の名前付けは全変換版 (`NO_CONV` 空) の stack で見たもの (`414bb0` → `665bd0` → `66d050` → `66d1a0`)。only40c の 158 stack は未取得。

## 未解決・起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側の機構: 実値で 149・158 の経路が変わる理由 (caller の frame 読み `offset=208/216` と戻り値の使い道) | 受入条件 1 の「機構」の核心。未特定 | #4777 (M11-N221) |
| caller の戻り値利用 (sret `+16` → `+192` 変化が 149・158 の分岐をどう変えるか) | 機構の確定に必要 | #4777 (M11-N221) |
| 生成器 `m11_sigfix40c_ab.py` の再現性 (素材の IR 形と `BODY_OLD` の一意性、`CALL_RE` の型) | variant の再生成ができず、cmp 一致の根拠も無い。variant の数値は作成時の記録で、本 run では再測定していない | #4809 (M11-N223) |
| 受入条件 2 (退行しない形で 40c650 を変換して survey 差 0) | #4748 (N211) が担当 | #4748 |

## 測定の範囲

- 全測定は `tools/m11/work/boot_final.ll` (`m11_gen_ir2.sh` の再生成 IR) 上。`work-m11` は素材の旧生成で基準に使わない (WORKFLOW §11)。
- 測定 commit: 4bb58c852 (生成器を追加した commit)。コード差分は `m11_sigfix40c_ab.py` と本 REPORT のみ。
- 本 run で再測定したのは入力生成 (only40c 入力の作成 49.5 秒・rc 0) と PE 展開 (2.7 秒) だけ。survey の unit 数値 (上の表) は再測定していない。
- 鮮度の証跡: `git diff 4bb58c852 HEAD -- tools/m11` は 8 file (`m11_build.sh`・`m11_post.py`・`ldfix/spill_classify_1161.py` ほか) に差分がある。`--slots` 無し (既定) の経路は、素材 `work-m11` の `boot_final.ll` を入力に、4bb58c852 版と HEAD 版の `m11_post.py` を実行して出力を比べた。出力 IR と report JSON は `cmp` で一致 (rc 0・両方)。`m11_build.sh` の `SLOT_ARG` は `M11_SLOT_ROWS` 空のとき空文字になり、`m11_post.py` の `--slots` 分岐は入らない。`ldfix/spill_classify_1161.py` の追加 (candidate_verdicts_4676 の読込) は、`tools/m11/m11_*.sh` からの参照が無い (`grep` で確認。参照元は `ldfix/audit_lsf_ssa_e2e.sh` のみ) ため、build・survey の経路に入らない。
- 生成物 (`work/`・`emsdk/`・`retdec/`) は gitignore または未追跡で commit しない。
