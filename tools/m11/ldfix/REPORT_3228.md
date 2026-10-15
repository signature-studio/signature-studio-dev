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

- 測定 commit: `028bbd9fb`。検証 HEAD: `878c87dfc` (origin/main 取り込みの merge commit)。
- 判定が実行するファイル (判定器 `audit_frame_store_callee_3228.py`・`ldmach.py`・`audit_frame_store_verdict.py`・`audit_frame_store_alias_2211.py`・入力 `results/audit_undefload_564_full.json`・`results/f4_564_post.json`・`results/frame_store_verdict_2211.json`) は、`git diff --stat 028bbd9fb 878c87dfc -- <上の 7 ファイル>` が空 (差分 0)。
- `git diff --stat 028bbd9fb 878c87dfc -- tools/m11/ldfix` の全体は 9 ファイル (本 PR の追加 3 本 = REPORT_3228.md と結果 JSON 2 本、main 取り込み由来 6 本 = REPORT_1325.md・REPORT_3195.md・REPORT_3230.md・residual_3195.py・fix_shx_t40.py・u3_check_4040.py)。main 由来の変更は判定に使わない。

## 4. 未達の受入条件 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1006fb6 の間接 call `[rax+0x30]` の呼び出し先の特定 | 1006ec0 が UNDETERMINED | #4086 [LD-191] |
| 呼び出し先が call を含む 3 site (1354784・44178f・454637) の再帰的追跡 | 1354630・441730・454090 が UNDETERMINED | #4086 [LD-191] |
| 関数境界が取れない 2 site (44892d → 423d20・5c4e43 → 424300) の関数境界の確認 | 4488f0・5c4dc0 が UNDETERMINED | #4086 [LD-191] |
| 呼び出し先の store 命令の REPORT 化 (call 命令・打ち切り理由は §3.2 で記録済み) | 呼び出し先の判定根拠が未記録 (受入 3 の残り) | #4086 [LD-191] |

受入 2 (DROP / LIVE-IN / UNDETERMINED の再判定) は未達。6 site の判定は 2211 から変わらない。

## 5. LD-191 (#4086) の残件 (機械語の呼び出し先)

PM 決定 (#4086 コメント, R7): 判定器は測定 commit `028bbd9fb` の版に固定。IAT thunk と間接 call は UNDETERMINED のまま。
判定器の版違いは §5.4 に記す。判定は `results/callee_chain_191.json` (`audit_callee_chain_191.py` が出力) の機械語事実に基づく。

測定 commit は成果物ごとに次の通り:
- `results/frame_store_callee_3228.json` (判定器 `audit_frame_store_callee_3228.py`): `028bbd9fb`。
- `results/callee_chain_191.json` (`audit_callee_chain_191.py`): 本 PR の `audit_callee_chain_191.py` を最後に変えた commit (下記 §5.5 の `HEAD`)。IAT thunk の import 名は同じ commit の出力で確認する。

### 5.1 呼び出し先の事実

| 元 site | 打ち切り call | 呼び出し先 | 機械語の事実 | 判定 (打ち切り) |
|---|---|---|---|---|
| 1006ec0 | `1006fa9 call [rax+0x30]` | 間接 | rdx = `lea [rbp+0x2c]` (frame 番地)。参照先は vtable 経由で PE 内に静的に決まらない | UNDETERMINED (INDIRECT_FRAMEARG) |
| 1354630 | `135477f call 0x12b0020` | 0x12b0020 (13 命令) | rdx = rcx (frame 番地) を受け、`call [rbx+0x28]` (vtable 経由・間接) へ渡す | UNDETERMINED (CALLEE_CALL・先は間接) |
| 441730 | `44177b call 0x441530` | 0x441530 (16 命令) | rcx = rbx (frame 番地) を受け、`call 0x441500` を条件 loop 内で呼ぶ。0x441500 は `[rcx+0x80]` 経由で `[rcx+0x6e]` に word を書く (条件付きの loop 内) | UNDETERMINED (CALLEE_CALL) |
| 4488f0 | `448928 call 0x423d20` | 0x423d20 (IAT thunk) | `jmp [rip+0x154d7e2]` のみ。IAT slot RVA `0x1571508` = `kernel32!VirtualQuery` | UNDETERMINED (外部 DLL・§5.3) |
| 454090 | `454524 call 0x41c820` | 0x41c820 (42 命令) | rdx = frame 番地を受け、`41c85d call [rip+0xf8882d]` (間接・PE 内 global の初期値 0) と直接 call 4 件 (0x418be0・0x407030・0x413060・0x4148e0) を含む | UNDETERMINED (CALLEE_CALL) |
| 5c4dc0 | `5c4e3e call 0x424300` | 0x424300 (IAT thunk) | `jmp [rip+0x154d69a]` のみ。IAT slot RVA `0x15719a0` = `gdi32!GetSystemPaletteEntries` | UNDETERMINED (外部 DLL・§5.3) |

事実の出どころ: `tools/m11/ldfix/results/callee_chain_191.json` (`audit_callee_chain_191.py`)。IAT thunk の 2 件は JSON の `IAT_THUNK`・`iat_slot_rva`・`import` の各フィールドで確認できる (`4488f0`・`5c4dc0` の `callee`)。

### 5.2 判定の変化

本 issue では判定器に再帰追跡を入れていない (判定器は `CALLEE_CALL` で打ち切るまま)。`audit_callee_chain_191.py` は呼び出し先 1 段の機械語事実だけを出す。
1 段の事実では、残り 4 site (1354630・441730・454090) の呼び出し先は間接 call か条件付き store を含み、DROP と確定できる根拠は無い。
再帰で DROP / LIVE-IN まで進める作業は残件として残す (受入 2 の残り。§5.6)。6 site とも判定は UNDETERMINED のまま。

### 5.3 IAT thunk (外部 DLL) の扱い

PE 内に関数本体が無い (`jmp [rip+X]` の転送のみ)。`.pdata` に関数境界が無いため `disasm_fn()` は空を返すが、生バイトの先頭 2 byte が `ff 25` (jmp [rip+disp32]) であることを `audit_callee_chain_191.py` が判定し、`IAT_THUNK`・`iat_slot_rva`・`import` を JSON に記録する (`0x423d20` → `kernel32.dll!VirtualQuery`、`0x424300` → `gdi32.dll!GetSystemPaletteEntries`)。PM 決定 R7 に従い、外部 DLL へ frame 番地を渡す call は打ち切り (UNDETERMINED) とする。
`VirtualQuery` と `GetSystemPaletteEntries` の DLL 側の仕様 (frame 番地の扱い) は **未確認**。受入 3 は「PE 内に本体が無いことの確認 (JSON で再現可能)」として達成し、外部 DLL 側は未達のまま残す。

### 5.4 判定器の版違い (測定値の固定)

- 測定 commit `028bbd9fb` の版で `audit_frame_store_callee_3228.py` を再実行: DROP 3 / LIVE-IN 35 / UNDETERMINED 10 (関数)、site は DROP 3 / LIVE-IN 36 / UNDETERMINED 11 / PTR_READ 1。`results/frame_store_callee_3228.json` と byte 一致。
- 現 origin/main (6c772a812) の版で再実行: DROP 3 / LIVE-IN 1 / UNDETERMINED 44 (関数)、site は DROP 3 / LIVE-IN 1 / UNDETERMINED 46 / PTR_READ 1。件数が変わる。
- 差分の出どころ: `audit_frame_store_alias_2211.py` (測定 commit 以降 151 行変更)・`audit_frame_store_callee_3228.py` (3 行変更)。
- 本 issue では測定 commit 版を正とし、main 版の再測定は行わない (PM 決定。main 版の件数変化は別件)。

### 5.5 測定 commit からの差分 (WORKFLOW §6)

- `results/frame_store_callee_3228.json` の測定 commit: `028bbd9fb` (§5.4 の版固定)。
- `results/callee_chain_191.json` の測定 commit: 本 PR で `audit_callee_chain_191.py` を最後に変えた commit (PR 本文の `測定 commit` 欄)。
- 検証 HEAD: 本 PR の merge 元 commit (下記の `HEAD`)。
- 判定に使うファイル (`audit_frame_store_callee_3228.py`・`ldmach.py`・`audit_frame_store_verdict.py`・`audit_frame_store_alias_2211.py`・入力 3 本) は、測定 commit から origin/main までに変更あり (`audit_frame_store_alias_2211.py` 151 行・`audit_frame_store_callee_3228.py` 3 行)。判定は測定 commit 版を使うため、この差分は結果に入らない。
- 本 PR で追加した判定器は無し。追加は `audit_callee_chain_191.py` (機械語の事実出力のみ・判定なし) と `results/callee_chain_191.json`。

### 5.6 残件 (受入の未達)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 call `[rax+0x30]` (1006fa9)・`[rbx+0x28]` (12b0045)・`[rip+0xf8882d]` (41c85d) の参照先 (vtable 実体) | 1006ec0・1354630・454090 が UNDETERMINED のまま | #4086 (PM 決定で打ち切り維持。判断は PM) |
| 0x441500・0x41c820 配下の call 先の再帰追跡 (判定器の変更が必要) | 441730・454090 の DROP / LIVE-IN 判定 | #4086 |
| IAT thunk 2 件の外部 DLL 側の仕様 (`VirtualQuery`・`GetSystemPaletteEntries`) | 4488f0・5c4dc0 の判定 | #4086 |
