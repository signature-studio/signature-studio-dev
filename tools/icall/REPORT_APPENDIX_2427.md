# 付録: icall #2427 (ICALL-77) — 脱落 frame slot store を IR に戻す pass と route への組込み

> 親: #2394 (ICALL-75)。残件: ICALL-78 (#2508)。
> 本付録の改訂: PR #2514 (merge 後の差し戻し) の指摘 (D24 の ID 衝突・sweep の再測定・census との定義の揃え・挿入点の基本ブロック保護) への対応。PR #2569 (その修正へのレビュー) の指摘 (無名 label の検出・D24 表記の取りこぼし・§3.2 の前 PR 表記) への対応。
> **既知類型との関係**: DEFECTS.md の D22 に近縁。REPORT_APPENDIX_2394 §6 の D24 候補 (脱落 store) の**修復側**を実装した。DEFECTS.md 本体への行追加は PM 判断 (`docs/WORKFLOW.md` §5)。

## 1. 結論

- pass `tools/icall/frame_slot_restore.py` を追加した。`fa_route_build.sh` に `FA_FRAME_SLOT=1` で組み込む (**既定 OFF**)。既定 OFF の理由: 本 pass は 181057b38 の IR だけを変え、closure の bit 一致数は動かないため、既定化は PM 判断とした。
- `function_181057b38`: 8 入力の結果が TRAP 8 → **TRAP 0** (例外なし。値は一致しない、§4)。BLK+0 (`0x36319008`) への "emsc" 書込み 8 → **0**。
- `fa_sweep.sh 8 60` (131 関数、同一 commit `08ec47c3` で base・fixed を各 2 回): 関数別の結果は各条件の 2 回で完全に一致 (131/131)。base と fixed の差は `0x181057b38` の **1 件** (`wasm_err` 8 → 0、`mismatch` 8 のまま)。他 130 関数は不変。
- 未達 (子 ICALL-78 #2508 へ移した): (a) `0x180da6e60` 候補 10 件の分類、(b) fixed IR でも残る 8/8 不一致の原因、(c) 元 `SlateCore.core_64` の bytes との照合 (`plugins-freshair` 素材が本 run に無い)。

## 2. 検出と復元 (`frame_slot_restore.py`)

- **検出** (`frame_slot_probe.py census` と同じ定義): 関数は rbp を frame pointer にする型 (`frame_slot_probe.frame_ops` の fp 判定) のみ対象。rbp 相対の 8B store `d` のうち、before IR (`before.0.drc.ll`) に同じ `insn.addr` の store が無く、lea で address を取られた slot `e` に対し `0 < d - e <= 0x40` を満たすもの (候補)。
- **値の解決**: 候補 store の source reg を、同一基本ブロック内で最後に書いた命令から解決する。`lea reg,[rbp+e]` なら frame slot の address、`lea reg,[rip+x]` なら global の VA。分岐先 (jump target) を跨ぐ場合と、call・ret・jcc を跨ぐ場合は未解決にして戻さない。
- **命名**: RetDec の `stack_var_X` は `X = disp - 8` (`[rbp+0x20]`→`stack_var_24`、`[rbp-8]`→`stack_var_-16`、`[rbp-0x20]`→`stack_var_-40` で確認)。
- **復元**: 戻す store の target slot `X` の alloca が無く、`X-8` が lea で取られた i64 alloca なら、両者を 1 つの `alloca i128` (16B) にまとめる (`X-8` が下位、`X` が上位)。そうでなければ `alloca i64` を足す。値の store は、`insn.addr` が元 VA より大きい最初の IR 命令の直前に挿入する。その直前までに基本ブロックの境界 (label・terminator) があるときは戻さず、`skipped` に `block boundary before insertion point` と記録する。label は名前付きと無名の 2 形式を検出する (§3.3)。
- **181057b38 での適用** (`work/fa_exp/frame_slot.json` の実測):
  - 候補 2 件: `0x181057b71` (`mov [rbp-8],rax`、値 = frame `-0x20`)、`0x181057b87` (`mov [rbp-0x20],rax`、値 = global `0x181306ce0`)。
  - merge 2 件: `[-24,-16]` と `[-48,-40]`。`-40` は `-48` (lea 済み、機械語上 `[rbp-0x28]` と `[rbp-0x20]` は隣接) に隣接するため、規則どおり merge した。REPORT_APPENDIX_2394 §4 の手作業実験では `-40` を単独 alloca にしていた。この違いによる結果の差は、8 入力 (TRAP 0・emsc 0) と sweep (他 130 関数不変) では出なかった。
- **180da6e60**: 候補 10 件 (`mov [rbp-0x29],rcx` 等) は全て `value: null` (局所の lea で値が出ない)。戻していない。この関数は native crash/timeout のため sweep でも比較できない。分類は ICALL-78 (#2508)。
- **census との一致**: F 131 関数の候補は 12 件 / 2 関数 (`181057b38` 2 件・`180da6e60` 10 件)。REPORT_APPENDIX_2394 §5 と一致。`frame_slot_restore.py` は census と同じ fp 判定を通すよう揃えた (`08ec47c3`)。両者の候補 `(関数 VA, store VA)` の集合は 12 件で一致 (差 0 件、§3.3)。

## 3. 実測 (測定 commit `08ec47c3`)

測定 commit は、コードを変えた最後の commit (`08ec47c3 fix(icall): align frame slot restore with census and skip cross-block insertions (ICALL-77 #2427)`)。本付録の commit は docs のみ。測定は `08ec47c3` の内容を worktree (`ws-2427`) で展開して行った。素材は `work-icall` (`rt_freshair-core`・`rw.dll`) と `toolchain-emsdk`。`FA_CORE=rw.dll`。`plugins-freshair` は不使用。base は `FA_FRAME_SLOT` 未設定、fixed は `FA_FRAME_SLOT=1`。route は各条件で `fa_route_build.sh` を実行し、sweep の前に build し直した。

### 3.1 8 入力 (`fa_wc_drv.cjs <fa_wc.cjs> 181057b38`)

| 条件 | 8 入力の結果 | WC 行 | BLK+0 (`0x36319008`) への "emsc" |
|---|---|---|---|
| base (`FA_FRAME_SLOT` 未設定) | TRAP 8 | 168 | 8 |
| fixed (`FA_FRAME_SLOT=1`) | OK 8 | 168 | 0 |

`fa_wc_drv.cjs` は OK/TRAP と書き込み行だけを出すので、8 入力の値は本 run では取っていない。値は fa_sweep の先頭 2 入力 (§3.2) で見ている。

### 3.2 fa_sweep (`fa_sweep.sh 8 60`、131 関数、各条件 2 回)

| 条件 | run | bit 一致 | native crash/timeout | wasm のみ err | 値の不一致 | 所要 (wall) | load (1 分) 実行前→後 |
|---|---|---|---|---|---|---|---|
| base | 1 | 47 | 66 | 9 | 9 | 15:04:46 → 15:05:56 (70 s) | 0.22 → 0.84 |
| base | 2 | 47 | 66 | 9 | 9 | 15:05:56 → 15:07:05 (69 s) | 0.84 → 1.29 |
| fixed | 1 | 47 | 66 | 8 | 10 | 15:07:18 → 15:08:28 (70 s) | 1.17 → 1.05 |
| fixed | 2 | 47 | 66 | 8 | 10 | 15:08:28 → 15:09:38 (70 s) | 1.05 → 1.01 |

- 逐次実行 (1 並列)。load は `/proc/loadavg` の 1 分平均 (実行前 → 後)。各 run の結果 (1 行 1 関数の `sweep.jsonl`) は `tools/icall/work/fa_route/sweep_{base,fixed}_{1,2}.jsonl` (gitignore 対象)。
- **関数別の安定性**: base の run 1 と run 2 は 131 関数すべて同じ (差分 0 件)。fixed の run 1 と run 2 も同じ (差分 0 件)。load が 0.2 〜 1.3 の範囲で動いても native crash/timeout の分類は変わらなかった。
- **base と fixed の関数別の差分は 1 件**: `0x181057b38`。他 130 関数は 4 run すべてで同一。

| 関数 | 条件 | run 1 (n / match / mismatch / wasm_err / native_err) | run 2 |
|---|---|---|---|
| `0x181057b38` | base | 8 / 0 / 8 / 8 / 0 (wasm のみ err) | 8 / 0 / 8 / 8 / 0 (wasm のみ err) |
| `0x181057b38` | fixed | 8 / 0 / 8 / 0 / 0 (値の不一致) | 8 / 0 / 8 / 0 / 0 (値の不一致) |

- 旧測定 (前 PR #2514 の単発・測定 commit `111c1411`: base 46/66/9/10、fixed 46/66/8/11) との差は、同じ 1 関数の揺れ (match と mismatch の間) と推定する。旧測定の関数別の出力は残っていないため、どの関数かは特定していない。本測定 4 run では再現しなかった。揺れの追跡は #2302 (既存)。

### 3.3 検証の補足

- **census と restore の候補の一致**: `frame_slot_probe.py census` の候補 `(関数 VA, store VA)` 12 件と、`frame_slot_restore.py` の候補 12 件は集合として一致 (差 0 件)。
- **修正の影響の範囲**: 修正前 (`d471439e` = main の script) と修正後 (`08ec47c3`) の `frame_slot.ll` と `frame_slot.json` は `cmp` で一致 (F 131 関数、入力 `after.0.restored.ll`)。修正は F 131 の出力を変えていない。
- **label の形式** (PR #2569 の指摘で追加): 実 IR の基本ブロック label は、列 0 から始まる次の 2 形式だけ。
  - 名前付き: `dec_label_pc_1803b3d10:` (判定 `^[A-Za-z0-9_.$-]+:`)
  - 無名: `; <label>:13:                 ; preds = %dec_label_pc_182319180` (判定 `^;\s*<label>:`。LLVM が名前の無い基本ブロックに付ける形式)
  - 件数: `before.0.drc.ll` は名前付き 1014・無名 19、`after.0.restored.ll` は名前付き 1092・無名 30。列 0 で `:` を含む行のうち、この 2 形式のどちらにも当たらないものは 0 件。
  - 修正前 (`08ec47c3`) の判定は名前付きだけを検出し、無名 label を見落としていた。修正後 (`a35e0259`) は両方を検出する。
- **修正後の F 131 の出力** (`a35e0259`): `frame_slot.ll`・`frame_slot.json` は修正前と `cmp` で一致 (F 131 に、挿入点の直前に label がある関数は無い)。sweep の入力 IR は変わらない。
- **基本ブロック保護の検証**: 挿入点は `function_181057b38` の `0x181057b87` (元 VA より大きい最初の非 alloca 命令 `  %10 = add i64 %0, 40, !insn.addr !6588`。直前は `!insn.addr !6587` の store)。その直前に label を 1 行入れた IR で `frame_slot_restore.py` を実行した。注入 IR は `tools/icall/work/fs_new/` (gitignore 対象)。F 131 の入力 (`after.0.restored.ll`) は変えていない。

| 注入した 1 行 | 修正前 (`08ec47c3`) | 修正後 (`a35e0259`) |
|---|---|---|
| 無名 `; <label>:99:` (`label_unnamed.ll`) | restored 2 件 (`0x181057b71`・`0x181057b87`)。`0x181057b87` は skip されず戻る (見落とし) | restored 1 件 (`0x181057b71`)。`0x181057b87` は `block boundary before insertion point` で skip |
| 名前付き `blk_test_99:` (`label_named.ll`) | restored 1 件 (`0x181057b71`)。`0x181057b87` は `block boundary before insertion point` で skip | 同じ (変化なし) |
- **負の対照**: 本 run では再実行していない。REPORT_APPENDIX_2394 §4 の `frame_slot_probe.py restore --separate` (store は戻し alloca を分けたまま) は TRAP 8・emsc 8 のまま。本 pass の結果 (TRAP 0) との差は、alloca の結合 (16B 化) による。

### 3.4 測定 commit からの差分

- 測定 commit 以降にコードを変えた commit は `a35e0259` (`frame_slot_restore.py` の label 判定 1 行)。`git diff 08ec47c3 HEAD -- tools/icall/*.py tools/icall/*.sh tools/icall/diff tools/icall/rt` の出力:

```diff
diff --git a/tools/icall/frame_slot_restore.py b/tools/icall/frame_slot_restore.py
index c96bf0c7..fa230292 100644
--- a/tools/icall/frame_slot_restore.py
+++ b/tools/icall/frame_slot_restore.py
@@ -152,7 +152,7 @@ def edit(fn, restores, escaped, md, gl_text):
     def same_block(p):
         for j in range(p - 1, -1, -1):
             l = lines[j]
-            if re.match(r'^[A-Za-z0-9_.$-]+:', l) or re.match(r'^\s+(br|switch|ret|unreachable|indirectbr)\b', l):
+            if re.match(r'^(?:[A-Za-z0-9_.$-]+:|;\s*<label>:)', l) or re.match(r'^\s+(br|switch|ret|unreachable|indirectbr)\b', l):
                 return False
             if '!insn.addr' in l and 'alloca' not in l:
                 return True
```

- 判定: 差分は label 判定の 1 行だけで、F 131 の `frame_slot.ll`・`frame_slot.json` は修正前と `cmp` 一致 (§3.3)。route の入力は `frame_slot.ll` だけなので、route の入力 IR は変わらない。レビュー (PR #2569) の判断どおり fa_sweep は再測定していない。§3.1・§3.2 の測定値は、同じ入力 IR に対する値として `a35e0259` でも有効。

## 4. 残件 (ICALL-78 #2508 へ移した)

- **fixed IR でも 8/8 不一致**: sweep の先頭 2 入力で wasm の結果は `0x0000000000000000` (REPORT_APPENDIX_2394 §4 でも wasm の xmm0 は 0 と記載)。native の値とは一致しない。harness 由来か lift 由来かは未切り分け。TRAP だけは消えた。
- **180da6e60 候補 10 件**: 値が局所で解決できず分類していない。`[rbp-0x29]` の store が `lea rdx,[rbp-0x31]` → `call r10` の先で読まれるかの確認が必要。
- **SlateCore.core_64 の bytes 照合**: 元ファイルは本 run に無い (`plugins-freshair` を `oc_artifacts` に指定していない)。REPORT_APPENDIX_2394 §2 の「rw.dll の同 VA と 205 B 一致」は元 PE の decode 結果との比較で、元ファイル本体の sha256 との照合は未実施。

## 5. 範囲と限界

- 検証範囲: `181057b38` (8 入力と fa_sweep 131 関数の 2 回ずつ)、`FA_FRAME_SLOT=1` の route・wc の build、検出件数 (F 131 関数)、挿入点の保護 (無名・名前付きの label 注入 各 1 件、§3.3)。
- 基本ブロック保護の限界: label と terminator の有無だけを見る。label は実 IR に現れる 2 形式 (§3.3) だけを見る。分岐先ごとの実行経路の意味 (store が条件付きで実行されるか) までは検証していない。保護で戻さなかった store は IR に入らないため、その関数は従来どおり脱落したまま残る。
- 範囲外: 180da6e60 の wasm 実行 (native crash/timeout)、元 `SlateCore.core_64` との照合、8/8 不一致の原因、RDA 段が store を消す条件 (REPORT_APPENDIX_2394 §8)、他 PE (FLEngine 等) への適用。
- merge 規則 (`X-8` が lea で取られた i64 なら 16B にまとめる) は 181057b38 の 2 件で確認したのみ。一般化の妥当性は他関数で未確認。

## 6. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .                      # tools/icall/work/ へ
bash tools/ott/native/build.sh                                               # fa_sweep に必要 (libottnative.so)
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"
env -u FA_FRAME_SLOT bash tools/icall/fa_route_build.sh                      # base
bash tools/icall/diff/fa_wc_build.sh && node tools/icall/diff/fa_wc_drv.cjs "$PWD/tools/icall/work/fa_wc/fa_wc.cjs" 181057b38
bash tools/icall/diff/fa_sweep.sh 8 60                                       # 131 関数 (70 秒。2 回実行する)
FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh                           # fixed (既定 OFF を env で ON)
bash tools/icall/diff/fa_wc_build.sh && node tools/icall/diff/fa_wc_drv.cjs "$PWD/tools/icall/work/fa_wc/fa_wc.cjs" 181057b38
bash tools/icall/diff/fa_sweep.sh 8 60                                       # 131 関数 (2 回実行する)
```

注: `fa_cmp.py` の native 参照は `FA_CORE` を読む。環境変数が無いと既定パス (`tools/targets/freshair/...`) を開き、全関数が `crash_or_timeout` になる。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x181057b38` fixed 後も 8/8 不一致 (wasm の xmm0 戻り値 0) の原因 | TRAP は消えたが bit 一致は 0/8 | ICALL-78 (#2508) |
| `0x180da6e60` 候補 10 件の miscompile か無害かの分類 | closure 全体の判定は native crash/timeout のため比較不能 | ICALL-78 (#2508) |
| 元 `SlateCore.core_64` の bytes と `rw.dll` の同 VA の sha256 照合 | (a) の根拠は PE decode 結果の比較のみ | ICALL-78 (#2508) (`plugins-freshair` 必要) |
| `FA_FRAME_SLOT` の既定 ON 化 | 既定 OFF のため closure の route は従来どおり | PM 判断 (本 PR では既定 OFF) |
| `docs/DEFECTS.md` への D24 行の追加 | 横断正本への反映 | PM 判断 (`docs/WORKFLOW.md` §5) |
| fa_sweep の ±1 の揺れ (旧単発の 46/66/9/10 と本測定の 47/66/9/9) | 数値の正本の取り方 | #2302 (既存) |

## 8. 測定 commit と差分

- 測定 commit: `08ec47c3` (sweep を測った commit)。以降にコードを変えた commit: `a35e0259` (`frame_slot_restore.py` の label 判定 1 行)。
- `git diff --name-only 08ec47c3 HEAD -- tools/icall/*.py tools/icall/*.sh tools/icall/diff tools/icall/rt` の出力: `tools/icall/frame_slot_restore.py` の 1 件 (差分の中身は §3.4)。
- 本付録の docs の commit は md のみ。
