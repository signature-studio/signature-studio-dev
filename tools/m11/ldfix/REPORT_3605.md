# LD-167 (#3605): F3d 適用 IR で 4 site (45d570・45d581・45b1bf・45f938) の store 実行を判定 (部分達成)

既知類型との関係 (docs/DEFECTS.md): 該当なし。上流 xor 0 (LD-127 #2745 の F3d) の判定追跡であり、新類型は無し。

## 1. 結論

- F3d を含めて IR を再生成し、`ir_conditions.json` の `ldfix=applied` を確認した (F3d=58・xor 0 行 3886 → 3828)。
- 監査 `audit_lsf_ssa_e2e.sh` を前景で実行し **rc=0・全ステップ一致** (§4)。
- 4 site の判定: **結論を変えられるほどの根拠は揃わなかった**。`results/` は更新していない (4 site とも UNDETERMINED のまま)。
  - 45d570・45d581: store を囲む分岐の述語と機械語 jcc が、同じ読み込み値 W = `word[arg1]` で同じ arm を選ぶことを確認 (§2)。OK_LOAD の候補。ただし `45d381` 直前の `eax = W` の確認が残るため、results は更新しない。
  - 45b1bf: P の store と 2 段目の load の間に store が無いことを IR で確認 (§3)。ただし dead edge `45b1a1→45b1b1` の上流は未照合。
  - 45f938: 局所の jcc (45f847・45f84c) は一致。0x4000 判定から 45f831 までの上流経路は未照合。
- 本 PR は issue の受入を全て満たさないため `Refs #3605`。

## 2. 45d570・45d581 の述語照合 (F3d 後 IR `boot_final3.ll` と機械語 `block00031_PE.bin`)

W = 機械語 45d0b5 `movzx rax, word ptr [rax]` (rax = [rbp+0x50] = arg1) = IR `%ldfxt15 = load i16 [arg1]` (F3d 挿入)。`%3 = zext W`。

| 段 | IR (述語) | 機械語 (jcc) | 対応 |
|---|---|---|---|
| 1 | `%122 = and %3, 16384`・`%123 = icmp eq %122, 0`・`br %123 → 45d5a9` | 45d381 `mov ecx,eax`・45d383 `test cx,0x4000`・45d388 `je 45d5a9` | 同じ判定 (bit 0x4000 が 0 なら 45d5a9) |
| 2 | `%125 = trunc %3 & 49151`・`%126 = ugt %125, 11`・`%138 = ugt %125, 18` → `45d432` | 45d38e `movzx eax,ax`・`and eax,0xffffbfff`・45d3fe `cmp eax,0x12`・45d401 `jg 45d432` | 同じ判定 (X = W & 0xBFFF) |
| 3 | `%143 = eq %125, 19` → `45d552` else `45d43d` | 45d432 `sub eax,0x13`・`je 45d552` | 同じ |
| 4 | `%144 = add %125,-20`・`%145 = eq %144, 0` → `45d565` (store 45d570) else `45d448` | 45d43d `sub eax,1`・45d440 `test`・45d442 `je 45d565` | 同じ (X == 20) |
| 5 | `%146 = eq %144, 1`・`%147 = eq %146, false` → `45d59a` else `45d576` (store 45d581) | 45d448 `sub eax,1`・45d44d `jne 45d59a`・45d453 `jmp 45d576` | 同じ (X == 21) |

- 結論の範囲: 「F3d 後 IR の store (45d565・45d576) は、W が `(W&0x4000)!=0 ∧ (W&0xBFFF)==20/21` のとき実行され、機械語も同じ条件で同じ store に進む」ことは一致した。
- 未照合 (results を更新しない理由): (a) 45d381 に入るまでに `eax` が W のまま保たれること (45d0b9 以降の `eax` 書換えの全経路を見ていない)。(b) 45d5ea の join の consumer (REPORT_2660 §10.2 の対応は既に確認済み。本節では再確認していない)。
- 45d0a0 の 45d381 までに `[arg1]` へ書く store は無い (機械語の store は `[rbp+0x28]`・`[rbp+0x50]`・`[rbp+0x38]` のみ。`grep` で確認)。

## 3. 45b1bf の P store と 2 段目 load の間 (IR `boot_final3.ll` の function_45b170)

| 行 | IR | 機械語 |
|---|---|---|
| 161565 | `%13 = load i64, ptr %12` (P = [arg2+8]) | 45b1b8 `mov rax,[rbx+8]` |
| 161566 | `store i64 %13, ptr %storemerge.in.in.in.reg2mem` (P の store) | (機械語に相当する store は無い: レジスタ経由) |
| 161567〜161571 | 無し (161570 は `load` の reload・161571 は inttoptr) | 45b1bc `mov rax,[rax]` |
| 161572 | `%storemerge.in = load i64, ptr %storemerge.in.in` (2 段目 = V = [P]) | 45b1bf `mov [rbp+0x38],rax` |

- P の store (161566) と 2 段目の load (161572) の間に **store は無い** (`awk` で確認)。受入条件 3 は IR 側で満たした。
- 未照合: dead edge `45b1a1→45b1b1` (REPORT_2660 §2) の上流 (45b18b の型タグ読みの F3d) と、45b1b8 に入る述語の機械語 jcc の対応。UNDETERMINED のまま。

## 4. 監査と再生成 (測定 commit `091e4a7b6` = origin/main。コード差分は無し)

- IR 再生成: `LDFIX_ARGS="--passes f1,f1v,f2,f3a,f3b,f3c,f3d,f4" bash tools/m11/m11_gen_ir2.sh` 51.2 s・rc 0。ldfix 内訳 F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=46 F3d=58 F4=10 (errors 0)。`ir_conditions.json`: `ldfix=applied`・`ld108=applied`・`ld115=applied`・`r8b=applied`・`ir_sha256=81c89797…`。
- 注: `m11_gen_ir2.sh` が書くのは `boot_final.ll`。監査の入力 `boot_final3.ll` は `m11_build.sh` の post 段で作られるため、同じ順 (alloca → guard699 → guard4fa210 → fix912 off → `--bind` → `m11_post.py`) を cc 無しで再現した。`xor i64 0, 0` 行は 3886 (旧) → 3828 で REPORT_2660 §10.1 と一致。
- 監査: `audit_lsf_ssa_e2e.sh` を前景で実行 (`M11_WORK`・`LD_WORK` 指定・`FL_WIN64_DIR` は `$RUNNER_TEMP/fl-win64`)。**rc=0・162 s (2 m 42 s)・loadavg 0.60 0.51 0.27 (開始時)**。ログ末尾: `[spill178_1161.tsv] results/ と一致`・`[spill178 (修復後 IR)] results/spill178_1161.tsv と一致`。監査スクリプトは 8 ステップ表記で、7 番目 (spill 分類) と 8 番目 (LD-143 修復後) がそれぞれ `cmp` 一致。
- spill 分類 (`results/spill178_1161.tsv`・現 results 版): 確定 150・判定不能 27・未判定 1 (REPORT_2660 §10.4 の 147/30/1 とは版が異なる。これは本 PR の範囲外で、再計算していない)。
- 鮮度: `git diff 091e4a7b6 HEAD -- tools/m11/ldfix/results tools/m11/ldfix/*.py` は 0 行 (コード差分無し)。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 45d570・45d581: 45d381 直前の `eax = W` の確認 (45d0b9 以降の `eax` 書換えの全経路) と、判定を OK_LOAD に上げるか | 4 site の判定が UNDETERMINED のまま | #3605 (Refs。次の run で確認) |
| 45f938: 0x4000 判定から 45f831 までの上流経路 (機械語 jcc と IR の `%118`・`%121`・`%122` の対応) | UNDETERMINED のまま | #3605 |
| 45b1bf: dead edge `45b1a1→45b1b1` の上流と、45b1b8 に入る述語の対応 | UNDETERMINED のまま | #3605 |
| 判定の results 更新 (根拠が立った判定だけ) | results は未更新。監査 7/7 は現 results と一致 | #3605 |
| spill 分類の版差 (REPORT_2660 §10.4 の 147/30/1 と現 results の 150/27/1) | 数値の版の注記のみ | LD-124 (#2689) |
