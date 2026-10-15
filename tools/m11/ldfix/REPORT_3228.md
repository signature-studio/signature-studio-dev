# REPORT_3228 — 漏出関数の call 越え 6 site の呼び出し先 store 判定 (#3228 / 親 #2211)

## 1. 測定条件

- 測定 commit: `028bbd9fb` (判定器 `audit_frame_store_callee_3228.py` を含む commit)。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211 と同じ)。
- PE: fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#2211 と同じ)。
- 再現: `audit_frame_store_alias_2211.py` を再実行し、`frame_store_verdict_2211.json` と byte 一致 (DROP 3・LIVE-IN 35・UNDETERMINED 10)。
- 判定器: 実行 0.25 秒 (4 vCPU・load average 0.01)。

## 2. 方式

2211 の判定器と同じ CFG 逆向き探索・同じ 3 値判定。変えたのは glk 関数の call だけ。

- call の引数 (rcx・rdx・r8・r9) の由来を、直前の定義から見る。
  - `FRAME(K)`: `lea`/`mov` で `[rbp+K]` の番地。
  - `MAYFRAME`: 由来が決まらない (分岐の合流・メモリ読み・間接 call)。frame 番地かもしれないとして扱う。
  - `NONFRAME`: 即値・rip 相対・直前の call の後・入口の値。
- `FRAME` / `MAYFRAME` の引数を受ける直接 call は、呼び出し先を機械語で見る。
  - 呼び出し先の R (引数) 由来の値を `[R+d]` へ store するなら、caller の `[rbp+K+d]` への書きと見る。読みの slot を全て覆う plain store が分岐の前にあれば `DEF`、一部だけなら `CALLEE_PARTIAL`。
  - R 由来の値を他へ出す (`ret` の rax・`push`・別 store の値) なら `CALLEE_ESCAPE`。
  - 呼び出し先が call を含む・関数境界が取れない・間接 call は打ち切り (`CALLEE_CALL`・`CALLEE_NOFN`・`INDIRECT_FRAMEARG`)。
- frame 番地を渡さない call は、その関数が frame 番地を外部メモリへ漏らさない (`leak_ext` 偽) なら透過。

仮定 (未検証): 引数レジスタは call で破壊されるので、直前の call を越えた引数は使われない (NONFRAME)。大域 (rip 相対) に frame 番地が保存される経路は見ない。呼び出し先が別の call で frame を使う経路は見ない (CALLEE_CALL で打ち切る)。

## 3. 結果

### 3.1 関数単位 (受入 2 の一部)

| 判定 | #2211 | #3228 |
|---|---|---|
| DROP | 3 | 3 |
| LIVE-IN | 35 | 35 |
| UNDETERMINED | 10 | 10 |

6 site の判定は変わらない (全て打ち切りのまま)。

### 3.2 6 site の打ち切り理由 (機械語)

| 関数 | 読み | 経路上の打ち切り (機械語) | 理由 |
|---|---|---|---|
| 1006ec0 | `1006fb6 cmp dword ptr [rbp + 0x2c], 1` | `1006fa9 call qword ptr [rax + 0x30]` | INDIRECT_FRAMEARG (間接 call に frame 番地が渡る可能性) |
| 1354630 | `1354784 cmp word ptr [rbp + 0x1d2], 1` | `135477f call 0x12b0020` | CALLEE_CALL (呼び出し先が call を含む) |
| 441730 | `44178f cmp word ptr [rbp + 0x6e], 0` | `44177b call 0x441530` | CALLEE_CALL |
| 4488f0 | `44892d cmp dword ptr [rbp + 0xd8], 0x1000` | `448928 call 0x423d20` | CALLEE_NOFN (呼び出し先の関数境界が取れない) |
| 454090 | `454637 cmp byte ptr [rbp + 0x16e], 1` | `454524 call 0x41c820` | CALLEE_CALL |
| 5c4dc0 | `5c4e43 cmp dword ptr [rbp + 0x58], 0xc0c0c0` | `5c4e3e call 0x424300` | CALLEE_NOFN |

6 site とも、読みから逆向きに辿る経路上で最初に当たる call で止まる。残る経路の判定は、この呼び出し先を先へ追うまで決まらない。

### 3.3 ネガティブコントロール (WORKFLOW §5)

| 条件 | DROP / LIVE-IN / UNDETERMINED (関数) | 変わった site (ctrl → 壊す) |
|---|---|---|
| ctrl (`results/frame_store_callee_3228.json`) | 3 / 35 / 10 | — |
| 壊す (`--negctl-transparent`: frame 番地を渡す call を全て透過) | 3 / 39 / 6 | 4 (1354784・44892d・454637・5c4e43 が UNDETERMINED → LIVE-IN) |

壊したときに変わるのは、呼び出し先の判定が効いている 4 site だけ。ただし、この 4 site の LIVE-IN は「呼び出し先を見た結果」ではなく「打ち切りを外した結果」なので、判定の正しさの根拠にはならない。

### 3.4 差分 (WORKFLOW §6)

- 測定 commit: `028bbd9fb`。
- `git diff 028bbd9fb HEAD -- tools/m11/ldfix` は REPORT_3228.md と結果 JSON 2 本 (`frame_store_callee_3228.json`・`negctl_callee_3228_transparent.json`) の追加だけ (PR 本文の検証結果に出力を載せる)。

## 4. 未達の受入条件 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1006fb6 の間接 call `[rax+0x30]` の呼び出し先の特定 | 1006ec0 が UNDETERMINED | #4086 [LD-191] |
| 呼び出し先が call を含む 3 site (1354784・44178f・454637) の再帰的追跡 | 1354630・441730・454090 が UNDETERMINED | #4086 [LD-191] |
| 関数境界が取れない 2 site (44892d → 423d20・5c4e43 → 424300) の関数境界の確認 | 4488f0・5c4dc0 が UNDETERMINED | #4086 [LD-191] |
| 呼び出し先の store 命令の REPORT 化 (call 命令・打ち切り理由は §3.2 で記録済み) | 呼び出し先の判定根拠が未記録 (受入 3 の残り) | #4086 [LD-191] |

受入 2 (DROP / LIVE-IN / UNDETERMINED の再判定) は未達。6 site の判定は 2211 から変わらない。
