# REPORT N124: set_other imm 非定数 55 件の CFG 到達定義による実値化の試行 (#1867, 親 #1835)

既知類型との関係: 該当なし (sigfix の引数値決定。欠陥類型は DEFECTS.md 外)。
前段: `REPORT_N112.md` (直線追跡で decided 0 / undecided 55)。

## 1. 結論

- CFG 到達定義 (`m11_setother_cfg_value.py`) で 55 件を決めようとした結果、**決まった 0 / 未決 55 (未分類 0)**。
- 未決の主因は分岐先ではなく **call による volatile 族の破壊**。`mov r8b, N` 等は下位 1 バイトだけを書くので、上位ビットは call 前の値に依存し、その値は ABI 上 call 後に未定義。
- よって 55 件の値は、caller 側の機械語からは定まらない。値を埋めると偽の定数になるため、`fixes.json` は変更しない。
- 受入 1 は「未分類 0・決められない件は件数で残す」を満たす。受入 2 は比較する決定値が無いため判定不能 (空真)。受入 3 (survey) は素材不足で未測定 (§5)。

## 2. 測定条件 (測定 commit `d5677fe3`)

| 項目 | 値 |
|---|---|
| 入力 | `tools/m11/work/boot_final.ll` (work-m11, sha256 `69c774…`)・PE `extracted/block00031_PE.bin` (fl-win64) |
| 素材 | `fl-win64`・`work-m11` を `tar --zstd -xf` で展開 (`$RUNNER_TEMP/fl-win64`) |
| `m11_sigfix_stats.sh` | rc 0・real 3.1 s・`[verify] fixes 33: match 33 / mismatch 0`・`zeropad sites 1049 / args 2064; const recovered 24` |
| `m11_setother_ledger_verify.py` | `match 410`・rc 0 (台帳の source 分類は変更なし) |
| `m11_setother_imm_class.py` | `full_const 6 / partial_write 35 / stack_partial 9 / arith 11 / no_write 0` |
| `m11_setother_ssa_value.py` (N112) | decided 0 / undecided 55 (再現) |
| `m11_setother_cfg_value.py` (本 REPORT) | **decided 0 / undecided 55** (未分類 0・全行に理由あり) |

## 3. 未決理由 (実測, `cfg_value_rows.json`)

実測 (`cfg_value_rows.json`・`why` の内訳。`call_clobber` を含む行は分岐先越えの後も含む):

| 区分 (imm_class) | 件数 | `call_clobber` を含む | 旧値が関数入口まで届いた (`entry`) | その他 |
|---|---|---|---|---|
| partial_write | 35 | 32 | 3 | 0 |
| stack_partial | 9 | 9 | 0 | 0 |
| arith | 11 | 7 | 0 | 4 (旧値が別レジスタ・メモリ由来の未対応源) |
| **計** | **55** | **48** | **3** | **4** |

- 分岐先 (merge) を越える処理は実装済みで、merge を含む行は 28 件。ただし merge 越えの後も全経路で call に当たる件は決まらなかった。
- `loop` / `merge_indirect` / `merge_nopred` は 0 件。関数内の間接 jmp による判定不能は無い。

## 4. 検算 (正の対照)

- 本 engine で、既存の `fixes.json` の `const` 復元 (int 33 件中 16 件を機械語から検証可能) を再計算し、**16 / 16 一致・不一致 0**。残り 17 件は旧値が未決 (`mem_size8`・`*_call_clobber`)。
- engine は正しく定数を追えている。0 件決定は実データの性質。
- 手検査 (`function_1046a30` → `function_4420e0` の引数 pos 2): `call 0x664890` の後ろで `mov r8b, 2`。上位ビットは call で破壊された r8 の値で、ABI 上定まらない。

## 5. 受入 3 (survey) が測れない理由

- `m11_gen_ir2.sh` と `m11_bounds.py` は `functions_dll.csv` (素材外の Ghidra 中間物) と `work/lift_pe.sha256` を要する (`REPORT_N112.md` §5 と同じ)。
- 素材だけでは survey (`M11_SIGFIX_RECOVER=1`) を回せないため、未測定。

## 6. 測定 commit と差分

- 測定 commit: `d5677fe3` (コードを変えた最後の commit = `tools/m11/m11_setother_cfg_value.py` の対象限定)。
- 測定 commit から本 REPORT を含む HEAD までのコード差分: `git diff --stat d5677fe3 HEAD -- tools/m11 ':(exclude)*.md'` は **0 行** (md のみ)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 55 件の値は caller の機械語だけでは決まらない (call 後の volatile 上位ビット) | set_other imm 非定数 55 件の値は未決のまま。0 詰め引数の意味は未保証 | #1835 |
| survey (受入 3) の素材 (`functions_dll.csv`・`lift_pe.sha256`) | survey 退行が未判定 | #1154 |
| `m11_argrecover_verify.py` の join 点越え検算 (REPORT_N1835 §4) | 検算の限界。本 run で変更なし | #1835 |
