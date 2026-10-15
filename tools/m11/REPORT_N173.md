# M11 REPORT (#3141 / [M11-N173] / 親 #3134): set_other 非 imm のうち呼出し戻り値・算術・狭い格納 58 件の接続判定

既知類型との関係: 該当なし (DEFECTS.md の D21 = 呼出し引数の出元の機械語↔IR 突合 と近縁だが、本 PR は分類のみで IR を変えず、D21 の修復 `m11_fix912.py` に触れない)。

結論: REPORT_N171 §3 の 58 件 (call_ret 19 + chain>call_ret 6 + arith 7 + chain>arith 9 + stack_narrow 17) を、
戻り値の機械語解析・算術の両辺評価・IR 型幅ゲートで判定し直した。測定 commit `7e5261ce4` の実測は
**実値化 0 / 復元不能 0 / 未決 58 / 未分類 0**。判定方法は 3 つとも入れて動作を確認した (§5 の正の対照 7/7・ネガ対照 3/3)。
実 PE の 58 件では定数に決まる件が無かった。主な原因は、callee の ret 直前が分岐先の合流点になり追跡を止める件 (202 callee 中 98) である。
型幅ゲート (stack_narrow) は 17 件中 8 件が一致 (格納元を辿ったが未決)、9 件が不一致 (上位ビットは旧スロット値に依存して未決)。

## 1. 判定方式 (REPORT_N171 §1 からの追加・変更)

- **呼出し戻り値 (call_ret)**: 直前の call の戻り値 (rax / xmm0) は、直接 call なら callee の全 `ret` 直前の rax/xmm0 を
  同じ後ろ向き追跡で求める (`ret_value`)。全経路が同じ定数なら実値化 (`ret_const`)、経路で値が違えば未決 (`ret_multi`)。
  間接 call (`call qword ptr [...]`) は callee 不明で未決 (`call_ret_indirect`)。入れ子は 3 段まで (`ret_depth`)・
  循環は `ret_cycle`。callee の中の復元不能 (揮発族の call 越し) は `ret>call_clobber` として復元不能に伝える。
- **算術 (arith)**: reg 右辺の add/sub/and/or/xor (同じ幅) は、旧値 (dst) と右辺 (src) を両方後ろ向きに追跡し、両方が定数なら計算する。
  どちらかが復元不能なら復元不能、それ以外は未決 `arith[dst:<why>|src:<why>]` (定数側は `const`)。
  即値の xor と、即値のシフト (shl/shr/sar) を追加した (chain>arith の終端になるため)。
- **狭い格納 (stack_narrow・型幅ゲート)**: 格納幅 S < 64 (byte/word/dword) の `[rsp+0x20+8*(pos-4)]` 書込は、
  callee の IR 仮引数型幅 W と S が**一致する時だけ**格納元 (reg・xmm・即値) を辿る (`stack_match>X`)。
  不一致は未決 `stack_narrow_ir<W>_st<S>` (上位 64-S ビットは旧スロット値に依存する)。
  格納幅が SIZE に無い (xmmword 等) は狭い格納に入れず、未決 `stack_width_other` (測定 commit `7e5261ce4` で追加。それ以前は st0 と出ていた)。
  **型幅の出所**: 入力 IR `work/boot_final.ll` の callee の `define` 行の仮引数 (pos 番目 = IR の index pos)。
  `work/sigfix_stats/final3_base.ll` (m11_post 出力) の同じ 8 callee の define 行と一致することを確認した (§4)。
  `--ir` で指定し、既定は `work/boot_final.ll`。
- 変更していない: 台帳 (`fixes.json`)・IR・実値化の判定が既存の 33 件 (`m11_argrecover.py` の set_const)。

## 2. 測定 (再現手順と数値)

- 入力: `work-m11` を展開 (`tools/m11/work/`・gitignore)。PE は `fl-win64` の `extracted/block00031_PE.bin`
  (`$RUNNER_TEMP/fl-win64` に展開)。
- 再現 (測定 commit `7e5261ce4`。本 run で手順 1〜5 を全件再実行し、下表・下記の数値と一致した。素材の sha: `boot_final.ll` `69c774de…`・`block00031_PE.bin` `b2c64da4…`):
  1. `python3 m11_post.py work/boot_final.ll work/sigfix_stats/final3_base.ll --pads work/sigfix_stats/pads.json` → 出力 sha `ecab191b13590dd0…` (REPORT_N86 §4・REPORT_N171 §2 と一致)。
  2. `python3 m11_argrecover.py work/sigfix_stats/pads.json --pe $PE --out work/sigfix_stats/fixes.json` → 台帳 非 imm 349 (reg 123・mem 150・lea 76)・imm 61 (REPORT_N171 §2 と一致)。
  3. `python3 m11_argrecover_verify.py work/sigfix_stats/fixes.json --pe $PE` → `match 33 / mismatch 0`・rc 0 (set_const の既存 33 件は不変)。
  4. `python3 m11_setother_nonimm_class.py work/sigfix_stats/fixes.json --pe $PE --ir work/boot_final.ll` →
     `実値化 0 / 復元不能 0 / 未決 349`。非 imm 349 件の全体でも未分類 0。
  5. (追加の一括再現) `python3 m11_setother_repro.py work/sigfix_stats/fixes.json --pe $PE` → 下の突合 (基準との行単位)・対象外 291 件の理由差分・§4 の分布を 1 度に出す。
- 58 件 (REPORT_N171 §3 の対象) の判定 (測定 commit の出力を、基準の分類器 (`68eb512cd`) と行単位で突き合わせた。突合は手順 5 の `m11_setother_repro.py` が行う。下表は測定 commit `7e5261ce4` の実測):

| REPORT_N171 の理由 | 件数 | 新しい判定 (HEAD) | 区分 |
|---|---|---|---|
| call_ret (直接 call の戻り値) | 19 | `call_ret>ret>partial_copy` 8・`call_ret_indirect` 4・`call_ret>ret>other:cvtsd2si` 3・`call_ret>ret>load_stack` 2・`call_ret>ret>chain>load_ptr` 1・`call_ret>ret>arith[…]` 1 | 未決 19 |
| chain>call_ret | 6 | `chain>call_ret>ret>other:cvtsd2si` 6 | 未決 6 |
| arith (reg 右辺) | 7 | `arith[dst:load_stack\|src:merge]` 2・`arith[dst:arith[dst:load_ptr\|src:load_stack]\|src:arith]` 2・`arith[dst:arith[dst:arith[…]\|src:load_stack]…]` 2・`arith[dst:arith[dst:chain>call_ret>ret>merge\|…]…]` 1 | 未決 7 |
| chain>arith | 9 | `chain>arith[dst:const\|src:merge]` 4・`chain>arith[dst:load_stack\|src:merge]` 4・`chain>load_ptr` 1 | 未決 9 |
| stack_narrow (狭い格納) | 17 | `stack_match>load_global` 3・`stack_match>load_ptr` 2・`stack_match>merge` 3・`stack_narrow_ir64_st8` 7・`stack_narrow_ir64_st32` 2 | 未決 17 |
| **合計** | **58** | | **実値化 0 / 復元不能 0 / 未決 58 / 未分類 0** |

  注: `chain>arith[dst:const|src:merge]` の `const` は、旧値 (dst) が定数に決まり、右辺 (src) だけが合流で止まった件。
  右辺が定数に決まれば実値化の候補になる件 (4 件・推定)。
- 対象外 291 件 (349 − 58): 理由語が 1 件も変わらなかった (`reason` の差分 0 件)。分類器の変更の影響は対象 58 件に閉じる。

## 3. 狭い格納 17 件の型幅判定 (型幅の出所つき)

IR 型は `work/boot_final.ll` の callee の define 行 (仮引数 pos 番目)。格納命令は台帳 kind `stack_set_other` の定義位置の命令。

| caller | callee | k | pos | IR 型 | 格納命令 (定義位置) | 判定 |
|---|---|---|---|---|---|---|
| function_12fb5b0 | function_6ee750 | 0 | 4 | i64 | `mov byte ptr [rsp + 0x20], al` | 不一致 (st8) |
| function_cba190 | function_6ee750 | 0 | 4 | i64 | `mov byte ptr [rsp + 0x20], al` | 不一致 (st8) |
| function_cc7130 | function_6ee750 | 0 | 4 | i64 | `mov byte ptr [rsp + 0x20], al` | 不一致 (st8) |
| function_cc7dd0 | function_6ee750 | 0 | 4 | i64 | `mov byte ptr [rsp + 0x20], al` | 不一致 (st8) |
| function_e7d8e0 | function_6ee750 | 0・1 | 4 | i64 | `mov byte ptr [rsp + 0x20], al` (×2) | 不一致 (st8) |
| function_de10c0 | function_773990 | 0 | 9 | i64 | `mov byte ptr [rsp + 0x48], bl` | 不一致 (st8) |
| function_dd5680 | function_6be960 | 0 | 4 | i64 | `mov dword ptr [rsp + 0x20], eax` | 不一致 (st32) |
| function_de10c0 | function_775da0 | 0 | 4 | i64 | `mov dword ptr [rsp + 0x20], eax` | 不一致 (st32) |
| function_a97780 | function_677fb0 | 0 | 4 | i32 | `movss dword ptr [rsp + 0x20], xmm0` | 一致 → `stack_match>load_global` |
| function_ff0d70 | function_699ca0 | 0・1 | 4 | i32 | `movss dword ptr [rsp + 0x20], xmm0` (×2) | 一致 → `stack_match>load_global` |
| function_e9d8a0 | function_de1da0 | 0 | 4 | i32 | `movss dword ptr [rsp + 0x20], xmm6` | 一致 → `stack_match>merge` |
| function_e9d8a0 | function_de1da0 | 0 | 5 | i32 | `movss dword ptr [rsp + 0x28], xmm0` | 一致 → `stack_match>load_ptr` |
| function_e9d8a0 | function_de1da0 | 0 | 6 | i32 | `movss dword ptr [rsp + 0x30], xmm0` | 一致 → `stack_match>load_ptr` |
| function_e9d8a0 | function_de2280 | 0 | 6 | i32 | `mov dword ptr [rsp + 0x30], r13d` | 一致 → `stack_match>merge` |
| function_e9d8a0 | function_de2280 | 0 | 7 | i32 | `movss dword ptr [rsp + 0x38], xmm7` | 一致 → `stack_match>merge` |

- 型幅の出所 (検算): `work/boot_final.ll` と `work/sigfix_stats/final3_base.ll` の上記 8 callee の define 行の仮引数型は全件一致 (確認コマンドは §5)。
- 一致 8 件の格納元の終端: `movss xmm0, dword ptr [rip+…]` (定数プールらしき読込み・3 件)・`[rax+…]` の読込み (2 件)・合流 (3 件)。
  rip 相対の読込みは、読取専用データ (.rdata) なら値が決まるが、本分類器は値を読まない (未決 `load_global`)。
- 不一致 9 件: 格納幅 8/32 と IR 幅 64。上位ビットは旧スロット値なので、定数に決める根拠が無い (未決)。

## 4. 戻り値解析の観測 (直接 call の callee 202 件)

全 matched 台帳の直接 call の callee 202 件に `ret_value` を適用した (測定 commit `7e5261ce4`。`m11_setother_repro.py` の §4 出力を下表に合算した):

| ret_value の終端 | 件数 | 意味 |
|---|---|---|
| merge | 98 | ret 直前が分岐先 (合流点)。追跡は直線区間で止める (保守的) |
| merge_at_call | 30 | 合流点が call 直後 |
| load_stack | 22 | 戻り値がスタックの読込み |
| call_ret_indirect | 12 | 戻り値が間接 call の結果 (callee 不明) |
| entry | 11 | 戻り値が関数入口の rax/xmm0 (呼出し元の値を通す) |
| ret_nodisasm | 6 | 機械語が取れない (pdata 外) |
| load_ptr | 6 | ポインタ経由の読込み |
| load_global | 4 | rip 相対の読込み |
| ret_depth | 3 | 入れ子 3 段の上限 |
| other:setne / other:sete | 2 / 1 | 条件設定 (flags 依存) |
| lea_ptr 1・arith_load 1・partial_copy 1・other:cvtsd2si 1・arith[…] 2 | 6 | (内訳の件数) |
| ret_noret | 1 | ret が無い (tail jmp) |
| **定数に決まった callee** | **0** | |

合計 202。`ret_multi` (経路で値が違う) と `ret_cycle` は 0 件。
表の合算の規則: `m11_setother_repro.py` の出力の各行は先頭の `ret>` を 1 つ外した形。表は、そこから `call_ret>ret>`・`call_ret>`・`chain>` の接頭辞を外した終端で合算した (例: merge 98 = `merge` 65 + `call_ret>ret>merge` 26 + `call_ret>ret>call_ret>ret>merge` 7)。合算の前の出力行は 28 種、合計は 202。

## 5. 検算・ネガティブコントロール・正の対照

- **対照検査 (素材不要・測定 commit `7e5261ce4` で実行済み)**: `python3 m11_setother_controls.py` (終了コード 0)。機械語は手で符号化し、期待値は手計算 (分類器の出力とは独立)。
  - **正の対照 7/7**: `mov eax,5; ret`→5、`xor eax,eax; ret`→0、`mov eax,5; mov ecx,3; add eax,ecx; ret`→8、`mov eax,5; shl eax,4; ret`→80、
    `mov eax,5; add eax,-1; ret`→4、`mov eax,5; xor eax,15; ret`→10、`call B (mov eax,9; ret); ret`→9。いずれも `ret_value` の出力は `実値化 ret_const`。
    実 PE で定数が 0 件なのは判定器の見落としではなく、§4 の合流点での停止が主因。
  - **ネガ対照 3/3 (型幅ゲート 2 件・格納幅 SIZE 外 1 件)**: 呼出元は `mov al,[rip+…]; mov [rsp+0x20],al; call`。台帳 1 行 (pos 4) を main 経路で判定し、callee の IR define 行の型だけを変える (ファイルは読まず、スクリプト内で define 行を作る)。
    `i64` (IR 幅 64 ≠ 格納幅 8) → `stack_narrow_ir64_st8`、`i8` (一致) → `stack_match>load_global`。ゲートが判定を動かすことを確認した。
    3 件目: 呼出元 `movups xmmword ptr [rsp+0x20], xmm0; call` → `stack_width_other`。修正前の分類器では `stack_narrow_ir64_st0` になりこの対照が NG になることを確認してから修正した (commit `7e5261ce4`)。
  - **既知の限界 M1**: `jmp rcx; mov eax,7; ret` → `実値化 ret_const 7` (偽の定数になりうる。§8)。
- **M2 (理由語)**: ret 自身が合流先のとき (`k == s`) は理由語が `ret>merge_at_call` になる。合流先は ret の直前ではなく ret 自身なので、`merge` が正確。区分 (未決) は変わらない。改名は分類器の変更で再測定を伴うため §8 で扱う。
- **型幅の出所の確認 (§3)**: 次の 1 行は、8 callee の define 行が 2 つの IR で一致するかを見る (`work/` は手順 1 の入力と出力。本 run で実行し `一致`)。
  `m11_post` は関数の define 行に `weak` を付けるため、両側から `define (weak )?` を外してから diff する (外さないと 8 行の差になり `一致` が出ない)。
  `diff <(grep -E '^define[^@]*@function_(6ee750|773990|6be960|775da0|677fb0|699ca0|de1da0|de2280)\(' work/boot_final.ll | sed -E 's/^define (weak )?//') <(grep -E '^define[^@]*@function_(6ee750|773990|6be960|775da0|677fb0|699ca0|de1da0|de2280)\(' work/sigfix_stats/final3_base.ll | sed -E 's/^define (weak )?//') && echo 一致`
- **独立検算 (別アルゴリズム)**: `m11_argrecover_verify.py` は op_str の文字列だけで set_const の 33 件を照合 (`match 33 / mismatch 0`)。
  新しい判定で実値化が 0 件のため、この照合の対象は増えない (受入 3 は「該当なし」)。
- **型幅の出所の検算**: §3 の 8 callee の define 行を `boot_final.ll` と `final3_base.ll` で比較 (本 run で全件一致。上の sed 付きの diff)。
- **既存の変更の影響**: 対象外 291 件の理由が変わらないこと (§2)。

## 6. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 58 件を 実値化 / 復元不能 / 未決 の 3 値で件数実測し未分類 0 | **達成** (測定 commit `7e5261ce4`) | §2 の表: 実値化 0・復元不能 0・未決 58・未分類 0 |
| 2. 型幅による判定 (stack_narrow) の IR 引数型の出所を REPORT に書く | **達成** | §1・§3。出所は `work/boot_final.ll` の callee の define 行 (仮引数の index = pos)。`final3_base.ll` と 8 件一致 |
| 3. 実値化した値は `m11_argrecover_verify.py` で一致 | **該当なし** | 実値化 0 件。既存 set_const の照合は 33/33 一致のまま |

## 7. 測定 commit と差分

- 測定 commit: `7e5261ce4` (分類器の最後の変更。この commit の分類器・対照検査で §2〜§5 の数値を測った)。以後のこの REPORT の commit は md のみ。
- 分類器 (`m11_setother_nonimm_class.py`) の変更の履歴: `0ed00d057` (58 件の判定を追加) → `7e5261ce4` (格納幅 SIZE 外を `stack_width_other` に分ける。実 PE の 349 件では理由が変わらない: 修正前の区分表に st0 は無く、修正後の `stack_width_other` は 0 件)。
- 実 PE の測定 commit: `7e5261ce4` (§2〜§4 の数値)。その後の分類器の変更は `257c3dd51` (rip 相対) と `fa7cd079d` (`movzx`/`movsx` の部分レジスタ書込みを未決 `partial_ext` に戻す・review 指摘の修正) の 2 件。
- `fa7cd079d` の実 PE 再測定は**未実施** (`work-m11` の素材が本 run の `$ARTIFACTS_DIR` に無く、`boot_final.ll`・`final3_base.ll` を用意できない)。§2〜§4 の数値は `7e5261ce4` の実測のままで、`fa7cd079d` の下での値は未確認。
- 素材 (`work-m11`) が揃えば `m11_setother_controls.py`・`m11_setother_repro.py`・`m11_argrecover_verify.py` を再実行して、測定 commit を更新する (#4015 の未解決に含める)。
- 対照検査 `m11_setother_controls.py` と再現 `m11_setother_repro.py` は `4a35c7868` で追加し、`7e5261ce4` で対照 1 件を足した。
- main の取り込み (merge `26ccd7658`) で `m11_argrecover.py`・`ldfix/` など他の m11 ファイルが変わったため、その取り込み後の tree で §2 の手順 1〜5 を再実行した (数値は取り込み前と同じ)。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 戻り値の合流点 (ret 直前の分岐先) で止まる (202 callee 中 98)。合流先の CFG 到達定義が要る | 呼出し戻り値 25 件は定数に決まらない | #3140 ([M11-N172]) |
| rip 相対の読込みの参照先は実 PE で `.text` 11・`.data` 3 件で、`.rdata` は 0 件 (§9)。値を読む経路は入れたが実 PE では効かない | 型幅一致の 3 件 (`stack_match>load_global`) は決まらない | #4015 ([M11-N206]) |
| 算術 16 件の旧値・右辺 (load_stack・load_ptr・合流) の SSA 接続。IR への接続方式は未決定 (本 PR では決めていない) | 算術 16 件が未決のまま | #4015 ([M11-N206]) |
| 間接 call の戻り値 (202 callee 中 12 件・本 58 件中 4 件) | 呼出し戻り値が未決 | #4015 ([M11-N206]) |
| survey (受入 ok ≥ 870): `functions_dll.csv`・`lift_pe.sha256` の素材欠落で未測定 | survey 退行は未判定 | #1154 |
| 実値化した件の IR への接続 (判定を IR の引数値へ反映する処理) は未実装。本 PR は分類のみ | 0 詰めの非 imm 引数は未保証のまま | #4015 ([M11-N206]) |
| M1: 間接 jmp (jump table) の先の ret を、直前の定数の続きとして扱う (`jmp rcx; mov eax,7; ret` → 実値化 7 を対照で確認) | 本 PR の実測は実値化 0 件で数値は変わらない。IR へ接続する段階で偽の定数になりうる | #3140 ([M11-N172]。分類器の変更は再測定と併せて行う) |
| M2: ret 自身が合流先のとき理由語が `ret>merge_at_call` (正しくは `merge`) | 理由語の読み違い (区分は未決のまま変わらない) | #3140 (同上) |

## 9. rip 相対の読込み (#4015 / M11-N206 の 1 種目)

- 分類器: `[rip+…]` の読込みは、参照先が書込み不可・非実行の section (.rdata 相当) で幅 8/16/32 の全幅を読めたときだけ値を読む (`rdata_const`)。`.text`・`.data`・`.bss` と読めない場合は、理由語 `load_global` のまま未決 (理由語は変えていない)。
- 対照検査 (素材不要): rip 相対 3/3 (`.rdata` の値 42 → 実値化 / `.data`・`.text` → 未決)。正の対照 7/7・ネガ対照 3/3 は不変。
- 実 PE の判定: 非 imm 349 件は 実値化 0 / 未決 349 のまま。rip 相対の読込み 14 件 (`load_global` 11・`stack_match>load_global` 3) の参照先は `.text` 11・`.data` 3 件で、`.rdata` は 0 件 (`block00031_PE.bin` の section 表)。
- 測定: 測定 commit `257c3dd51` (rip 相対の経路を入れた分類器)。`m11_setother_repro.py` は 4.3 秒。対象外 291 件の理由変化 0・直接 call 202 の内訳は §4 と同じ。
- `fa7cd079d` で `partial_ext` 分岐を戻した (`257c3dd51` で diff から消えていた)。対照 `movzx ax,cl` (上位既知) → 未決 `partial_ext` を追加し、対照検査は rc=0 (正 7/7・ネガ 3/3・rip 3/3・partial_ext 1/1)。実 PE での再測定は未実施 (§7)。
- 残り 3 種 (算術 16・間接 call の戻り値 4・IR 引数への反映) は未着手。IR への接続方式は未決定。
