# REPORT #2794 — spill 宛 TRUE_DROP 24 site の 1 対 1 判定と修復 pass (LD-130)

既知類型との関係: 機構は `docs/DEFECTS.md` の D4 (`mov r64,[r8]` の disp=0 の 1 段 deref の脱落) と同型の「2 段 deref が 1 段に潰れる」に近い。ただし同一とは確定しないため DEFECTS の ID は付けない (REPORT_1169 §冒頭の判断を継承)。

親: #1169 (LD-37)。本 issue は `docs/WORKFLOW.md` §3 の規定に従い、受入条件を満たした範囲に縮めて `Closes #2794` とする。残りは子 issue と PR 本文の未解決表に書く (§4)。

## 0. 結論

- TRUE_DROP 24 site のうち **9 site を修復**した。IR に K (セル) を読む load が 1 本、機械語にもセルの読み出しが 1 箇所だけという 1 対 1 の site に限る (`fix_spill_2794.py`)。spill 宛 CELL_COLLAPSED は **37 → 28 site**。
- 残り 15 site は直さない。6 site (B: #1・4・8・14・15・24) は IR の読み出しが機械語より少ない (lift 段の欠落の疑い) で、子 #2940 [LD-141] に移した (§3-2)。9 site (C: #2・6・7・13・17・18・20・21・22) は読み出し数は一致するが、どの読み出しが どの load に対応するか 1 対 1 に決まらないため、子 #2910 [LD-137] に移した。
- 受入条件 (#2794 本文を C 9 site を外して縮めた後の内容) を満たす: 15 site の判定記録 (§2)・1 対 1 の修復とネガコン (§4・§5)・残数の実測 (§5)・emcc 通過 (§5)・e2e 1 コマンド再現 (§8)。C 9 site の判定は子 #2910 の受入。

## 1. 測定条件

- 測定 commit: `95536527` (コードを変えた最後の commit: `fix(m11): assert the no-gate negative control count in e2e (#2794)`)。作業 worktree `ws-2915` (branch `2794-spill-true-drop-repair`。#2915 の差し戻し対応で追補)。前版の測定 commit は `f5b35a1d` (`fix(m11): repair spill TRUE_DROP sites with 1-to-1 machine check (#2794)`)、起点 `origin/main` = `40dd4460`。
- 素材: `work-m11` を `$RUNNER_TEMP/m11work` に展開し、`M11_WORK=<その tools/m11/work>` で指定 (`tools/m11/work/` への展開は行わない)。`work-m11` は #516 以前の snapshot で、結論はこの IR に限る (REPORT_1169 §1 と同じ注意)。emcc は runner 既存の `[EMSDK]` を使い、`toolchain-emsdk` の展開は不要だった。`work-liftdiff` は本 e2e では未使用 (受入の `oc_artifacts` 行には残す)。
- 実行: `bash tools/m11/ldfix/fix_d17_e2e.sh` (`TMPDIR` は `RUNNER_TEMP`、foreground)。
- 実測 (測定 commit `95536527`、n=2): real 46.84 s / 46.51 s、rc=0 / rc=0、load average (1 分、実行前) 0.71 / 0.87。前版 (`f5b35a1d`) の実測は real 46.50 s / 46.40 s、rc=0 / rc=0 で、同じ範囲。対照として、修復 pass を入れる前の `40dd4460` で同じ script の既存 5 step を回すと real 31.10 s、rc=0、load average 0.85 (1 分)。増分 15.30 s (46.40 − 31.10) は、修復 pass と修復後 audit (step 5) の追加による。
- 測定後の差分 (測定 commit から HEAD までのコード差分。この REPORT を追加する commit 以外は無い)。e2e が実行する依存 (`fix_d17.py`・`audit_lsf*.py`・`ldmach*.py`・`spill37_1169.py`・`lb_base.py`) と本修復の 3 本、結果 TSV を含む:

  ```
  git diff 95536527 HEAD -- tools/m11/ldfix/fix_d17.py tools/m11/ldfix/fix_d17_e2e.sh tools/m11/ldfix/audit_lsf*.py tools/m11/ldfix/ldmach*.py tools/m11/ldfix/spill37_1169.py tools/m11/ldfix/fix_spill_2794.py tools/m11/ldfix/check_spill_2794.py tools/m11/ldfix/results tools/m11/lb_base.py
  (空: 差分 0)
  ```

  前版 (`f5b35a1d`) から `95536527` までの変更は e2e 本体 (`fix_d17_e2e.sh`) のネガコン 2 の件数 assert だけ (m4)。修復の IR・判定・突合のコードは変えていない。

## 2. 判定 (受入 1): TRUE_DROP 24 site の 1 site ずつの記録

判定の軸: 機械語の site は `mov rA,[rip+X]; mov rD,[rA]` (depth 2) → `mov [rbp/rsp+d], rD`。IR 側は K = X − 0x400000 (IR 座標。全 37 site で同じ差) を `load iN, ptr inttoptr (K)` で読んでおり、値が 1 段で潰れている (V = `*X` を読まずに K を読む)。
M = 機械語で X に触れる rip 相対アクセスの数 (`audit_lsf.descend` の命令集合)、I = IR 関数内で `i64 K to ptr` が出現する数 (全幅・全用途。読み出しに限ると全 24 site で同数)。

| # | fn | site | K | M | I | 判定 | 根拠 |
|--:|---|---|---|--:|--:|---|---|
| 1 | 1003c20 | 1003c73 | 11e2218 | 2 | 1 | 欠落 (B) | 機械語 1003c4f (`jge` 不成立側) も X を読む。IR には無い。詳細は §3 |
| 2 | 100b890 | 100b8d0 | 11e27f0 | 3 | 3 | 対応未決 (C) | 読み出し数は一致。どれが site に対応するか未決 |
| 3 | 1046a30 | 10472ea | 11e3550 | 1 | 1 | **修復** | 1 対 1。i32 = 機械語 32 bit |
| 4 | 1046a30 | 104c3f0 | 11e36d8 | 3 | 2 | 欠落 (B) | IR の読み出しが 1 本少ない |
| 5 | 1046a30 | 104c56d | 11e3290 | 1 | 1 | **修復** | 1 対 1。i32 = 32 bit |
| 6 | 1046a30 | 104c769 | 11e2c50 | 2 | 2 | 対応未決 (C) | 読み出し数は一致 |
| 7 | 1046a30 | 104c9e6 | 11e28c8 | 3 | 3 | 対応未決 (C) | 読み出し数は一致 |
| 8 | 11f16b0 | 11f1785 | 11e14a8 | 3 | 2 | 欠落 (B) | IR の読み出しが 1 本少ない |
| 9 | 1221840 | 1221a63 | 11e3550 | 1 | 1 | **修復** | 1 対 1 |
| 10 | 1221bc0 | 1221c58 | 11dfc40 | 1 | 1 | **修復** | 1 対 1。§4 の例 |
| 11 | 1253260 | 12532d6 | 11e0338 | 1 | 1 | **修復** | 1 対 1 |
| 12 | 127fe20 | 127fef3 | 11e4d50 | 1 | 1 | **修復** | 1 対 1 |
| 13 | 1280530 | 12827e6 | 11dfda8 | 7 | 7 | 対応未決 (C) | 読み出し数は一致 |
| 14 | 128c320 | 128ca3f | 11e42e0 | 7 | 3 | 欠落 (B) | IR の読み出しが 4 本少ない |
| 15 | 12a4450 | 12a4531 | 11e26a0 | 4 | 3 | 欠落 (B) | IR の読み出しが 1 本少ない |
| 16 | 1354630 | 1354b99 | 11e4938 | 1 | 1 | **修復** | 1 対 1 |
| 17 | c589b0 | c5d2df | 11e1f40 | 4 | 4 | 対応未決 (C) | 同じ K の site が 2 本 (#18) |
| 18 | c589b0 | c5d343 | 11e1f40 | 4 | 4 | 対応未決 (C) | #17 と同じ K |
| 19 | e4f410 | e4f4e1 | 11e27f0 | 1 | 1 | **修復** | 1 対 1 |
| 20 | ea7ae0 | ea7c61 | 11e35c0 | 2 | 2 | 対応未決 (C) | 読み出し数は一致 |
| 21 | ea7ae0 | ea7c97 | 11e4a40 | 2 | 2 | 対応未決 (C) | 読み出し数は一致 |
| 22 | ea7ae0 | ea7cc8 | 11e1f98 | 2 | 2 | 対応未決 (C) | 読み出し数は一致 |
| 23 | f40840 | f43266 | 11e3a60 | 1 | 1 | **修復** | 1 対 1 |
| 24 | ff8b60 | ff8c63 | 11e0c60 | 2 | 1 | 欠落 (B) | IR の読み出しが 1 本少ない |

集計: 修復 9 (#3・5・9・10・11・12・16・19・23) / 欠落の疑い B 6 (#1・4・8・14・15・24) / 対応未決 C 9 (#2・6・7・13・17・18・20・21・22)。
機械可読の表は `results/spill_repair_2794.tsv` (`check_spill_2794.py` が出力し、e2e が `cmp` で照合する)。

- B (欠落の疑い): M > I。IR に機械語の読み出しが無い。どの block が落ちたかは site ごとには未特定 (§3 は 1003c20 のみの照合)。
- C (対応未決): M = I ≥ 2。読み出し数は合うが、対応付けの根拠 (支配関係・値の流れ) を持たないため触らない。
- M は `audit_lsf.descend` が辿る命令のうち rip 相対オペランドを持つもの (`rip_touches`) だけを数える。絶対アドレスや計算で得たアドレスで同じセルに触れるアクセスは数えない。1 対 1 ゲートは必要条件であって十分条件ではない (同じセルへの別経路の読み出しは見えない)。

## 3. 1003c20 の IR 照合 (REPORT_1169 §3 の未検証項目)

REPORT_1169 §3 が「未検証」とした 1003c20 を、機械語と IR で照合した。

- 機械語: 1003c42 `cmp dword ptr [rax+0x794], 0` → 1003c49 `jge 0x1003c69`。不成立側 (1003c4b〜1003c63) で `mov rax,[rip+X]; mov rax,[rax]; mov edx,[rax+0x10]; call qword ptr [rbx+0x1a0]` を実行する。X = 0x15e2218 は 1003c4f と 1003c69 (主経路) の 2 箇所で読まれる (M = 2)。
- IR `function_1003c20` (`boot_final3.ll` 845〜912 行): K = 0x11e2218 の読み出しは 1 本 (`%5 = load i32, ptr inttoptr (i64 18752024)`)。定数 1940 (0x794) の比較は無く、間接 call (`call [rbx+0x1a0]`) も無い。IR の call は直接 5 本 (`function_4232e0`・`function_663aa0`・`function_423980`・`function_bd68e0`・`function_11d5520`)。
- よって (a) 不成立側のブロックが IR から丸ごと欠落している (lift 段の欠落)、(b) 1003c73 は IR i32 に対して機械語が 64 bit の store (幅が一致しない)。どちらも 1 対 1 ではないため、この site は修復していない。
- REPORT_1169 §3 の「IR と機械語の対応が取れていない兆候」は、(a) (M=2・I=1 と間接 call の欠落) で裏付けられた。

### 3-2. B 6 site の機械語・IR の行番号 (子 #2940 の本文と同じ)

M = `rip_touches` で数えた機械語の読み出し命令のアドレス。I の行 = `boot_final3.ll` で `i64 K to ptr` が出る行 (`grep -n`)。関数範囲は IR の `define` から `}` までの行。

| 関数 | store site | K | M / I | 機械語の読み出し (命令アドレス) | IR の K の load (行) | IR 関数範囲 (行) |
|---|---|---|--:|---|---|---|
| 1003c20 | 1003c73 | 11e2218 | 2 / 1 | 1003c4f, 1003c69 | 857 | 845–912 |
| 1046a30 | 104c3f0 | 11e36d8 | 3 / 2 | 104c328, 104c343, 104c3e7 | 23545, 23594 | 16267–24295 |
| 11f16b0 | 11f1785 | 11e14a8 | 3 / 2 | 11f1742, 11f174e, 11f177c | 49517, 49537 | 49474–49605 |
| 128c320 | 128ca3f | 11e42e0 | 7 / 3 | 128c832, 128c84a, 128c86e, 128ca36, 128ca8e, 128caa6, 128cacd | 74580, 74729, 74736 | 74166–76137 |
| 12a4450 | 12a4531 | 11e26a0 | 4 / 3 | 12a4513, 12a4528, 12a4583, 12a45c6 | 78582, 78626, 78642 | 78475–78729 |
| ff8b60 | ff8c63 | 11e0c60 | 2 / 1 | ff8c0c, ff8c5a | 493304 | 493210–493326 |

- 6 site とも M > I。IR の K の読み出しが機械語より少ない (読み出しが欠けている)。どの block が落ちたかは、この表では特定していない (起点の特定は子 #2940)。
- 1003c20 の (a) (不成立側の欠落) は §3 で確認済み。他の 5 関数は未確認。

## 4. 修復 pass (受入 2)

`tools/m11/ldfix/fix_spill_2794.py`。入力は fix_d17 の出力 IR と audit の cell 情報、判定 TSV。対象は判定 TRUE_DROP ∩ spill 宛 CELL_COLLAPSED (24 site)。次の 3 条件をすべて満たす site だけを直す。

1. 機械語: 関数内で X に触れる命令が 1 つ (`mov reg,[rip+X]` の読み出し)。
2. IR: 関数内で `i64 K to ptr` の出現が 1 つ、かつそれが `load iN, ptr inttoptr (K)` (N は整数幅。`ptr` は対象外)。
3. 幅: N = 機械語 store の幅 w。

修復は `fix_d17.py` と同じ 2 段分割: `%v = load iN, ptr inttoptr K` を `%cellps.K = load ptr, ptr inttoptr K` と `%v = load iN, ptr %cellps.K` に置き換える。store の有無は要らない (直すのは K の load だけ)。

例 (1221bc0 1221c58。機械語 `1221c4f: mov rax,[rip+0x3bdfea]` → `1221c56: mov eax,[rax]` → `1221c58: mov [rbp+0x4c],eax` と照合):

```
- %16 = load i32, ptr inttoptr (i64 18742336 to ptr), align 8
+ %cellps.11dfc40 = load ptr, ptr inttoptr (i64 18742336 to ptr), align 8
+ %16 = load i32, ptr %cellps.11dfc40, align 8
```

直した IR は `%16 = select` の分岐 (`test eax,0x30000; je`) と同じ位置で使われ、機械語の意味と一致する。

修復後の audit では、直した 9 site が CELL_COLLAPSED から CELL_DEEP へ移った。見送った 15 site は CELL_COLLAPSED のまま残る。
alg1/alg2/alg3 のフラグ数は、spill 修復では変わらない。比較元は fix_d17 後の audit (e2e step 3) で、alg3 58 / alg_any 65。spill 修復後の audit (step 5) も同じ値。原 IR (step 1) からは alg3 77 → 58、alg_any 83 → 65 に変わるが、これは fix_d17 (step 2) による変化で、spill 修復による変化は 0。

## 5. 検証 (受入 3・4) とネガティブコントロール

| 項目 | 修復前 | 修復後 |
|---|--:|--:|
| spill 宛 CELL_COLLAPSED site (`audit_lsf_ssa.py`) | 37 | 28 |
| うち TRUE_DROP 24 site の残数 | 24 | 15 |
| 修復した site | - | 9 |

- 突合 `check_spill_2794.py` (修復前後の audit と報告を照合): C1 修復後の集合 ⊆ 修復前の集合、C2 消えた集合 = 報告の修復集合、C3 修復は TRUE_DROP だけ。3 つとも満たして `RESULT: PASS` (rc=0)。
- ネガコン 1 (修復を外す): 修復後 audit の代わりに d17 のみの audit を渡すと `FAIL C2: 消えた site 0 件 != 修復した site 9 件` (rc=1)。e2e で FAIL することを確認している。
- ネガコン 2 (1 対 1 ゲートを外す): `--gate none` で 24 件を書き換える (ゲートあり 9 件)。残り 15 件は読み出しが複数ある関数で、先頭の K 読み出しを任意に選ぶことになる。ゲートは誤修復の防止に必要。e2e は出力の `spill fixed=24 skipped=0` を grep で assert する (一致しなければ rc=1。`95536527` で追加)。
- emcc: 修復 IR (`boot_spill.ll`) を `emcc -c -O0 -g1` で通す (rc=0)。
- e2e: `bash tools/m11/ldfix/fix_d17_e2e.sh` rc=0 (測定 commit で n=2、§1)。

## 6. 検証範囲 / 範囲外

- 範囲: `work-m11` の IR 1 本 (`boot_final3.ll`) に対する audit と修復・emcc 構文検証。
- 範囲外: 修復 IR を使ったビルド後の wasm の実行 (FLEngine の起動・boot の挙動)。本 issue ではやっていない。修復の正しさは、機械語との 1 対 1 照合と audit の再判定による。実行での確認は PM 判断。
- 起動・GUI に関わらない IR 修復のため、製品 KPI (FLEngine 起動の dispatch 数等) は測っていない。

## 7. 未解決と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 対応未決 9 site (C 分類: #2・6・7・13・17・18・20・21・22。読み出し数は一致、対応付けの根拠なし) | spill 宛 CELL_COLLAPSED 28 のうち 9 が残る | 子 issue #2910 [LD-137] (#2794 本文から移した) |
| 読み出し欠落 6 site (B 分類: #1・4・8・14・15・24。IR の読み出しが機械語より少ない。§3-2) | 修復できない。lift 段の欠落の起点は未特定 | 子 issue #2940 [LD-141] (本 PR で起票。#2705 (LD-125・`128f9e0` 専用) とは別の関数) |
| 判定不能 7 site (UNDETERMINED) | 判定なし。修復対象外 | #2253 (LD-95) (既存) |
| NO_CONSUMER 4 site・OK_LOAD 2 site | 判定確定どおり修復対象外 | — (判定確定) |
| 修復 IR の実行検証 (FLEngine 起動) | 意味の正しさは機械語照合のみ | PM 判断 (本 issue の範囲外) |
| `work-m11` が #516 以前の snapshot | 結論はこの IR に限る | 現 main の IR 再生成は REPORT_1169 §5 と同じ扱い (本 issue では行わない) |

## 8. 再現

```
bash tools/m11/ldfix/fix_d17_e2e.sh
```

素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff` (`work-m11` が必須。emcc は runner の `[EMSDK]`)。判定の入力は `results/spill37_1169.tsv` (TRUE_DROP だけを修復対象にする)。
修復後の突合の出力は `results/spill_repair_2794.tsv`。

## 9. 検収用の検算

- `check_spill_2794.py` は audit の CELL_COLLAPSED 集合の差分で突合する。`fix_spill_2794.py` が出した修復リストと独立に、消えた site の集合だけから判定する (C2)。
- 1 対 1 ゲートの M は `audit_lsf.descend` の命令集合で数える。試行では `disasm_fn` (線形逆アセンブル) でも数え、TSV の M が一致することを e2e の `cmp` で確認した (修復 9 件・見送り 15 件)。
