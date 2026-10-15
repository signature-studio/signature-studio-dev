# REPORT_4204 — 5cb210 `5cb4aa` の call 戻り値の別名判定 (LD-204 / 親 #4166)

## 1. 結論

`5cb4aa` の判定は **UNDETERMINED (BARRIER(LEAK_STORE))** のまま。DROP にも LIVE-IN にもしない。
受入 3 (示せない) に該当する。理由は 2 つ (§4):

1. `call 0x409410` の戻り値 `rax` は、間接 call 先 `407a50` の戻り値に依存する。`407a50` の戻り値が frame を指さないことを示すには、5 個の呼出し先まで解析が必要。
2. `5cb210` は `5cb21e mov qword ptr [rbp+0x68], rbp` (frame アドレスの自己保存) により glk になり、`5cb47d` の store が LEAK_STORE で打ち切られる。これは #3225 (LD-150) の範囲で、戻り値の規則では解けない。

判定器 `audit_frame_store_alias_2211.py` の規則は変えていない。

## 2. 測定条件

- 測定 commit: `0607eacb1` (判定器は未変更。結果 JSON `results/frame_store_alias_4204.json`・`results/negctl_alias_4204_glk.json` を含む)。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211・#4166 と同じ)。
- PE: fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#2211 と同じ)。
- 判定器: 0.26 秒 (rc 0)。load average 0.07 (4 vCPU)。
- 再現確認: 測定 commit の判定器で再実行し、`results/frame_store_verdict_2211.json` と 48 関数・51 site が完全一致 (fn diff 0・site diff 0)。

## 3. 機械語の追跡 (受入 1)

| 段 | 機械語 | 結果 |
|---|---|---|
| 0 | `5cb3d3 call 0x409410` → `5cb3d8 mov [rbp+0x148], rax` → `5cb43c mov rdi, [rbp+0x148]` → `5cb456 movsq [rdi], [rsi]` (LEAK_STORE 打ち切り) | `5cb4aa` の読みは `5cb456` で止まる。`rdi` が frame を指すかが問題 |
| 1 | `409410`: `test rcx,rcx; jg 40941e`。`40941a xor ebx,ebx` か `40941e call qword ptr [rip+0xf9c86c]`。`mov rbx,rax`・`test rbx,rbx`・`jne`・`mov rax,rbx`・`ret` | 戻り値 `rax` = `rbx`。`rbx` は 0 か、間接 call の戻り値。`40942c call 0x409730` (cl=1) は `rbx` = 0 の経路だけで、戻り値に影響しない |
| 2 | 間接 call の slot `RVA 0xfa5c90` (`.data`) | import directory に対応無し。静的初期値は `0x407a50`。全 57816 関数の rip 相対参照を走査し、書き込みは見つからなかった。参照は call 3 箇所のみ (`409410`・`409470`・`41c250`) |
| 3 | 直接 call 先 `407a50` (243 命令。`lock cmpxchg` を含むアロケータ形) | 戻り値 `rax` の生成は `mov rax,[rdx+0x18]`・`mov eax,0x100`・`lea rax,[rip+...]`・`call 0x4073e0/0x4074d0/0x407570/0x407680/0x407770`・`mov rax,rsi`・`xor rax,rax` など。`frame_derived` の F は rbp/rsp だけ |
| 4 | `407a50` の呼出し先 5 個 (`4073e0`・`4074d0`・`407570`・`407680`・`407770`) | この run では解析しなかった。戻り値の由来を閉じるには、これらの戻り値規則まで広げる必要がある (子 issue へ) |

段 2 の走査は `ldmach.Machine` で `.pdata` の関数境界を使い、rip 相対の実効アドレスを比べた。

## 4. 判定の理由 (受入 2・3)

1. **戻り値の規則が閉じない**: 判定器の現行規則は「戻り値は rax のみ」「call は ENTRY_AFTER_CALL の印を付けるだけ」。`409410` の戻り値を frame 非派生と示すには `407a50` の戻り値を示し、その中の 5 個の呼出し先の戻り値まで辿る必要がある。
2. **漏出 store が残る**: `5cb210` の frame 派生値 F への漏出は、`5cb21e mov qword ptr [rbp+0x68], rbp` (自己保存) の 1 箇所だけ (`frame_derived` と store/call/ret の走査で確認)。この 1 箇所で関数全体が glk になり、`5cb47d mov dword ptr [rax+8], ecx` が LEAK_STORE になる。戻り値の規則を広げても、`5cb47d` は残る。これは #3225 (LD-150) の範囲。

## 5. ネガティブコントロール (受入 4)

| 条件 | 関数 DROP / LIVE-IN / UNDETERMINED | site DROP / LIVE-IN / UNDETERMINED / PTR_READ | 結果 JSON |
|---|---|---|---|
| 対照 (規則変更なし) | 3 / 35 / 10 | 3 / 36 / 11 / 1 | `results/frame_store_alias_4204.json` |
| 壊す (`--negctl-glk`: 全関数の漏出を True) | 3 / 1 / 44 | 3 / 1 / 46 / 1 | `results/negctl_alias_4204_glk.json` |

壊す条件の結果は `results/negctl_alias_2211_glk.json` と fn・site ともに一致する (漏出規則が効いていることの再確認)。対照の `5cb210` は `5cb4aa` が `BARRIER:LEAK_STORE` (`5cb47d`)。

## 6. 差分 (WORKFLOW §6)

- 測定 commit: `0607eacb1`。
- この commit から HEAD までで `tools/m11/ldfix` に変わるのは本 REPORT (`REPORT_4204.md`) のみ。`git diff 0607eacb1 HEAD -- tools/m11/ldfix` の出力は PR 本文に載せる。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出し先 `407a50` と 5 個 (`4073e0`・`4074d0`・`407570`・`407680`・`407770`) の戻り値規則 | `409410` の戻り値が frame 非派生と示せず、`5cb4aa` の判定が閉じない | #4238 [LD-205] |
| 漏出 store `5cb47d` (frame 自己保存 `5cb21e` が根) | 関数 5cb210 が glk のまま `5cb4aa` が UNDETERMINED | #3225 [LD-150] |
