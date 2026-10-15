# REPORT_APPENDIX_3077 (WIN-16 #3077)

#2880 (WIN-11) の残りの受入。`CreateFruityInstance` の `EnterCriticalSection(0x12bd390)` が失敗する経路の、boot 側の trap 地点・CS の登録 unit・呼出元 VA を実測で特定した。原因は `function_8c5eb0` の guard699 (#699, D19 の修復 pass) の fail-fast 辺が機械語と食い違うこと。修正後、boot は init 54 の trap を越え、次の停止点は shim の未実装 `LoadImageW`。cfi_probe は依然 `EnterCriticalSection` で止まる。

既知類型: D19 (件数 0 ループ・#699 の修復側)。修正の呼出し先 `410360` の vtable 呼出しの IR 脱落は既知類型 D15 (未解決・§4-1)。新規の lift 欠陥類型は追加しない。shim の欠陥は無し (`CS-MISS` の挙動は仕様どおり)。
測定 commit: `89bee32d` (guard699 の修正。コードを変えた最後の commit)。以降の commit は docs のみ (本節・DOC_MAP)。差分の証跡 (WORKFLOW §6): `git diff 89bee32d HEAD -- tools/m11 tools/shim tools/gui/flengine/cfi_probe.mjs tools/gui/flengine/build.sh` の出力は 0 行。

## 1. 受入条件の状態 (#3077 の 6 項目)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1 boot の `unreachable` の地点 | 達成 | `function_8c5eb0` の guard699 ブロック `dec_label_pc_8c5ef5_g699_t` の `llvm.trap` (§2-1)。呼出し鎖は §2-2 |
| 2 CS `0x12bd390` の登録 unit | 達成 (IR 上)。実行時の登録は未観測 | 登録側は `function_1266a60` (init 列 `inits_text.txt` の 1675 行目) → `function_423940` = `InitializeCriticalSection(0x12bd390)` (§3)。boot が 1675 に届いたかは未計測 |
| 3 `EnterCriticalSection(0x12bd390)` の呼出元 VA | 達成 | 直接の呼出元は `function_4232e0`。呼出し鎖 `CreateFruityInstance` → `function_1265690` → `function_4232e0` → `EnterCriticalSection` (§2-2) |
| 4 解放側 `function_41cd70` が init 列の 4 番目に入る理由 | 未達 | 本 run では未調査。子 issue [WIN-20] |
| 5 DEFECTS 照合と修復 | 達成 (呼出し側)。呼出し先 `410360` の D15 型の脱落は未解決 (§4-1・§8) | D19 の修復側 (guard699 の fail-fast 辺)。機械語 `8c6066`〜`8c60a0` の呼出し側に合わせて修正 (§4)。shim 側の修正は無し |
| 6 `cfi_probe.mjs` が `EnterCriticalSection` を越える | 未達 | 修正後も `CS-MISS key=0x12bd390` で abort。boot が先に `LoadImageW` で止まる (§5)。子 issue [WIN-19] |

## 2. 実測: trap 地点と呼出し鎖 (修正前・同じ IR)

測定に使った build: `boot7` を #2880 §9-2 の手順で再作成 (lift 222,014 行・gen_ir2 707,524 行・m11_build signature mismatch 0)。wasm の関数名は `build.sh` の `-g1` では消えるため、同じフラグで `-g2` にしたリンクを診断用に作った (`tools/gui/work/diag_g2/`、コミットしない)。コードの生成は同じ `-O0` で、デバッグ情報だけ増えている。

### 2-1. boot の trap
- `function_8c5eb0` (VA `0x8c5eb0`) の `dec_label_pc_8c5ef5_g699_t` が `call void @llvm.trap()` を実行する。guard699 (#699) が挿入した件数 0 ガードの fail-fast 辺。
- 通過条件: 件数 `[rcx+0x14] <= 0` かつ arg2 の下位 byte ≠ 0。

### 2-2. 呼出し鎖 (スタックは `-g2` build の JS error stack)
- boot: `m11_boot_enter` → `entry_point` → `function_41d8f0` → `m11_InitLib` → `function_4120c0` → `m11_icall` → `m11_tr_function_56fde0` → `function_56fde0` → `function_8c5eb0` (unreachable)。
- CFI: `CreateFruityInstance` → `function_1265690` → `function_4232e0` → `EnterCriticalSection` → `shim_unimplemented` → abort (CS-MISS `0x12bd390`)。
- `function_1265690` は `function_4232e0(ptr 19649424)` を呼ぶ。`19649424` = `0x12bd390` (IR の定数。動的な引数ではなく、グローバルのアドレス)。

## 3. CS `0x12bd390` の登録と解放 (IR 上)

| 役割 | init 列の行 (`inits_text.txt`) | 関数 | 中身 |
|---|---|---|---|
| 初期化 | 1675 | `function_1266a60` | `function_423940(0x12bd390)` を呼ぶ。`function_423940` は `call void @InitializeCriticalSection` (IR 193361〜193365 行) |
| 解放 | 1676 | `function_12669a0` | `function_423290(0x12bd390)` を呼ぶ。`function_423290` は `call void @DeleteCriticalSection` (IR 192940〜192944 行) |

- 両者は参照カウント (`19649468` = `0x12bd3bc` の `add 1`・`add -1`) で対になる。`function_1266a60` は `function_511fe0` の戻り値を `19649416` に入れてから CS を初期化する。
- `function_1266a60` は `m11_tr_function_1266a60` (icall 経由) としても存在する。init 列の呼出し経路は未確認。
- 1675 番目の到達は未計測。修正前は boot が init 54 で止まる。修正後は `LoadImageW` で止まり、CFI は依然 `CS-MISS` を出す (§5)。

## 4. 修復: guard699 の fail-fast 辺を機械語どおりにする

機械語 (`block00031_PE.bin` を capstone で逆アセンブル):

```
8c6066: cmp qword [rbp+0x90], 0      ; arg3
8c606f: je 8c6084
8c6071: mov rcx,[rbp+0x90]; mov rdx,[rbp+0x80]; call 8ca670
8c6084: cmp byte [rbp+0x88], 0       ; arg2 下位 byte
8c608b: je 8c60df                    ; == 0 → return [rbp+0x80]
8c608d: mov rcx, [rbp+0x80]
8c6094: call 410360                  ; != 0 (件数 0 の経路)
8c6099: mov [rbp+0x80], rax
8c60a0: jmp 8c60df                   ; return [rbp+0x80] (= 410360 の戻り値)
```

- 旧 IR (`_t`): `llvm.trap` (arg3 の `8ca670` 呼出しも飛ばす)。
- 新 IR (`_t`): arg3 ≠ 0 なら `function_8ca670(arg3, arg1)` (戻り値は捨てる)、続けて `r = function_410360(arg1)`、`ret r`。
- 修正は `tools/m11/guard699/m11_guard699.py` の `GD_BLOCK` (1 箇所)。`--mode off`→`--mode on` の往復で IR が一致し、`on` の再適用は変化なし (冪等)。
- 旧版の記録 (`tools/m11/trap_triage/REPORT_699.md` §3-1・§6 (ii)) は、この経路を「本版は trap。挙動変更として記録」としていた。本 run で、この経路が boot の init 54 で実際に通ることを確認した。

### 4-1. 呼出し先 `410360` の効果 (D15 型・未解決)

「機械語どおり」は呼出し側 (`8c608d`〜`8c60a0`) に限る。呼出し先 `410360` の効果は機械語と一致しない。

- 機械語 (VA `0x410360`、`block00031_PE.bin`): `rbx = [rcx]; call [rbx-0x50]` (AfterConstruction の仮想呼出し。`0x41037d`) の後、`[rbp+0x38]` (= 引数) を返す (`0x4103a2`)。戻り値は引数そのもの。
- IR 本体 (`dec_label_pc_410360`): `ret i64 %arg1`。機械語の `call [rbx-0x50]` が IR から脱落している。戻り値は機械語と一致し、欠けるのは副作用の仮想呼出しだけ。
- 型: DEFECTS D15 (メモリ間接 call の無言の脱落・`docs/DEFECTS.md`)。`tools/m11/m11_ov.c` の `function_410360` override が vtable 呼出しを補うが、`M11_OV_CLASSCREATE` は既定 0 のため既定ビルドでは無効。
- 既定ビルドの修正後の実効: 件数 0 ∧ arg2 下位 byte ≠ 0 の経路で、arg3 ≠ 0 なら `8ca670(arg3, v)` を呼んだ後、`v` (= `[rbp+0x80]`) をそのまま返す。機械語の vtable 呼出しは実行されない。
- 根拠の範囲: `410360` が読む vtable (対象 object R の `[vt-0x50]`) が VA `0x410070` (`ret` の stub・no-op) であることは、REPORT_134 §3 が trap 時 (unit 56・1 回目の呼出し) に wasm で実測した。その 1 object の値であり、他の object・修正後の boot が通る他の呼出しは未確認。

## 5. 修正前後の比較 (cfi_probe と boot の実測)

| 項目 | 修正前 (`729a67cb` と同じ IR) | 修正後 (`89bee32d`) |
|---|---|---|
| boot の停止 | `unreachable` (`function_8c5eb0`・init 54) | `gui_failfast: LoadImageW` (`function_623840` → `function_425100` → `LoadImageW`) |
| CFI | `Aborted` 1 ms・`CS-MISS key=0x12bd390` | 同じ (`Aborted`・`CS-MISS key=0x12bd390`) |
| GUI-REACH (cfi_probe) | `LoadStringW` ×3 (reached 1) | reached 12 (`LoadStringW`〜`LoadCursorW` IMPL・`LoadImageW` STUB) |
| 参考: guard のみ外す (`M11_GUARD699=off`) | boot `memory access out of bounds` (#699 の OOB)・CFI は同じ `CS-MISS` | — |

- 参考の行から、trap を外すだけでは CS の登録に届かないと分かる。`off` では #699 の OOB に変わるため、機械語どおりの分岐が必要。
- CFI が `CS-MISS` を出すのは、boot が abort した後の呼出し。boot が 1675 (初期化) まで届いていないか、届いても解放されたかは、未計測 (§6)。

## 6. e2e (測定 commit `89bee32d`・`bash tools/gui/flengine/e2e.sh`)

| 項目 | 結果 |
|---|---|
| 所要・exit | wall 8 分 40 秒・load 0.45 0.62 0.56 → 1.09 1.00 0.79・exit 1 |
| judge | **JUDGE FAIL (13/14)**。失敗は B1 のみ |
| B1 boot parity | FAIL: `units_run 109 (base 109)`・`dllmain_done False` (base `True`)。`init_count` は 111 で一致。原因: GUI shim の `LoadImageW` が fail-fast (§5)。base (shim 無し・m11 の stub 経路) は DllMain が完了する (base 側の `LoadImageW` の扱いは未確認) |
| base の基準値 | B1 の base は `units_run` 52 → 109 に変わった (同じ IR を使うため。base も trap を越えるようになった) |
| L1 / A1 | PASS (sigmismatch/undefined/duplicate 0・declare 193 = adapter 193) |
| R1 / R2 | PASS (`first=LoadStringW calls=3`・`reached=12`) / PASS (reached 33, floor 19) |
| S1 / S2 | PASS `873/1/47/21/0` (base `873/1/47/21/0`) / PASS (ff fail-fast = `['LoadImageW']`) |
| P1〜P5・W1 | PASS (P4 `hwnd=0x1100010`・P5 `hwnd=0x110000f`) |
| selftest / parity / pe_image | 506 passed 0 failed / PASS / PASS |
| ネガコン N1〜N9 | 9 件すべて期待どおり FAIL |

- 前回 (`ae963e28`) の記録は 14/14 (S1 `872/1/47/22/0`)。今回の S1 の値は base と一致する。
- B1 FAIL は修正の副作用。修正前は boot が init 54 で止まり、`LoadImageW` に届かなかった。届くようになった未実装 API を、stub で握りつぶさず子 issue で実装する ([WIN-19])。

## 7. 製品 KPI (起動・ウィンドウ)

- FLEngine 起動の通過 unit 数: 修正前 `units_run 52` (base) / GUI boot は init 54 で停止。修正後 `units_run 109` (base と GUI の両方) / GUI boot は `LoadImageW` で停止 (`dllmain_done False`)。
- 最初のウィンドウ: 製品起動では無し (前後とも。boot が窓作成の前で止まる)。直接テストの P4・P5 の window は従来どおり PASS。
- 動かしていないもの: 実 FL の製品起動。`LoadImageW` 実装後の boot の完走。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `LoadImageW` が shim で未実装 (fail-fast) | boot が `dllmain_done False` で止まり、B1 FAIL・CS の登録 (1675) に届かない | 子 issue [WIN-19] (親 #3077) |
| CS `0x12bd390` の登録 (1675) の実行時の到達・解放 (1676) との順序 | `EnterCriticalSection` の通過 (受入 6) | 子 issue [WIN-19] |
| `function_41cd70` が init 列の 4 番目に入る理由 (受入 4) | 解放の早期実行の有無 | 子 issue [WIN-20] (親 #3077) |
| `tools/m11/guard699/m11_guard699.py` の旧 trap 形を前提にしたネガコン `trap_triage/negctl_699.sh` の G2 (`fix=unreachable`) | 期待値が現版と食い違う (G2 は FAIL する見込み・未実行) | 子 issue [WIN-20] |
| `tools/m11/trap_triage/REPORT_699.md` の §3-1・§6 (ii) の記述 (旧 trap 形) | 旧版の記録。修正の正本は本 REPORT | 子 issue [WIN-20] |
| `tools/gui/flengine/REPORT.md` の行数超過 (479 行・上限 250) | 本 PR 前から超過。分割は別 PR | PR 本文の未解決表のみ |
| `function_410360` の `call [rbx-0x50]` の IR 脱落 (`ret i64 %arg1`・D15 型。既定ビルドで override 無効) (§4-1) | trap 地点の後の vtable 呼出しが無言で消える (D15)。実測は trap 時の 1 object のみ | PM 判断 (REPORT_134 §7 の未解決と同じ。子 issue は作らない) |
| merge 後の main での e2e 未測定 (main は `729a67cb` の後に `tools/m11/m11_run.mjs`・`m11_survey.mjs`・`m11_e2e.sh` など e2e 用スクリプトを変更。`git diff 729a67cb origin/main -- tools/m11` で確認) | merge 後の main 上の e2e 結果は本 PR の測定 (`89bee32d`) と同一とは限らない | PM 判断 (再測定のみのため子 issue は起票しない) |

**PM 判断 (`pm-decision`)**: D15 依存の経路 (`410360` の vtable 呼出しが IR に無い) のまま、boot がこの経路を通ることを許容するか。既定案: **許容** (#3077 の目的どおり、trap を越えて次の停止点へ進める)。許容しない場合は、`410360` の vtable 呼出しを IR に戻す修正が別に必要になる (起票の要否は PM 判断)。本 PR は既定案を前提に出す。
