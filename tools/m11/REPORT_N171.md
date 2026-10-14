# M11 REPORT (#3134 / [M11-N171] / 親 #1154): set_other 非 imm 349 件の定義探索と 3 値分類

結論: 台帳の非 imm 349 件 (reg 123・mem 150・lea 76) を、機械語で代入元の定義を後ろ向きに探して分類した。**実値化 0 / 復元不能 0 / 未決 349 / 未分類 0**。定義を mov 連鎖・符号拡張・即値演算まで辿っても定数に決まった件は 0 だった (#1154 の REPORT_N86 §2 と同じ結果)。復元不能 0 は、呼出し越えで揮発族が壊れた件が非 imm に無かったため。未決 349 は接続先を 3 子 issue (#3140・#3141・#3142) に分けた (§3)。survey 退行の受入 (ok ≥ 870) は素材の欠落で測れず、未達 (§5・§6)。

## 1. 接続方式 (決めたこと)

- 対象: 台帳 (`m11_argrecover.py` の `site_detail[].src` が `imm` 以外) の各引数。レジスタ引数 (pos 0〜3) は rcx/rdx/r8/r9 の族、スタック引数 (pos ≥ 4) は `[rsp + 0x20 + 8*(pos-4)]` のスロット。
- 遡る範囲: call 直前から後ろ向きの直線区間。分岐先 (jump target) を越える時点で `merge`、ret/jmp で `branch`、関数入口で `entry`。jcc は値を変えないので越える。
- 定義の読み方:
  - 全幅 (32/64bit) の `mov r, imm`・`xor r, r`・同族の全幅コピー (`mov r, r`・`movss/movaps` の xmm コピー) は、元の定義まで連鎖をたどる。
  - `movzx`/`movsx`/`movsxd` (reg 源) と即値の `add`/`sub`/`and`/`or` は、旧値をたどって値を計算する (終端が定数なら実値化)。
  - 8/16bit の部分書込と、型幅より狭いスロット格納は、上位ビットが旧値依存なので未決。
- call の扱い: 揮発族 (rax/rcx/rdx/r8/r9/r10/r11/xmm0〜5) は call で壊れる。定義が無いまま call に当たった場合、rax・xmm0 は戻り値 (`call_ret`・未決)、その他は `call_clobber` (復元不能: Win64 ABI で call 後の値が保証されない)。引数領域 (スタック) も同じ扱い。
- 実値化の条件: 直線区間で全幅の定数に到達すること。IR の引数型幅は使わない (型幅が要る件は `stack_narrow` として未決に残した)。

## 2. 測定 (実測)

- 測定 commit: `69bab10e` (分類器 `tools/m11/m11_setother_nonimm_class.py` を追加した最後の commit)。
- 入力: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774ded8aaf717…`)・PE は `fl-win64` の `extracted/block00031_PE.bin`。
- 実行 (HEAD `69bab10e`・すべて rc 0):
  1. `m11_post.py` → 既定出力 sha `ecab191b13590dd0…` (REPORT_N86 §4 と一致)。
  2. `m11_argrecover.py` → 台帳 set_other 系 410・非 imm 349・imm 61。
  3. `m11_setother_ledger_verify.py` → `match 410`・exit 0 (台帳の kind 分類は不変)。
  4. `m11_setother_nonimm_class.py` → 下表。
  5. `m11_setother_imm_class.py` → `full_const 6 / partial_write 35 / stack_partial 9 / arith 11` (変化なし)。

| 台帳 kind | 終端の理由 | 件数 | 区分 |
|---|---|---|---|
| mem_global | load_global (`mov r, qword ptr [rip+d]`) | 11 | 未決 |
| mem_ptr | load_ptr (`mov rcx, qword ptr [rcx]` 等) | 89 | 未決 |
| mem_stack | load_stack (`mov rdx, qword ptr [rbp+d]` 等) | 50 | 未決 |
| lea_ptr | lea_ptr (`lea rcx, [rdi+0x10]`) | 17 | 未決 |
| lea_stack | lea_stack (`lea rcx, [rbp+0x48]`) | 59 | 未決 |
| reg | load_ptr | 28 | 未決 |
| reg | merge | 25 | 未決 |
| reg | merge_at_call (呼出し命令そのものが分岐先) | 8 | 未決 |
| reg | call_ret (直前の call の戻り値) | 19 | 未決 |
| reg | arith (`add edx, eax` 等・reg 右辺) | 7 | 未決 |
| reg | entry (関数入口) | 1 | 未決 |
| reg | chain>arith (ext・即値演算の連鎖の終端) | 9 | 未決 |
| reg | chain>call_ret | 6 | 未決 |
| reg | chain>merge | 1 | 未決 |
| reg | chain>load_ptr | 1 | 未決 |
| reg | chain>load_stack | 1 | 未決 |
| stack_set_other (reg) | stack_narrow (`mov byte ptr [rsp+0x20], al`・`movss dword ptr [rsp+0x20], xmm0`) | 17 | 未決 |
| **合計** | | **349** | **実値化 0 / 復元不能 0 / 未決 349 / 未分類 0** |

- `call_clobber` は 0 件。非 imm の定義は、call を越える前に必ず見つかった。
- 定数に決まった件は 0 件。`movzx/movsxd` 連鎖と即値演算を入れても 0 のため、定数の連鎖は非 imm 側には無い。

## 3. 未決 349 件の接続先 (IR 側で何を接続すれば決まるか)

| 理由 | 件数 | IR で接続すべきもの | 起票先 |
|---|---|---|---|
| merge・merge_at_call・chain>merge | 34 | CFG 到達定義 (分岐先の複数の定義) | #3140 ([M11-N172]) |
| call_ret・chain>call_ret・arith・chain>arith・stack_narrow | 58 | callee の return 定義 / 旧値 SSA 値との演算 / 引数型幅 (格納幅) | #3141 ([M11-N173]) |
| load_*・chain>load_*・lea_* | 256 | 読込元の store / alloca・引数ポインタ (メモリ SSA) | #3142 ([M11-N174]) |
| entry | 1 | 呼出元の def (inherit) | #1373 |

34 + 58 + 256 + 1 = 349。

## 4. 検算

- `m11_setother_ledger_verify.py` (別アルゴリズム・op_str 照合): 410/410 一致・exit 0。
- 本分類器の終端と台帳 src の対応 (§2 の表): mem_* → load_*、lea_* → lea_*、reg → (copy 連鎖の終端)、stack reg → stack_narrow。台帳 kind と矛盾する件は 0。
- 検算の独立性は限定的: 窓 (分岐・call で打ち切る範囲) と call 位置の対応は `m11_argrecover.py` の `AR.Fn` と共通 (REPORT_N86 §3 と同じ制約)。窓の誤りは検出できない。
- `m11_argrecover_verify.py`: 実値化 0 件のため照合対象なし (該当なし)。

## 5. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 非 imm 349 件を 実値化 / 復元不能 / 未決 の 3 値で件数実測・未分類 0 | **達成** | §2 (0 / 0 / 349 / 0 = 349)。接続で実値化できた件は無く、未決の接続は子 3 件へ移した |
| 2. `M11_SIGFIX_RECOVER=1` の `m11_e2e.sh` で survey ok ≥ 870 | **未達 (測れない)** | §6。素材に `functions_dll.csv` が無い。本分類器は IR と `fixes.json` を変えないので、既定経路の値は変わらない (コード差分 0 行は §7) |
| 3. 実値化した値を `m11_argrecover_verify.py` で一致 | **該当なし** | 実値化 0 件 |

## 6. survey が測れない理由 (実測)

- `M11_SIGFIX_RECOVER=1 FL_WIN64_DIR=<fl-win64 展開先> bash tools/m11/m11_e2e.sh` を `timeout 240` で 1 回実行。`work/lift_pe.sha256` が無いため全再生成モードに入り、`m11_bounds.py` が `tools/m2/work/ghidra_dll/functions_dll.csv` を読めず fail-closed で停止 (`FileNotFoundError`・`M11_SUMMARY {"reached_stage":0}`・rc 1・0.5 秒)。
- `functions_dll.csv` は Ghidra 中間物で素材に無い (REPORT_N86 §6・§9・REPORT_N112 §5 と同じ)。本 run では解消できない。
- 起票先: #1154 (既存の追跡先)。

## 7. 測定 commit と差分

- 測定 commit: `69bab10e` (コードを変えた最後の commit)。本 REPORT を含む commit は md のみ。
- `git diff 69bab10e HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (本 REPORT 以外に `tools/m11` のコード差分なし)。
- `m11_post.py`・`m11_argrecover.py`・`ldfix/ldmach.py`・既存の検算スクリプトは変更していない。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未決 34 件 (CFG 到達定義) | 0 詰め非 imm 引数の値が未保証 | #3140 ([M11-N172]) |
| 未決 58 件 (call_ret・算術・狭い格納) | 同上 | #3141 ([M11-N173]) |
| 未決 256 件 (メモリ読込・lea) | 同上 | #3142 ([M11-N174]) |
| 未決 1 件 (関数入口) | 同上 | #1373 ([M11-N87]) |
| survey (受入 2): `functions_dll.csv`・`lift_pe.sha256` の欠落 | survey 退行が未判定 | #1154 |
