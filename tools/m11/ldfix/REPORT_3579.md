# REPORT_3579 — spill TRUE_DROP の残り 5 site (局所スロット [rbp+d]) の判定

親: #2910 (LD-137)。子: #3579 (LD-163)。前提: #3586 (callarg gate) は main に merge 済み (`8d93a181a` 時点)。

## 1. 結論

- 5 site はいずれも `fix_spill_2794.py` の 1to1 gate・callarg gate の**どちらも通らない**。修復 0 件。
- 根拠の付かない site は触らない (受入 2)。`fix_spill_2794.py` の gate は変えていない。
- `fix_d17_e2e.sh` は rc=0 で完走し、突合 (`check_spill_2794.py`) は PASS。

## 2. 5 site の照合 (受入 1)

素材: `tools/m11/work/boot_final3.ll` (work-m11)。行番号は絶対行。

| fn | site | K | M/I | 機械語 (store 先) | IR の K の load | 見送り理由 (fix_spill_2794.py) |
|---|---|---|--:|---|---|---|
| 1046a30 | 104c769 | 11e2c50 | 2/2 | `mov [rbp+0x5b8],eax` | 23856 `%3499 = load i32` → 23857 `store %3499, ptr %stack_var_16` | `callarg_site_not_rsp` |
| 1046a30 | 104c9e6 | 11e28c8 | 3/3 | `mov [rbp+0x5b8],eax` | 24026 `load i32` → 24027 `store ..., ptr %stack_var_16`。24035 `load i32` は別経路 | `callarg_site_not_rsp` |
| 1280530 | 12827e6 | 11dfda8 | 7/7 | `mov [rbp+0xc4],eax` | 7 本 (ptr 3・i32 4) | `callarg_site_not_rsp` |
| c589b0 | c5d2df | 11e1f40 | 4/4 | `mov [rbp+0x48],eax` | 6 本 (i32) | `callarg_site_not_rsp` |
| c589b0 | c5d343 | 11e1f40 | 4/4 | `mov [rbp+0x48],eax` | 同上 | `callarg_site_not_rsp` |

- 1046a30 の `%stack_var_16` は `alloca i32` (IR 16475) で、関数内の局所 IR 名。`[rbp+0x5b8]` との対応は IR からも機械語からも示せていない (REPORT_2910 §2 の未確認事項と同じ)。名前の対応を示せないので、ここでは直さない。
- 1280530 と c589b0 は、K の load と store の行単位の照合を今回行っていない (見送り理由の確認だけ)。受入 1 の完全な照合は未了で、次の run の作業。
- 5 site とも 1to1 gate は通らない (M = I ≥ 2 で、1 対 1 の条件に届かない)。callarg gate は `[rsp+0x20+8j]` の store 条件で落ちる。

## 3. e2e (`bash tools/m11/ldfix/fix_d17_e2e.sh`)

- 素材展開: `work-m11` (`tar --zstd -xf`、2 秒)。emsdk は `/opt/emsdk/emsdk_env.sh` 既存。
- 結果: rc=0 / `RESULT: PASS` (突合) / `emcc rc=0`。
- TRUE_DROP 30 site: REPAIRED 13 / SKIPPED 17 (旧 24 site 相当から、#3752・#3753 で判定が増えた)。
- 修復前 CELL_COLLAPSED 37 → 修復後 28 (消えた 9)。

## 4. 生成物の更新と assert の変更 (本 PR の差分の理由)

- **`spill37_1169.tsv` が古かった**: 生成元 `results/spill178_1161.tsv` は `f592bd2aa` (#3752) と `91d5c5ca4` (#3753) で 6 site を UNDETERMINED から TRUE_DROP に変えたが、`spill37_1169.tsv` (`30860c30b` 生成) は更新されていなかった。このため main の e2e は step 4 の `cmp` で既に FAIL していた。生成元から再生成して差し替えた (`spill37_1169.py` の出力を `cmp` 一致させた)。
  - 変わった行: 128c320 128cad6・128d007・128d495、128f9e0 12900c4、c343f0 c3460e、dcdde0 dcdeee の 6 site (UNDETERMINED → TRUE_DROP)。
- **`spill_repair_2794.tsv` の更新**: 上記 6 site が TRUE_DROP に入ったので、SKIPPED の 6 行が増えた (`fix_spill_2794.py` の出力そのもの)。
- **assert の数値**: `fix_d17_e2e.sh` の固定値を現在の件数に合わせた。
  - ネガコン 2 (`--gate none`): 24 → 30 (TRUE_DROP 全数)。
  - ネガコン 3 (`--gate 1to1`): 見送り 15 → 21 (増えた 6 件はいずれも 1to1 の根拠なし)。
  - ネガコン 4 (argi ずらし): 見送り 15 → 21 (同上)。
  - `fixed=9` と `callarg_ir_matches=0` の 4 件は変わらず。

## 5. 未解決

- 受入 1 の「1 対 1 の根拠の有無の記録」は本 REPORT §2 で行った。ただし `%stack_var_16` ↔ `[rbp+0x5b8]` の同一性は未確認のまま (解けない)。
- 局所スロット経由の 5 site を直すには、局所 IR 変数と `[rbp+d]` の対応を示す新しい根拠の型が要る。これは本 issue の範囲外で、必要なら別 issue として起票する (未起票)。
