# REPORT #2940 — spill 宛 TRUE_DROP の B 6 site の読み出し欠落の起点 (LD-141)

既知類型との関係: `docs/DEFECTS.md` の D4 (1 段 deref の脱落) と同型の「2 段 deref の潰れ」を含む。ただし欠落の機構は site ごとに違い、同一とは確定しないため DEFECTS の ID は付けない。X 形式の読み出し (10 進 VA の残り) は D11 の既知類型 (`tools/m11/REPORT_N1318.md`) に当たる (§4)。

親: #2794 (LD-130)。前提 PR #2915 は 2026-10-14T20:33:27Z に merge 済み (`main` に入っている)。

## 0. 結論

- B 6 site のうち **5 site の起点を特定した** (§2)。1003c20 は分岐の欠落 (lift 段)、12a4450 は loop 脱出の読みが IR で別の値 (`trunc(%indvars.iv)`) に置き換わっている、1046a30・11f16b0・ff8b60 は読み出しの欠落ではなく計数の差 (X 形式の読みの未計数 2 件・直前の読みの再利用 1 件)。
- **128c320 (site 128ca3f) は起点が未特定**。機械語 7 読みに対し IR 3 読み。残りの対応は支配関係の確定が要るため子 issue **#3612 [LD-168]** に移した。
- 判定 (TRUE_DROP) は 6 site とも変えない。store site の読みは 1 段に潰れており、TRUE_DROP の根拠は残る。変えたのは B の内訳だけ (§8)。
- 修復 pass・修復数 (9) は変えない。局所では 1 対 1 に見える 2 site (11f1785・104c3f0) は、関数単位のゲートの見直しを子 issue **#3613 [LD-169]** に移した。
- e2e `bash tools/m11/ldfix/fix_d17_e2e.sh` は rc=0 (§9)。

## 1. 測定条件

- 測定 commit: 本 REPORT の追加と同じ commit (コード変更は `tools/m11/ldfix/origin_b_2940.py` の新規追加だけ。修復の経路は変えていない)。測定 commit は §9 に書く。
- 素材: `work-m11` を `$RUNNER_TEMP/m11x` に展開し、`M11_WORK=$RUNNER_TEMP/m11x/tools/m11/work` で指定 (`tools/m11/work/` への展開は行わない)。`work-m11` は #516 以前の snapshot (REPORT_1169 §1 と同じ注意)。emcc は runner の `[EMSDK]`。`fl-win64`・`toolchain-retdec`・`toolchain-emsdk`・`work-liftdiff` は本 REPORT の e2e・スクリプトでは未使用 (`oc_artifacts` 行は既存の依頼どおり残す)。
- 実行: `bash tools/m11/ldfix/fix_d17_e2e.sh` (`TMPDIR` は `RUNNER_TEMP`、foreground)、`python3 tools/m11/ldfix/origin_b_2940.py` (機械語と IR の対応表)。

## 2. 判定 (B 6 site の起点)

M = 機械語で X (= K + 0x400000) を rip 相対で読む命令の数 (`origin_b_2940.py`、ImageMachine の線形 disasm)。I(K) = IR 内で `inttoptr (i64 K to ptr)` の行数 (audit の I と同じ定義)。I(X) = IR 内で `inttoptr (i64 X to ptr)` の行数 (audit の I は数えない・§4)。M は REPORT_2794 §3-2 の値 (2/3/3/7/4/2) と一致し、I(K) も §3-2 の値 (1/2/2/3/3/1) と一致する。

| # | 関数 | store site | K | M | I(K) | I(X) | 機械語の読み → IR の行 | 起点・内訳 | 判定 (B の内訳) |
|--:|---|---|---|--:|--:|--:|---|---|---|
| 1 | 1003c20 | 1003c73 | 11e2218 | 2 | 1 | 0 | 1003c4f → なし / 1003c69 → 857 | 分岐の欠落 (§3) | **欠落確定** |
| 2 | 1046a30 | 104c3f0 | 11e36d8 | 3 | 2 | 1 | 104c328 → 23534 (X 形式) / 104c343 → 23545 / 104c3e7 → 23594 | 計数 (X 形式を I が数えない) (§4) | **計数** (M = I = 3 で 1 対 1) |
| 3 | 11f16b0 | 11f1785 | 11e14a8 | 3 | 2 | 0 | 11f1742 → 49517 (`%15`) / 11f174e → 49517 を再利用 (CSE) / 11f177c → 49537 (`%24`) | 直前の読みの再利用 (§5) | **計数** (CSE・store site は局所で 1 対 1) |
| 4 | 128c320 | 128ca3f | 11e42e0 | 7 | 3 | 0 | 128ca36 → 74736 (`%314`) ほか 6 読み。対応未特定 (§7) | **未特定** | 未判定 → 子 #3612 |
| 5 | 12a4450 | 12a4531 | 11e26a0 | 4 | 3 | 0 | 12a4528 → 78582 (`%38`) / 12a4583 → 78626 (`%58`) / 12a45c6 → 78642 (`%68`) / 12a4513 → なし | loop 脱出で読みが `trunc(%indvars.iv)` に置換 (§6) | **欠落** (値の差し替え) |
| 6 | ff8b60 | ff8c63 | 11e0c60 | 2 | 1 | 1 | ff8c0c → 493273〜493275 (X 形式・P1 の 2 段読み) / ff8c5a → 493304 (`%57`) | 計数 (X 形式を I が数えない) (§4) | **計数** (M = I = 2 で 1 対 1) |

- 1: 欠落の位置は `1003c42 cmp [rax+0x794],0` → `1003c49 jge 1003c69` の不成立側 (1003c4b〜1003c63)。
- 4: 機械語の X 読み 7 本はすべて 2 段読み (`mov reg,[X]` + `[reg]`)。対応の残りは未特定 (§7)。
- 5: 差し替えの候補。IR の値が機械語と一致するかは IR だけからは証明できない (§6)。
- 6: P1 (`dec_label_pc_ff8bde`) の 2 段読みは IR で `%40 = load i64 (X 形式)` → `%41` → `%42 = load i32` と対応する。`%42` は 493276 行の `%43 = sext` を経て、493277 行の `%44` 呼び出しの第 7 引数になる。

## 3. 1 の欠落の根拠 (1003c20)

- 機械語 (1003c20〜1003d12): `cmp dword [rax+0x794],0` (1003c42) → `jge 1003c69` (1003c49)。不成立側 1003c4b〜1003c63 は `mov rcx,[rbp+0x60]`・`mov rax,[X]` (1003c4f)・`mov rax,[rax]`・`mov edx,[rax+0x10]`・`mov rax,[rbp+0x60]`・`mov rbx,[rax]`・`call [rbx+0x1a0]` を持つ。
- IR (845〜912 行): 直接 call は 855 行 (`function_4232e0`) を含めて 5 本だけで、間接 call は無い。`1940` (0x794) を含む比較は無い (`grep -n 'i64 1940\b' boot_final3.ll` の 845〜912 行の範囲は 0 件)。
- 主経路 (1003c69) は 857 行の `%5 = load i32 K` に対応する。IR の 856 行の直後にこの経路だけが続き、1003c42〜1003c63 の block は IR に無い。
- 結論: IR から不成立側 block と、その前の `cmp`・`jge` が丸ごと欠落している (lift 段の分岐の欠落)。REPORT_1169 §3 の (a) を機械語と IR の行番号で確認した。

## 4. 計数の差 (X 形式) — 2 と 6

- audit の I は `inttoptr (i64 K to ptr)` (K 形式) だけを数える (REPORT_2794 §2)。IR は同じ rip 相対セルを X 形式 (`inttoptr (i64 K+0x400000 to ptr)`) でも書いている。1046a30 は 23534 行 (`%ce81n11_function_1046a30 = inttoptr i64 22951640`)、ff8b60 は 493272 行 (`%ce5n11_function_ff8b60 = inttoptr i64 22940768`)。
- 2 site とも、K 形式と X 形式を合わせると M と一致する (gap 0)。K 形式だけでは gap 1 になる (ネガコン: `origin_b_2940.py` は I(K) 2・1 を出す)。
- 機械語の読みと IR の X 形式の読みの形は一致する。104c328 は `mov rax,[X]; mov [rax],ecx` (ポインタの 1 段読み + store) で、IR 23534〜23537 行の `%3322 = load i64` → `store i32 %3323, ptr %3324` と対応する。ff8c0c は `mov rax,[X]; mov eax,[rax]` (2 段読み) で、IR 493273〜493275 行の `load i64` → `inttoptr` → `load i32` と対応する。
- **注意 (未検証)**: X 形式の定数は、既定の build で VA のまま残る可能性がある。`m11_passes.py` の M2 は 16 進の `inttoptr i64 0x…` だけを LVA に直す。10 進の命令形を直す M2p は `M11_M2P=1` のときだけ動き、`.github` と `tools/m11/*.sh` に `M11_M2P` を設定する箇所は 0 件だった。10 進 VA の残りは `tools/m11/REPORT_N1318.md` と `docs/DEFECTS.md` D11 が既知の未解決として記録している (追跡 issue #417 は closed)。本 REPORT は**読みの対応**だけを判定する。X 形式の読みが実行時に同じセルを指すかは主張しない。
- 参考: 10 進 `inttoptr i64 N` の 24,482 件のうち、N が 0x1000000〜0x13fffff (K 形式の範囲) は 13,655 件、0x1400000〜0x17fffff (X 形式の範囲) は 1,213 件 (`grep -oE 'inttoptr \(?i64 [0-9]+' boot_final3.ll` の集計)。

## 5. 再利用 (CSE) — 3

- 11f1742 (`cmp dword [rax],7`) と 11f174e (`cmp dword [rax],0`) の間は `jg` だけで、store も call も無い。IR は 49517 行の `%15` を 49523〜49524 行の `%17`・`%18` の比較に使う。同じセルの値が 2 回の読みで同じ (書き込みが無い) ため、CSE は機械語の意味と一致する。
- store site の 11f177c (`mov rax,[X]; mov eax,[rax]`) は、49537 行の `%24 = load i32 K` と 1 対 1 に対応する (49536 行の `%23 = call 8da350` の直後の block 内)。
- REPORT_2794 の関数単位のゲート (M = 3 と I = 2 の不一致) が、この 1 対 1 を見送っている (§8・子 #3613)。

## 6. 差し替え — 5 (12a4450)

- 機械語 12a450a〜12a4524: `cmp [rbp+0x4c],0x1f5; jl 12a4524` の不成立側 (12a4513) は `mov rax,[X]; mov eax,[rax]; mov [rbp+0x4c],eax` で、ループ脱出の値 `*(*X)` を [rbp+0x4c] に書く。12a44e9 の `jge 12a450a` (ループ脱出) から入る。
- IR 78571〜78574 行 (`dec_label_pc_12a450a.split.loop.exit`): `%36 = trunc i64 %indvars.iv.reload to i32` を `%stack_var_-60.0.off0.lcssa.reg2mem` に書く。機械語の `*(*X)` の読み (K 形式) は IR に無い。
- IR の値 (induction variable) が機械語の値と等しいかは IR から証明できない。ここでは「読みが IR で別の値に置き換わっている」ことを確認するまでに留め、正しさは未検証 (§11)。
- store site 12a4531 は 78582 行 (`%38`) と 1 対 1 に対応する。`%38` は 12a4583 の store (78626〜78628 行) で使われる。

## 7. 未特定 — 4 (128c320)

- 機械語の X 読み 7 本: 128c832 (`mov r9,[X]`)・128c84a (`mov r10,[X]`)・128c86e (`mov rax,[X]`)・128ca36 (store site の `mov rax,[X]; mov eax,[rax]`)・128ca8e (`mov r8,[X]; mov r8d,[r8]`)・128caa6 (`mov r9,[X]; mov r9d,[r9]`)・128cacd (`mov rax,[X]; mov eax,[rax]`)。
- IR の K 読み 3 本 (i32): 74580 (`%222`)・74729 (`%.pre69`)・74736 (`%314`)。
- 128ca36 (store site) ↔ 74736 (`%314`) は 1 対 1 で確認した。残り 6 本と IR の 2 本 (74580・74729) の対応は、支配関係の確定が要る。
- 128ca42 以降の IR の join block (`dec_label_pc_128ca42`) には K 読みが無い (74751 行の `%319 = load i32 [18761688]` は別のセル)。128ca8e・128caa6・128cacd は、間接 call `[rsi+0x188]` (128cade) の引数準備にある。IR の対応する call の位置は本 run では特定しきれなかった。
- したがって起点は未特定。子 #3612 [LD-168] に移した。

## 8. 判定の扱い

- TRUE_DROP (6 site) は変えない。6 site の store site の読みは、いずれも IR で 1 段 (`load iN` の i32) に潰れている。これは TRUE_DROP の根拠であり、読みの欠落や計数の差では消えない。
- 変えたのは B の内訳だけ: 欠落確定 (1)・差し替え (5)・計数 (2・3・6)・未特定 (4)。
- `results/spill37_1169.tsv`・`results/spill_repair_2794.tsv` は変えない (e2e の `cmp` で一致を確認)。修復 pass (`fix_spill_2794.py`) も変えない。修復数は 9 のまま。
- 修復の見直し候補: 11f1785 (site 3) と 104c3f0 (site 2) は、局所で 1 対 1 だが関数単位のゲートで見送られている。子 #3613 [LD-169] に移した。

## 9. 検証 (受入 3) とネガコン

- e2e: `bash tools/m11/ldfix/fix_d17_e2e.sh` (`M11_WORK` 指定)。実測は §9-1 (commit を付けてから測る)。
- 対照 (ネガコン 1): K 形式だけを数えると gap = M − I(K) が 1 (2 と 6)。X 形式を数えると 0。計数の定義が 2 と 6 の gap の原因であることを示す。
- 対照 (ネガコン 2): gap が残る 1・3・4・5 は、X 形式を数えても消えない。1 は分岐の欠落 (§3)、3 は CSE (§5)、5 は差し替え (§6)、4 は未特定 (§7)。
- 独立算法: 機械語側は `audit_lsf.descend` の再帰降下ではなく、`ImageMachine.disasm_fn` の線形 disasm (.pdata の区間) で数えた。M は 6 site とも REPORT_2794 §3-2 と一致する。
- 検証範囲: `work-m11` の IR 1 本 (`boot_final3.ll`) と、その機械語 (`m11_image.bin`)。
- 範囲外: 修復後の wasm の実行、FLEngine の起動、X 形式の読みの実行時アドレス (§4 の注意)。起動・GUI に関わらないため、製品 KPI は測っていない。

### 9-1. 実測 (測定 commit と e2e)

- 測定 commit: `fc594f86a` (コードを変えた最後の commit。`origin_b_2940.py` の追加。修復の経路は変えていない)。
- 測定 commit からの差分 (修復の経路の範囲。空 = 0 件):

  ```
  git diff fc594f86a HEAD -- tools/m11/ldfix/fix_d17.py tools/m11/ldfix/fix_d17_e2e.sh tools/m11/ldfix/audit_lsf*.py tools/m11/ldfix/ldmach*.py tools/m11/ldfix/spill37_1169.py tools/m11/ldfix/fix_spill_2794.py tools/m11/ldfix/check_spill_2794.py tools/m11/ldfix/results tools/m11/lb_base.py
  (空: 差分 0)
  ```

- e2e `bash tools/m11/ldfix/fix_d17_e2e.sh` (HEAD で n=2): rc=0 / rc=0、real 47.17 s / 47.15 s、load average (1 分、実行前) 0.50 / 0.77。REPORT_2794 の測定 (46.84 s / 46.51 s) と同じ範囲。
- e2e の出力: 修復 9 / 見送り 15 (`spill fixed=9 skipped=15`)、spill 宛 CELL_COLLAPSED 37 → 28、`check_spill_2794.py` RESULT: PASS、ネガコン 2 (`--gate none`) は `spill fixed=24 skipped=0`、emcc `-c -O0 -g1` rc=0。
- `origin_b_2940.py`: 0.6 秒。M は 2/3/3/7/4/2、I(K) は 1/2/2/3/3/1 (§2)。

## 10. 検証の再現

```
M11_WORK=<tools/m11/work 相当の dir> python3 tools/m11/ldfix/origin_b_2940.py
M11_WORK=<同> bash tools/m11/ldfix/fix_d17_e2e.sh
```

## 11. 未解決と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 128c320 (128ca3f) の起点 (機械語 7 読み・IR 3 読み。残り 4 本の対応) | 1 site 未判定 | 子 #3612 [LD-168] (本 issue から移した) |
| 11f1785・104c3f0 の修復 (関数単位ゲートが局所 1 対 1 を見送る) | 修復候補 2 site が残る | 子 #3613 [LD-169] (本 issue から移した) |
| 12a4450 の loop 脱出の値 (`trunc(%indvars.iv)` と機械語の `*(*X)` の一致) | 値の正しさは未検証 | 子 #3612 に追記する (同じ関数・同じ site 群) |
| X 形式の 10 進 VA 残り (1046a30・ff8b60 の読みが実行時に同じセルを指すか) | 計数は直るが実行時の正しさは未検証 | 既存の未解決 `docs/DEFECTS.md` D11・`tools/m11/REPORT_N1318.md` (#417 は closed) |
| 修復 IR の実行検証 (FLEngine 起動) | 意味の正しさは機械語照合のみ | PM 判断 (#2794 と同じ扱い) |

## 12. 再現 (コマンドの詳細)

- 対応表: `M11_WORK=… python3 tools/m11/ldfix/origin_b_2940.py` (0.6 秒)。
- e2e: `M11_WORK=… bash tools/m11/ldfix/fix_d17_e2e.sh` (foreground、約 48 秒)。
- 素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff`。
