# REPORT_3382 — COPY 候補 (複写経由・直接呼出し) 103 箇所の IR 側一次判定 (#3382 / CI-153)

親: #3328 (CI-149, CLOSED)。候補の定義は `REPORT_3328.md` §1・§4。判定の対象は `scan_spill_deref_3328.py` の COPY (49 関数 / 103 箇所)。

## 0. 結論

- COPY 103 箇所を機械で一次分類した (`judge_copy_3382.py`)。**確定判定はまだ無い**。一次分類は「誤り候補」「判定不能」の振り分けであり、窓の人手読みが最終判定になる (REPORT_2555 §5 と同じ位置づけ)。
- 一次分類の内訳: **ERR_BARE 14 / ERR_CAND 57 / UNCLEAR 16 / MISMATCH 14 / OK_ARGK 2** (合計 103)。
- 0x7888f0 の未判定 2 箇所 (0x78890f・0x78892d) のうち、**0x78892d は誤り** (IR が `%arg2` を裸で渡し、機械語は `*arg1`)。**0x78890f は判定保留** (IR が定数 `0` を渡す。別経路の可能性を排除できない)。
- 全数の人手判定は本 run の時間に収まらなかった。残りは子 issue に移す (§6)。

## 1. 数え方と再現

- 素材: `block00031_PE.bin` (fl-win64 26.1.7.5653・sha256 `b2c64da4…9496d`)。IR は `work-m11` の `boot_final3.ll` (sha256 `010451add…7de17e7ce43de7cb9e`、gitignore の `tools/m11/work/`)。REPORT_3328 §2 と同じ指紋。
- 走査: `python3 tools/m11/ldfix/scan_spill_deref_3328.py tools/m11/work/boot_final3.ll --pe <PE> --out <json>` → `CALL 11 関数 13 箇所 / CMP 13 関数 20 箇所 / COPY 49 関数 103 箇所 / EXCL 3 関数 3 箇所` (実行 4.9 s・load average 0.29 / 0.20 / 0.09)。REPORT_3328 §2 と一致。
- 一次分類: `python3 tools/m11/ldfix/judge_copy_3382.py tools/m11/work/boot_final3.ll --pe <PE> --scan <json> --out <json>` → `ERR_BARE 14 / ERR_CAND 57 / UNCLEAR 16 / MISMATCH 14 / OK_ARGK 2` (実行 0.4 s)。
- 窓: `python3 tools/m11/ldfix/show_site_2555.py tools/m11/work/boot_final3.ll --pe <PE> <関数 VA> <call VA>`。

### 一次分類の定義 (`judge_copy_3382.py` の `judge`)

機械語は `*argK` を呼出し先の argpos 番目へ渡す。同じ呼出し先への k 番目の IR 呼出しの argpos 番目の引数 `a` を見る。

| 判定 | 条件 | 意味 |
|---|---|---|
| ERR_BARE | `a` が裸の `%argM` | 機械語は `*argK` (値) を渡すのに、IR はアドレス `%argM` を渡す。**誤り候補 (強)** |
| ERR_CAND | `a` の定義閉包に `%argK` が無い | 値が一致しない見込み。ただし定数・別式の経路も含む。**誤り候補 (弱)** |
| OK_ARGK | `a` の定義閉包に `%argK` と load がある | 一致候補 |
| UNCLEAR | `a` の定義閉包に `%argK` があるが load が無い | 人手判定 |
| MISMATCH | IR と機械語の呼出し件数が違う・k 番目が無い | 判定不能 |

「定義閉包」は `a` の SSA 定義を推移的にたどった行の集合 (上限 40 行。引数名 `%argN` で止める)。

## 2. 窓の確認 (人手で読んだ 6 件)

| 関数 | deref → call | 機械語の渡す値 | IR の該当引数 | 判定 | 根拠 |
|---|---|---|---|---|---|
| 0x7888f0 | 0x78892d → 0x78893d (`414ec0`, argpos 2, k=1) | `*arg1` (`mov rdx,[rbx]`) | `%arg2` (裸) | **誤り** | ERR_BARE・窓で確認 |
| 0x7888f0 | 0x78890f → 0x788912 (`43c3f0`, argpos 2, k=1) | `*arg1` (`mov rdx,[rbx]`) | `i64 0` (定数) | **保留** | IR の `43c3f0` 呼出しは 1 件・引数は定数 0 のみ。別経路の可能性を排除できない |
| 0x44f440 | 0x44f501 → 0x44f50f (`414da0`, argpos 3, k=1) | `*arg1` (`mov r8,[rbx]`) | `%arg1` (裸) | **誤り** | ERR_BARE・窓で確認。判定器の argpos の取り方を確認した (`r8` = 3 番目) |
| 0x41c650 | 0x41c685 → 0x41c688 (`414850`, argpos 1, k=1) | `*arg1` (`mov rcx,[rbx]`) | `%arg1` (裸) | **誤り** | ERR_BARE・窓で確認 |
| 0x79da80 | 0x79da9e → 0x79dab4 (`6edf50`, argpos 1, k=1) | `*arg2` (`mov rcx,[rsi]`) | `%arg2` (裸) | **誤り** | ERR_BARE・窓で確認 |
| 0x1280250 | 0x12802dd → 0x12802e2 (`73ca40`・argpos 1) | `*arg2` (`mov rcx,[rsi]`) | `i64 0` (定数) | **保留** | 0x1280250 の 11 件のうち ERR_CAND 5・UNCLEAR 5・ERR_BARE 1。IR の引数が定数の例 |

- 窓の確認で、判定器の argpos の取り方 (機械語の引数レジスタ rcx=1・rdx=2・r8=3) は正しいことを確かめた。
- 0x1280250 (11 件) と 0x1280380 (13 件) は、計 24 件のうち ERR_CAND 15・UNCLEAR 7・ERR_BARE 2 (実測)。IR 側が定数・`%9` などの式を渡しており、閉包判定だけでは誤り・正のどちらにも決まらない。

## 3. ERR_BARE (強い誤り候補)

ERR_BARE 14 件 (deref VA → call VA。`judge_copy_3382.py` の出力): 0x1280250 (0x1280271→0x1280274)・0x1280380 (0x12803a1→0x12803a4)・0x40fcf0 (0x40fd0b→0x40fd11)・0x41c0a0 (0x41c0b2→0x41c0bc)・0x41c650 (0x41c685→0x41c688)・0x41c780 (0x41c7b5→0x41c7b8)・0x44f440 (0x44f501→0x44f50f)・0x4504e0 (0x45050d→0x450510)・0x5b03a0 (0x5b040f→0x5b0412)・0x79da80 (0x79da9e→0x79dab4・0x79dab9→0x79dabe・0x79dc23→0x79dc32)・0x7888f0 (0x78892d→0x78893d・0x788954→0x788957)。
- 窓で確認したのは 0x7888f0・0x44f440・0x41c650・0x79da80 の一部 (§2)。0x1280250・0x1280380・0x40fcf0・0x41c0a0・0x41c780・0x4504e0・0x5b03a0 は窓未確認。

- 0x788954 は REPORT_2555 §2 で誤り判定済み。0x78892d も同じ形で、窓で誤りと確認した (§2)。
- 機械語の deref が後段で書き換えられる場合 (`rewrite_va`) は、窓で確かめる必要がある。COPY で `rewrite_va` を持つのは 6 件 (0x1280250・0x1280380・0x439f90・0x43adf0・0x44b380・0x8e5f80) で、いずれも未判定。

## 4. 検証した判定器の性質

- 判定器の argpos の取り方 (機械語の引数レジスタ rcx=1・rdx=2・r8=3) は、0x44f440 (r8) の窓で確かめた。
- OK_ARGK 2 件: 0x41b850 (`4106f0`・`%13`) と 0x8e5f80 (`414890`・`%35`)。どちらも IR の引数の定義閉包に `%argK` と load がある。窓の確認は未了。
- ERR_CAND 57 件は、定義閉包に `%argK` が無いというだけの弱い根拠。定数 (`i64 0` など) と別式が含まれ、誤りとは断定できない。

## 5. 判定不能 (MISMATCH) の内訳

- 0x4130c0・0x4398f0・0x439930・0x51abb0: IR の呼出しが 0 件か 2 件 (機械語 1 件)。呼出し対応が取れない。
- 0x439f90 (4 件): REPORT_2555 §5 と同じ関数。`414850`・`44ba40`・`409c80` の件数が機械語と IR で一致しない。
- 0xf552a0 (6 件): IR 5 件 / 機械語 6 件。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| COPY 103 箇所の窓の人手判定 (ERR_BARE 14・ERR_CAND 57・UNCLEAR 16) | 複写経由の取りこぼしの確定数 | 子 #4211 [CI-186] |
| 0x78890f (IR 定数 0) と 0x1280250・0x1280380 の定数引数 (計 24 件のうち ERR_CAND 15・UNCLEAR 7) の判定 | 保留の件数 | 子 #4211 [CI-186] |
| MISMATCH 14 件の判定不能 (呼出し件数の不一致) | 判定不能の件数 | 子 #4211 [CI-186] |

## 7. 検証範囲

- 範囲内: COPY 103 箇所の一次分類と、0x7888f0 の 3 箇所の窓での確認。
- 範囲外: 全 103 箇所の人手判定、修復、ldfix_e2e の実測。
- 測定 commit: この PR の最後のコード commit。`judge_copy_3382.py` は本 PR で追加した。

## 8. ERR_CAND 57 件の窓による人手判定 (#4972 / CI-201)

- 対象: `judge_copy_3382.py` の ERR_CAND 57 件 (定義閉包に `%argK` が無い)。全 57 件の窓 (`show_site_2555.py --before 6`) を読んだ。
- 結果: **誤り 0 / 正常な参照 2 / 判定不能 55** (判定不能 = 定数・定数式 18 + 別式 37)。誤りと断定できた件は無い。
- 正常な参照 (2): 0x414120 → 0x414194 (#16) と 0x414ad0 → 0x414b4c (#19)。機械語は `[rbp+0x28]+0x10` を `[rbx]` に格納してから `[rbx]` を読んで渡す。読む値は自関数の書込みで、ERR_CAND の前提 (`*argK` を渡す) に当たらない。IR の `stack_var_-48` との同一性は窓外で未確認。
- 判定不能 (55) の内訳:
  - IR 引数が定数・定数式 (18): 0x1280250 の 5 件・0x1280380 の 8 件・0x419750・0x5b03a0・0x60a420・0x707f10・0x7888f0 の 1 件ずつ。機械語は `*argK` を読むが、IR の定数が同じ値かは呼出し元の窓外。
  - IR 引数が別引数・計算式由来 (37): 窓の定義閉包で `%arg2`/`%arg3` 由来と分かっても、機械語の `*argK` と IR の対応は決まらない。
- 0x1280250 (#1): 機械語は `rsi = rdx = arg2`。0x128028f で `*arg2` が null の経路だけ `[rsi]` に新しい値を書き、0x12802dd で `*arg2` を再読みして 0x73ca40 の第 1 引数に渡す。IR の `%23 = call @function_73ca40(i64 0, i64 8)` は定数 0。0x73ca20 の呼出しを挟むため、`*arg2` が 0 に畳まれたかは確定できない。**判定不能 (保留)**。
- 0x1280380 (#6〜#15): 関数先頭で `rsi = rdx = arg2` (0x128038e `mov rsi, rdx`) を確認。IR の引数は `%25`・`%27` の式・定数・`%ce*` の定数式が混在し、`*argK` との対応は窓外。**判定不能**。
- 0x1280250・0x1280380 の定数引数 (受入条件 3): 定数の出所を窓で確かめた。`*arg2` を null 判定した後の書込み (0x128028f) と、その後の再読みが IR で 0 になるかが焦点。書込み先の値の出所は呼出し先 0x7372a0 の戻り値で、本 REPORT の窓の外。**判定不能で止める**。

### 再現

```
python3 tools/m11/ldfix/scan_spill_deref_3328.py tools/m11/work/boot_final3.ll --pe <PE> --out <scan.json>
python3 tools/m11/ldfix/judge_copy_3382.py tools/m11/work/boot_final3.ll --pe <PE> --scan <scan.json> --out <judge.json>
python3 tools/m11/ldfix/classify_err_cand_4972.py <judge.json> --md <out.md>
```

- scan: `COPY 49 関数 103 箇所` (REPORT_3328 §2 と一致)、judge: `ERR_BARE 14 / ERR_CAND 57 / UNCLEAR 16 / MISMATCH 14 / OK_ARGK 2` (§0 と一致)。
- classify: `ERR_CAND 57 件: 判定不能 55 / 正常な参照 2`。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 判定不能 55 件の確定 (定数 18 + 別式 37、0x1280250・0x1280380 の定数引数を含む) | 複写経由の取りこぼしの確定数は未確定 | #4993 [CI-205] |
| 0x7372a0・0x73ca20 の副作用 (`*arg2` の書込み) の確認 | 0x1280250 #1 の定数 0 の正否 | #4993 [CI-205] |
