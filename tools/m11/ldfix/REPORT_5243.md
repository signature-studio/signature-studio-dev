# #5243 (LD-260) site ↔ IR i32 読み出しの対応を機械語の値の流れから作る方式の計測

**判定: 部分達成**。受入 1 (方式を決め REPORT に書く)・2 (決まらない site は未確認と明記) は達成。受入 3 (100b890 cell 11e27f0 の実測) は**未達**: 初回の §3 の記述は、同じ REPORT の §1 の出力と一致せず、再測定 (`work-m11`) の差分で確かめるまで採用しない (§3・§4・§5 参照)。
受入 4 (#4556 への 1 行返し) は本 run の最後にコメントで行う。方式の採否は既存規則の一部を変えるため、修復 pass への組み込みは別 issue (§5)。

## 1. 測定条件

- 測定 commit: `425347571` (origin/main。本 PR で追加するのは `tools/m11/ldfix/value_flow_5243.py`・`value_flow_5243_e2e.sh`・本 REPORT のみ)。
- 素材: `work-m11` (`tools/m11/work/`・`boot_final3.ll`・`m11_image.bin`)。`toolchain-emsdk` は本計測では不使用 (emcc は走らない)。
- 再現: `bash tools/m11/ldfix/value_flow_5243_e2e.sh` (foreground)。**下の出力は初回の run のもので、現 HEAD では未再現** (`work-m11` が無く実行できなかった)。再測定の結果は本節の末尾に追記する。

```
[value_flow_5243_e2e] 1/3 audit (修復前)
{"functions": 7421, "lsf_sites_arg": 90, "lsf_sites_unresolved": 370, "fns_unresolved": 169, "alg1_flagged_fns": 26, "alg2_flagged_fns": 38, "alg3_flagged_fns": 77, "alg1_or_alg2_fns": 41, "alg_any_fns": 83}
[value_flow_5243_e2e] 2/3 value_flow (base)
{"rule": "base", "linked": 11}
[value_flow_5243_e2e] 3/3 value_flow (rmw)
{"rule": "rmw", "linked": 13}
[value_flow_5243_e2e] base=11 rmw=13 added=2 removed=0
[value_flow_5243_e2e] ir_use(rmw)={'store': 9, 'icmp': 2, 'sub': 1, 'zext': 1}
```

差分の証跡: `git diff 425347571 HEAD -- tools/m11/ldfix/` は本 PR の追加分だけ (既存の `audit_lsf_ssa.py`・`link_d17.py`・`fix_d17.py` は変更なし)。

## 2. 方式 (受入 1)

修復報告 (`fix_spill_2794.py` の `fixed[].ir_name`) を使わず、機械語と IR の両方から以下だけで作る。

1. **機械側 chain** (`link_d17.mach_chains` と同じ抽出): `mov rA,[rip+X]` (K = X のセル) の直後 3 命令以内に、rA を基底にした `mov rD,[rA]` (disp 0)。途中で rA が壊れれば不採用。
2. **IR 側**: 同一 dec_label ブロック内の `load T, ptr inttoptr (K)`。
3. **結ぶ条件**: ブロック内で IR 読みが 1 本・chain が 1 本・幅一致。それ以外は結ばない (未確認として残す)。
4. **使用判定 (本計測で差を入れた箇所)**: rD が後続 8 命令以内で読まれるか。
   - `base` (既存): オペランド 1 以降の読みだけを数える。
   - `rmw` (提案): 2 オペランドの RMW 形 (`imul r32,m32`・`add`・`cmp` 等) では、宛先レジスタ自体も被演算子として読むと数える。

既存の `link_d17.py` は `base` 規則。`imul` の宛先兼被演算子を読みと数えないため、`imul` で使われる rD が「未使用」となる偽陰性があった。

## 3. 結果 (受入 3: 100b890 cell 11e27f0)

100b890 の K=11e27f0 (= 18753520) の IR i32 読み出しは 3 本 (`%6`・`%15`・`%23`)。機械側の読みは 100b8c7 (callarg)・100b8f2 (`%15` 側)・100b915 (`%23` 側) の 3 本。

| 規則 | 結べた読み | 結べない理由 |
|---|---|---|
| base (link_d17 と同じ) | 1 本 (`%6` ↔ 100b8ac の callarg store) | 100b8f2・100b915 が `dst_unused` (`imul` の宛先兼被演算子を未使用と数える) |
| rmw (提案) | **未検証** (再測定待ち) | — |

**未検証の記述 (撤回・再測定待ち)**: 初回の版は「rmw で 3 本 (`%6`・`%15`・`%23`) が結べ、`%15`・`%23` の消費命令は `%17 = mul`・`%28 = mul`」と書いていた。しかし同じ REPORT §1 の `ir_use(rmw)={'store': 9, 'icmp': 2, 'sub': 1, 'zext': 1}` には `mul` が 1 件も無く、`ir_consumer` (最初の使用行の opcode) の定義と矛盾する。この記述は検証前の推測として扱い、採用しない。

**再測定で確認すること**: `vf_base.json`・`vf_rmw.json` の差分 (key は `fn`・`k`・`blk`・`ir`) を出し、base から増えた行の `ir_use` と、100b890 の K=11e27f0 の行がどれになるかを記録する。

注意: 値の流れの「形」の一致も、実行時の値の一致も、現時点では確認していない。

## 4. 未確認 (受入 2)

- **rmw で追加された 2 件 (`added=2`)**: どの 2 件かは、この REPORT では特定していない。初回の版の `11d47c0` (K=11e4628)・`126bdb0` (K=11e3550) の icmp ↔ cmp という記述は、base に既にあった件との区別を確かめていないため撤回する。再測定の差分で特定する。
- **未結合の残り**: base の 11 件・rmw の 13 件以外は、link_d17 の既存表 (REPORT_1168 §6) の通り未確認。規則は採用していない。
- 修復の正しさ (実行時の値の一致) は未検証。

## 5. 結論 (受入 4 の返し)

- 方式 (§2) は採用候補。修復 pass には組み込まない (本 run の範囲外)。
- 100b890 cell 11e27f0 の mul 側 2 本が rmw で結べるか: **未確認** (§3 の再測定待ち)。
- 残件: (a) rmw 規則を `link_d17.py` に入れる判断と、その e2e への影響測定 → #2072 (LD-76) の受入 1・2 (値の流れで決める方式の実装) の範囲。(b) audit の判定粒度 (関数 × K → site 単位) → #4556 (LD-224) の範囲。
- 本 run では修復 pass を変えず、新規の子 issue も起票しない (a は #2072 の既存受入、b は #4556 の既存受入に入るため)。

## 6. 範囲外

- audit の判定を変えない (#4556 の範囲)。
- 修復 pass (`link_d17.py`) を変えない。
- 起動・GUI に関わらない IR 修復のため、製品 KPI は測っていない。
