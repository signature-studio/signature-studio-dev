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

## 8. rewrite_va の argpos 補正 (#4982 / CI-204)

§3 の「判定器の欠陥」を直した。`rewrite_va` を持つ行は `deref_reg` の argpos ではなく、deref から call までの `mov` 複写で値を運んだ先の引数レジスタの argpos で判定する (`rewrite_argpos`)。値が引数レジスタへ届かない行は `REWRITE_NOARG` (判定不能)。あわせて `closure()` が reg2mem の枠 (alloca への store → load) を追うようにした (0x43adf0 の `%rsi.0.reg2mem` 経由で `%arg3` に届く形)。

- 測定 commit: `f343fa38b` (`git diff f343fa38b HEAD -- tools/m11/ldfix/` は本節の追記のみ)。
- 素材: §1 と同じ (`block00031_PE.bin`・`boot_final3.ll`)。scan は §1 の `scan_spill_deref_3328.py` の出力をそのまま使う (scan 側は未変更)。
- 再現: `python3 tools/m11/ldfix/judge_copy_3382.py tools/m11/work/boot_final3.ll --pe <PE> --scan <json> --out <json>` → `ERR_BARE 14 / UNCLEAR 14 / REWRITE_NOARG 5 / ERR_CAND 47 / MISMATCH 13 / OK_ARGK 10` (0.39 s・load average 0.16 / 0.27 / 0.15)。
- 補正前: `ERR_BARE 14 / ERR_CAND 57 / UNCLEAR 16 / MISMATCH 14 / OK_ARGK 2`。

### 変わった行 (14 件・旧→新)

| 関数 | deref → call | callee | 旧 argpos/判定 | 新 argpos/判定 |
|---|---|---|---|---|
| 0x1280250 | 0x12802a6 → 0x12802ba | 0x823c30 | 1 / UNCLEAR | - / REWRITE_NOARG |
| 0x1280380 | 0x12803f5 → 0x128040f | 0x660a00 | 1 / ERR_CAND | - / REWRITE_NOARG |
| 0x414370 | 0x4143b3 → 0x4143c2 | 0x409c80 | 1 / ERR_CAND | 1 / OK_ARGK |
| 0x416db0 | 0x416e3e → 0x416e41 | 0x413540 | 2 / ERR_CAND | 2 / OK_ARGK |
| 0x439f90 | 0x43a0e7 → 0x43a0fa | 0x409c80 | 3 / MISMATCH | - / REWRITE_NOARG |
| 0x43adf0 | 0x43ae29 → 0x43ae32 | 0x4399e0 | 1 / ERR_CAND | 2 / OK_ARGK |
| 0x44b380 | 0x44b392 → 0x44b3a2 | 0x44b2b0 | 1 / UNCLEAR | - / REWRITE_NOARG |
| 0x44fa30 | 0x44fa61 → 0x44fa6c | 0x44f110 | 2 / ERR_CAND | 2 / OK_ARGK |
| 0x44fab0 | 0x44fadf → 0x44fafd | 0x44fb40 | 2 / ERR_CAND | 2 / OK_ARGK |
| 0x65e3c0 | 0x65e3e5 → 0x65e3e8 | 0x414e70 | 2 / ERR_CAND | 2 / OK_ARGK |
| 0x79da80 | 0x79dac3 → 0x79dac6 | 0x40faa0 | 1 / ERR_CAND | 1 / OK_ARGK |
| 0x8e5f80 | 0x8e6001 → 0x8e600d | 0x414890 | 2 / OK_ARGK | - / REWRITE_NOARG |
| 0x9635d0 | 0x963650 → 0x963660 | 0x9648f0 | 2 / ERR_CAND | 2 / OK_ARGK |
| 0xf552a0 | 0xf55399 → 0xf5539c | 0x12df760 | 1 / ERR_CAND | 1 / OK_ARGK |

### 窓との照合

- **0x43adf0 → OK_ARGK (argpos 2)**: 窓 (#4973 のコメントと本 run の再読) で、`mov rcx,[rsi]` (0x43ae29) → `mov rdx,rcx` (0x43ae2c) → `mov rcx,rax` (0x43ae2f) と確認。値は argpos 2 に届く。IR は `%15 = load(%14)`・`%14 = inttoptr %rsi.0.reload`・`%rsi.0.reload` は `store %arg3` の reg2mem 枠で、`%arg3` 由来の load として閉包に入る。窓の「一致の見込みは高い」と整合する。値の一致そのものは未確定。
- **0x439f90 → REWRITE_NOARG**: 0x43a0e7 の `mov r8,[rbx]` の後、0x43a0ea〜0x43a0f7 で `sub/sar/adc/add` により r8 が計算値になり、その値を 0x43a0fa で渡す。`*argK` そのものではない。窓の「判定不能」と整合する。
- **0x8e5f80 OK_ARGK → REWRITE_NOARG**: 0x8e6001 の `mov rdx,[rbx]` の後、0x8e6007 の `movzx rdx, word ptr [...]` で rdx が上書きされ、0x8e600d の call では rdx が別の値。deref の値は call へ届かない。補正前の OK_ARGK は誤りだった。
- **0x44b380 UNCLEAR → REWRITE_NOARG**: 0x44b392 の deref 値は 0x44b39d で rcx を再ロードして上書きされ、0x44b3a0 の `mov edx,eax` は別の値。届かない。
- **0x1280250・0x1280380 → REWRITE_NOARG**: 0x12802b5・0x12803f8 の rewrite で値が計算に入る形。届かない。窓は未確認。

窓で確認したのは 0x43adf0・0x439f90・0x8e5f80・0x44b380 の 4 件 (本節)。変わった 14 件のうち、残る 10 件 (0x1280250・0x1280380 と、ERR_CAND→OK_ARGK の 0x414370・0x416db0・0x44fa30・0x44fab0・0x65e3c0・0x79da80・0x9635d0・0xf552a0) は窓の判定が未了。OK_ARGK は閉包判定の一次分類であり、一致の確定ではない。

### 数の読み方

- 補正後の `OK_ARGK 10` は、閉包が arg と load を含むという一次分類。窓の確認は上の 4 件だけ。
- `REWRITE_NOARG 5` は判定不能。誤りとも正しいとも決めない。
- MISMATCH 13 件 (補正前 14) は、0x439f90 の 1 件が REWRITE_NOARG に移った分。区分 A・B・C の内訳は #4973 の記録の通り。
