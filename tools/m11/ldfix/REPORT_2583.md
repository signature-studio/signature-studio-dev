# REPORT #2583 — LD-118: spill 宛 held 9 site の IR・機械語照合 (LD-98 の残り)

親: #2265 (LD-98)。前提の PR #2522 は 2026-10-14T15:52Z に merge 済み (main 取込後に着手。前 run の停止理由は解消)。
照合の対象: `results/held_verdicts_2265.jsonl` の 9 行 (旧判定の根拠の原文)。素材は `work-m11` (`boot_final3.ll`・`m11_image.bin`) と `work-liftdiff` を worktree `ws-2583` に展開して使った。

## 1. 結論 (受入条件ごと)

| 受入条件 | 結果 |
|---|---|
| 9 site を `boot_final3.ll` と `m11_image.bin` で照合し、site・引用行・一致/不一致を表で残す | **達成**。§2 の表 (一致 8・確認不能 1・不一致 0) |
| 一致 site を `held` から `candidate_verdicts_1161.jsonl` へ戻し、`spill_classify_1161.py` で `spill178_1161.tsv` を再生成する | **達成**。8 行を追記し held から削除。spill178 を再生成 (測定 commit `095be5b9`) |
| 不一致・確認不能 site を未判定のまま残し、残数を実測で書く | **達成**。残数 **1** (`6c5930:6c6125`・確認不能)。不一致 0 |
| `audit_lsf_ssa_e2e.sh` の 7/7 を HEAD で確認する | **達成**。測定 commit `095be5b9` で rc=0・7/7 (§5) |

- 測定した commit (コードと結果を変えた最後の commit): **`095be5b9`** (`feat(m11): verify held 8 spill sites against IR and machine code (LD-118, #2583)`)。
- 本 REPORT を含む後続 commit は `tools/m11/ldfix/REPORT_2583.md` と `docs/DOC_MAP.md` だけを変える (§5 の差分の証跡)。

## 2. 照合の表 (9 site)

照合は機械語 (`audit_lsf.descend` で降下) と IR (`boot_final3.ll`) の両面で行った。機械語の前後は `ld118_show.py` (作業用・非コミット) で出した。IR の行番号は `boot_final3.ll` の行。旧 evidence の主張のうち誤りのあった点は §4 に書く。

| site | 旧判定 | 機械語 (VA・命令) | IR (boot_final3.ll 行) | 結論 | 新判定 |
|---|---|---|---|---|---|
| 775340:77545c | TRUE_DROP | 77545c `mov [rbp+0x90],rax` (P=*X の格納)。消費者 775678 `call 0x7747c0` が rcx を読む | 290821 `call function_7747c0()` (引数 0 個)。被呼出側 290584 の alloca に store 無し、290589 の load が未初期化 | 一致 | TRUE_DROP |
| 775340:77593b | OK_LOAD | 77593b `mov [rbp+0x70],rax`。消費者 7759f6・775a29 が P を読んで float store | 291006 `load P` → 291069・291092 の store が同じ P を使う | 一致 (P の流れ) | OK_LOAD |
| 815050:815220 | TRUE_DROP | 815216・81521d の二段 load (`mov rax,[rip+..]` → `mov rax,[rax]`)。815220 で格納。消費者 815227・815231・815238 は二段目の値 | 318485 `load G` は一段のみ。318486・318491・318493 は一段目の `%69` を使う | 一致 | TRUE_DROP |
| 6c3700:6c3c78 | TRUE_DROP | 6c3c78 `mov [rsp+0x20],eax` → 6c3c80 `call [r13+0x128]` (第 5 引数) | 267396-267407 の内側ループに間接 call も機械メモリの load も無い (spill slot の再読込のみ) | 一致 | TRUE_DROP |
| 6c3d20:6c44bd | TRUE_DROP | 6c44bd `mov [rsp+0x20],eax` → 6c44c5 `call [rsi+0x128]` | 267830-267841 に間接 call 無し | 一致 | TRUE_DROP |
| 6c5930:6c6125 | TRUE_DROP (根拠は IR 不在のみ) | 6c6125 → 6c612d `call [rbx+0x128]`。到達は 6c6042 の jle 経由 (静的に到達可) | 6c5930 の IR は 6c5a6e 付近で打ち切られ (ラベルは 6 個のみ)、6c6037 以降に対応ブロック無し (267973-268105) | **確認不能** | **未判定 (held に残す)** |
| 1042d20:1043e2d | TRUE_DROP | 1043e2d `mov [rsp+0x20],eax` → 1043e34 `call [rsi+0x188]` (第 5 引数) | 14895 `function_60a270` の後、14898 は直接 call `function_12d6660(%895)` のみ。間接 call 無し | 一致 | TRUE_DROP |
| f3e050:f3e0c2 | TRUE_DROP | f3e0c2 store。je 不成立側の f3e0f7 → f3e10b `call [rax+0x38]` (rdx=slot) | 468253 の je 成立側 468265-468278 に slot を渡す call も間接 call も無い。slot を渡す call 468262 は別分岐 | 一致 | TRUE_DROP |
| 12f9730:12f9752 | TRUE_DROP | 12f9748-12f9750 の二段参照 (`[[arg2]]` の dword) → 12f9752 store。消費者 12f975e `add ecx,[rax+8]`・12f9842 `cmp` | 96779 `%1 = xor i64 0,0` → 96781 `trunc` (入口ブロック・到達可)。96785・96871 に定数 0 が流入 | 一致 | TRUE_DROP |

- 一致 8 件の機械語側は subagent 3 名が読み取りで照合し、親が主要な IR 行を再確認した (775340 の 290580〜290592・290819〜290821、815050 の 318483〜318494、12f9730 の 96778〜96782・96869〜96872、6c3700 の 267395〜267408、1042d20 の 14894〜14899・14965〜14973、f3e050 の 468252〜468266)。
- 機械語の確認は `audit_lsf.descend` の降下結果に基づく (`ld98_dump.py` と同じ経路)。

## 3. 残数と分布 (実測)

| 項目 | 変更前 (97bfd673) | 変更後 (095be5b9) |
|---|---|---|
| spill 宛 unk site の status 未判定 | 9 | **1** (`6c5930:6c6125`) |
| status 確定 / 判定不能 | 139 / 30 | 147 / 30 |
| 脱落関数の和集合 (`drops_510` 69 + spill 宛の確定 TRUE_DROP で drops_510 に無い関数) | 77 (= 69 + 8) | **83** (= 69 + 14) |

- 和集合の増分 6 関数: `6c3d20` `775340` `815050` `f3e050` `1042d20` `12f9730` (本 PR で新たに確定 TRUE_DROP。`6c3700` は前 run から確定済み)。
- `results/spill178_1161.tsv` の変更は 8 行 (未判定 → 確定)。

## 4. 判定の訂正と強さ

- **1042d20:1043e2d**: 旧 evidence の「IR 14896–14897 の load 2 本は未使用」は誤り。14966・14968・14972 で使われる。判定の根拠は間接 call `[rsi+0x188]` に対応する IR の call が無いことで、この根拠は変わらない。台帳の evidence に訂正を注記した。
- **12f9730:12f9752**: 旧 evidence の「12f975e `mov ecx,[rsp+0x50]` → cmp」は誤り。12f975e の直後は `add ecx,[rax+8]` (機械語 12f9762) で、cmp は 12f9846 の側。判定の根拠 (store 元が `xor i64 0,0` に置換されて 96871 に 0 が流入) は変わらない。
- **6c3700:6c3c78・6c3d20:6c44bd**: 旧 evidence の「ループに load も無い」は、機械メモリの load が無いという意味に限る (spill slot の再読込はある)。
- **6c5930:6c6125**: 根拠が IR の不在のみで弱い。機械語の到達は確認できたが、IR が 6c5a6e 付近で打ち切られているため対応箇所を決められない。確認不能として未判定に残す (受入条件の「確認できない site は未判定」)。
- **775340:77593b (OK_LOAD)**: 注記の間接 call 7759bb の副作用は、P の複写スロット `[rbp+0x70]` も X の再読みも無いため P の流れには影響しない。ただし、7759d3 が読む `[rbp+0xac]` は IR 291044 で定数 `%1 = 0` になっている (§5 の別件)。

## 5. 検証 (e2e 実測と差分の証跡)

- 変更前 HEAD `97bfd673`: `TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` → rc=0・real 2m47s・load 0.44 0.29 0.11 (開始) → 0.98 0.62 0.28 (終了)・7/7。step 7: 未判定 9・確定 139・判定不能 30。和集合 77。
- **測定 commit `095be5b9`** (本 PR のコードと results の最後の commit): 同じ手順 → **rc=0・real 166 s・load 0.02 0.13 0.16 (開始) → 0.98 0.52 0.31 (終了)・7/7 完了**。step 5 の `drops_510.tsv`・step 7 の `spill178_1161.tsv` は results/ と cmp 一致。step 7: 未判定 1・確定 147・判定不能 30。和集合 83 (= 69 + 14)。
- 差分の証跡: `git diff --stat 97bfd673 095be5b9 -- tools/m11/ldfix/results tools/m11/ldfix/*.py tools/liftdiff` = 3 files changed, 16 insertions(+), 16 deletions(-) (results の 3 ファイルのみ。e2e の入力のうち results の変更)。
- 測定 commit から HEAD までのコード差分 (e2e が読む範囲): `git diff 095be5b9 HEAD -- tools/m11/ldfix/audit_lsf.py tools/m11/ldfix/audit_lsf_ssa.py tools/m11/ldfix/window_recount.py tools/m11/ldfix/dyn_xcheck.py tools/m11/ldfix/tally_510.py tools/m11/ldfix/negctl_510.sh tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/audit_lsf_ssa_e2e.sh tools/m11/ldfix/results tools/liftdiff` の出力は空。この REPORT と `docs/DOC_MAP.md` の追加のみが後続 commit の変更で、e2e の入力に触れない。再測定は要らない (`docs/WORKFLOW.md` §6)。
- `find tools/m11/ldfix -type f -size +20M` = 0 件。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `6c5930:6c6125` の確認 (IR が 6c5a6e 付近で打ち切られ、6c6037 以降の対応ブロックが無い) | 脱落集合 83 の外。当該 site は未判定 1 件 | 親 #2265 へ報告。IR の打ち切りは lift 側の修復 (PM 判断) |
| `775340` の `[rbp+0xac]` の定数化 (IR 291044 `%1 = 0`)。float 格納値の欠落の疑い | 775340:77593b の float 値 (P の流れは一致)。判定の範囲外 | 親 #2265 へ報告 (候補。DEFECTS 未登録) |
| 12f9846 の `jle` (符号付き) と IR 96871 の `icmp ugt` (符号なし) の不一致 | 12f9730 の比較の符号扱い。REPORT_2265 §4 の 1221290 と同型 | 親 #2246 へ報告 (判定外の別欠陥候補) |
| 新規類型の DEFECTS 行案 (775340:77545c の間接 call 引数欠落・12f9730:12f9752 の二段参照の定数化) | `docs/DEFECTS.md` 未登録 | 行案は REPORT_2265 §5 に既出。DEFECTS 登録は PM 判断 |
| `REPORT_1161.md` の §表 (旧判定保留 9 site の行) が本 PR 時点で古い | 数値の二重記載 (REPORT_1161 の測定値) | 次の REPORT_1161 再測定で更新 (起票しない) |
