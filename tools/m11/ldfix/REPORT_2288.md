# REPORT #2288 — spill 宛 未判定 `c589b0`・`128f9e0` 24 site の IR 側突合 (LD-104)

親: #2266 (LD-99) / #2244 (LD-92) / #1161 (LD-35)。本 run は判定を 1 件も入れず、機械語側の入口と IR 側の不一致を残した。

## 1. 測定

- 測定 commit: e53d845b (run 開始時の origin/main)。以後コード差分は 0 (`git diff e53d845b HEAD -- tools/m11/ldfix` が空)。
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (rc=0・所要 1m53s・7/7 完了・load average 0.42)
- 結果: `spill178_1161.tsv` と `drops_510.tsv` は results/ と一致 (cmp OK)。
- 集計 (step 7/7): spill 宛 unk site 178 / 71 関数。status 未判定 120 / 確定 51 / 判定不能 7。脱落関数の和集合 69 (変更無し)。
- 素材: `work-m11` は `tools/m11/work/`、`work-liftdiff` は `tools/liftdiff/work/` に展開 (tarball 内が `tools/m11/work/...` の相対パスのため、展開後に 1 段移動した)。
- 再現用の素材名: `oc_artifacts: fl-win64 work-m11` (`work-liftdiff` は `audit_lsf_ssa_e2e.sh` の 4/7・5/7 で使うため併せて指定する場合は `work-liftdiff` を足す)。

## 2. 機械語側の主張 (前 run の記述。§7-1 で再検証)

- 対象 24 site は `spill178_1161.tsv` の status=未判定 (`c589b0` 12 / `128f9e0` 12) と一致 (§1 の集計で確認)。
- 前 run の主張は次のとおりで、2 回目 run の §7-1 で `work-m11` の image から再検証した (fl-win64 の PE は使っていない)。
  - 全 24 site で、store 元 (`mov qword ptr [rbp+X], rax`) の直前に `mov rax,[rip+X]` → `mov rax,[rax]` (二段参照) があり、一段目の参照先が LVA `0x11e0ab0` (10 進 18746032) である。 → 再現。
  - 同 slot は両関数の機械語からそれぞれ 27 回参照される (両関数で計 54 回)。 → 再現 (前 run の「計 27 回」は各関数の数)。

## 3. IR 側の確認 (不一致)

- IR 本体は `function_c589b0` (390809〜391214) と `function_128f9e0` (76541〜77198) で、issue 記載と一致。
- **両関数の IR に、slot `0x11e0ab0` (定数 `18746032`) を読む命令は 1 件もない** (IR_refs=0)。本 run で再実行して一致 (下記)。
- `boot_final3.ll` 全体では `18746032` は 8 件で、**すべて `function_10c7cd0`** (define 行 32557 の関数内) にある。hit の行は 34472, 35307, 35314, 35325, 35426, 36276, 36283, 36294 (いずれも `inttoptr (i64 18746032 to ptr)` の load)。`function_cf3790` (定義行 401631) には無い。
- 一方、既判定の TRUE_DROP 候補 `c5d2df`・`c5d343` が読む定数は `18751296` (LVA `0x11e1f40`) で、`0x11e0ab0` とは別セル。
- REPORT_2266 の「slot `0x11e0ab0` の 1 段 deref」という記述は、IR 側では確認できない。IR に読みが無いため、「deref が落ちている」か「値が別経路で作られる」かを site ごとに区別できない。

### 3-a. 再現の状況 (未再現・記録の欠落)

- **IR 側 (§3) は本 run で再実行して一致した**。対象 IR は `oc_artifacts: work-m11` で展開した `tools/m11/work/boot_final3.ll` (展開元 `work-m11.tar.zst`・gitignore 対象)。
  - sha256: `010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e` (本 run 実測)
  - `grep -n '18746032' boot_final3.ll` → 8 件 (全件 `function_10c7cd0` 内。§3 の行番号)
  - `sed -n '390809,391214p' boot_final3.ll | grep -c 18746032` → 0 件 (`function_c589b0`)
  - `sed -n '76541,77198p' boot_final3.ll | grep -c 18746032` → 0 件 (`function_128f9e0`)
  - `grep -ci '11e0ab0' boot_final3.ll` → 0 件 (16 進表記)
- **§2 (機械語側) は 2 回目 run で再現した** (§7-1)。
- `boot_final3.ll` は実行ごとに sha256 が変わり得る (`docs/WORKFLOW.md` §11・#680)。再現には上記 sha256 の IR が要るため、次の手順でも sha256 を必ず記録する。
- 再現手順 (次 run・未実行。素材 `oc_artifacts: fl-win64 work-m11` が前提):
  1. `tools/m11/work/boot_final3.ll` の sha256 を記録する (`sha256sum`)。
  2. IR 側: `grep -c '18746032'` を全体と `function_c589b0` (390809〜391214 行) / `function_128f9e0` (76541〜77198 行) の範囲で数える。範囲の抜き出しは `sed -n 'A,Bp'`。
  3. 機械語側: fl-win64 の PE を capstone で逆アセンブルし、rip 相対で `0x11e0ab0` を指す命令を走査する。出力と走査スクリプトを `tools/m11/ldfix/results/` に残す (生成元を REPORT に書く)。
  4. 上記の結果が §2・§3 と違えば、§2・§3 を書き換えて §4 の判定 (0 件) を見直す。

## 4. 判定の結果

- 本 run で確定させた判定: **0 site**。`candidate_verdicts_1161.jsonl` は変更なし。
- 理由: 24 site の判定根拠 (IR の store→load 対応) を IR 側で立てられなかった。IR に当該 slot の読みが無いため、TRUE_DROP / OK_LOAD / NO_CONSUMER のどれを付けても根拠にならない。根拠の無い判定は脱落集合を誤って確定させる。

## 5. 次の一手 (後続に渡す)

1. slot `0x11e0ab0` の値の出自: 機械語側は §7-1 で確定した (セル → V の参照。V は実行時に値が入る参照フィールド)。残りは V の実行時値の出所 (§7-4 の 2)。
2. その結果で IR 側の扱いを決める: IR が slot を一切読まない場合、24 site の store 元は IR の別経路 (`function_X__lifted` や inline 展開) を経ている可能性があり、関数の IR 本体の取り違えを先に確認する。
3. 判定は 1 と 2 の後に、site 単位で `candidate_verdicts_1161.jsonl` と同じ形式で入れる。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `c589b0` の未判定 12 site の IR 突合 (判定 0 件) | spill 宛の脱落関数の和集合 69 が未確定 | #2288 (本 PR は部分達成・Refs) |
| `128f9e0` の未判定 12 site の IR 突合 (判定 0 件) | 同上 | #2288 |
| slot `0x11e0ab0` の値の出自 (§5-1) | 上記 24 site の判定根拠が立たない | #2288 (次 run) |
| 24 site の IR 側 store 値の対応付け (§7-4 の 1) | 判定 0 件 (脱落関数の和集合 69 は未確定) | #2288 (次 run) |
| V の実行時値の出所 (§7-4 の 2) | 24 site の判定根拠 | #2288 (次 run) |
| 機械語走査は RetDec 関数区間 (config) のみ (§7-1) | 区間外からの書き込みは未走査 | #2288 (次 run) |

## 7. 2 回目 run: 機械語側の再検証と V の出所 (LD-104 継続)

- 測定 commit: 463d8176 (`ld104_cell_origin.py` と `results/ld104_*.tsv` を追加した commit)。以後 `git diff 463d8176 HEAD -- tools/m11/ldfix` のコード差分は 0 (本 REPORT のみ)。
- 実行: `python3 tools/m11/ldfix/ld104_cell_origin.py` (約 3 秒) と `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (rc=0・所要 2m44s・7/7 完了・load average 0.99・`drops_510.tsv` / `spill178_1161.tsv` は results/ と cmp 一致)。
  - 1 回目の e2e は worktree に `work-liftdiff` を展開していなかったため step 5/7 が落ちた。展開後に 7 step を再実行し、上の値は再実行のもの。
- 素材: `oc_artifacts: work-m11 work-liftdiff`。`boot_final3.ll` の sha256 は `010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e` (前 run と一致)。

### 7-1 機械語側 (§2 の再検証)

- 24 site (`results/ld104_sites.tsv`) は全て `mov rA,[rip+X]` → `mov rax,[rax]` → 後続命令の型。cell の VA は 0x15e0ab0 (LVA **0x11e0ab0**) で 24 site 共通。
- cell K (0x11e0ab0) を指す rip 相対参照は RetDec 関数区間内で 72 件 (`results/ld104_cell_refs.tsv`)。書き込み (W)・RMW は 0 件。内訳は c589b0 27・128f9e0 27・10c7cd0 18。絶対アドレス表現 (immediate) は 0 件。
- c589b0・128f9e0 の各 27 件は、`mov rax,[rax]` で連鎖する 24 件と `mov rcx,[K]` の 3 件。連鎖 24 件のうち、直後が spill 宛 store (`[rbp+D]`) になるのは 12 件 (site)。残り 12 件は直後に spill 宛 store が無い (直後は `[rbp+D]` の読み出し、別 slot の読み出し、または `mov rdx,[rip+X]`)。
- cell の内容 V = 0x12b81b0 (LVA; VA 0x16b81b0)。`m11_image_gen.py` は .reloc が指す値だけを VA→LVA に直すため、K の内容は PE の DIR64 で初期化された値と推定される (.reloc 表そのものは image に無く未確認)。
- V の 8 byte は image 上で 0。しかし V は実行時に値が入る参照フィールドと読める。`0x418190` は `[rcx]` (rcx = V) の値を読み、非 nil なら V を 0 に戻して参照を減らす (解放の型)。V の address を渡すのは `c21d80` の `lea rcx,[rip+X]` の 1 件だけで、`c21d80` はカウンタと 0 判定で初回だけ `0x415c30`・`0x418190` を呼ぶ。V を指す rip 参照もこの `lea` 1 件のみ。image の 0 は実行時の値ではない。

### 7-2 IR 側 (前 run の確認の追認)

- `c589b0`・`128f9e0` の IR 本体には K (18746032) を読む load が 1 件もない。boot_final.ll・boot_final2.ll・boot_final3.ll・bf_c.ll・bf_x.ll・shimx_link の各版でも同じ。`10c7cd0` には 8 件 (`load ptr`) ある。
- V (19628464) の定数を含む IR 行は c589b0・128f9e0 の範囲外に 1 件 (`boot_final3.ll` 383162 行)。
- したがって 24 site の store 値は、IR で K → V → *V の連鎖を通らない。ただし、この事実だけでは TRUE_DROP の根拠にならない。store 先 `[rbp+D]` と IR の stack_var / reg2mem の対応を site 単位で立てていないため。

### 7-3 判定

- 本 run の判定: **0 site** (`candidate_verdicts_1161.jsonl` は変更なし)。
- 理由: 機械語側の出自は確定したが、IR 側の store 先との対応を 1 site も立てていない。根拠無しの判定は入れない。

### 7-4 次の一手

1. 24 site の `[rbp+D]` と IR の stack_var / reg2mem の対応を site 単位で立てる。入口は `results/ld92_machine_evidence.tsv` (後続の読み) と `results/ld104_sites.tsv`。
2. V の実行時値の出所を追う: `0x418190` と `c21d80` の呼び出し元で、V の参照フィールドに入る値 (object 参照) を確認する。
3. 1 と 2 が立った site から、`candidate_verdicts_1161.jsonl` と同じ形式で根拠行付きで入れる。

## 8. 3 回目 run: c589b0 の 12 site を到達不能と確定 (NO_CONSUMER)・128f9e0 は次 run (LD-104 継続)

- 測定の基点: origin/main `927cd651`。コード変更は `ld104_reach.py` と results (`ld104_reach.tsv`・`candidate_verdicts_1161.jsonl` の 12 行・`spill178_1161.tsv` の 12 行) の追加だけ。`git diff 927cd651 HEAD -- tools/m11/ldfix` でも同じ。
- 素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff`。`work-m11.tar.zst` / `work-liftdiff.tar.zst` を worktree のルートで展開 (内部パスが `tools/<area>/work/` のため 1 段移動は不要)。`boot_final3.ll` の sha256 は `010451add…` で前 run と一致。fl-win64 は未使用。
- 注意: §2〜§7 の集計 (未判定 120 / 確定 51 / 判定不能 7) は 463d8176 時点。main の現状 (927cd651) の `results/spill178_1161.tsv` は 未判定 65 / 確定 97 / 判定不能 16 だった (他 issue の判定が入っている)。以下の増減はこの基点からの差。

### 8-1 IR に 24 site が無い理由 (機械語の CFG で確認)

- c589b0 の IR は `dec_label_pc_c59201` (IR 391009 行) で、c59230 の store (`0x1104dd8`・機械語 `mov byte ptr [rip+..], al` と一致) の直後に `br label %dec_label_pc_c5d220`。機械語は c59236 〜 c5928e (内部分岐 c5924a・c59253・c5925c、store 2 本、c5928e `jne c5d220`) を経由するが、IR に c59236 〜 c5928e の命令は無い。
- 機械語の rip 相対参照のうち IR 関数本体に現れない LVA は c592b8 以降に集中する (`ld104_reach` 作業中の確認。K = `0x11e0ab0` の 27 件を含む)。
- 欠落した到達可能な store のうち、2 本は VA `0x1504dd9` (LVA `0x1104dd9`・`mov byte ptr [rip+0x8abb6f], al` c59264) と VA `0x1504dda` (LVA `0x1104dda`・`mov byte ptr [rip+0x8abb69], 1` c5926a)。**これは未検証の候補**: この 2 cell が後続で読まれるか、IR のどこかで別に表現されているかは未確認。読まれるなら silent miscompile の候補 (新規類型の候補・DEFECTS.md 未登録。PM 判断)。
- 24 site のうち c589b0 の 12 site は、枝刈り (§8-2) を入れると入口から到達できなくなる site。c592c2 は c592ae 系 (c59299 の配下) にある。

### 8-2 到達性 (`ld104_reach.py` → `results/ld104_reach.tsv`)

- 方法: 関数入口から jcc / jmp / call の後続を BFS (命令単位)。定数分岐の枝刈りは c589b0 だけ (`PRUNE_C589B0`): c5927c `je c59299`・c59283 `je c5a7b8` は取られず、c5928e `jne c5d220` は必ず取られる。
- 根拠 (枝刈りの前提): VA `0x1504dd4` (dword) を rip 相対で指す命令を config 関数区間の全 8227 関数から走査した結果、書込み **1 件** (c59182 `mov dword ptr [rip+..], 8`)、読み 4 件 (c591a9・c591d4・c59208・c59271)。絶対アドレス参照は 0 件。c59271 の読みは値 8 (image 初期値 0x7fffffff も同じ枝)。`sub eax,6/4/1` の後に 0 になるのは v=6・10・11 だけで、v=8 も 0x7fffffff も該当しない。
- 入口の predecessor: c59299 ← c5927c `je` のみ (fallthrough 無し)。c592a0 ← c59299 のみ。c5a7b8 ← c59283 `je` のみ。c59201 ← c591a0 `jne` のみ。

| fn | 機械語の命令数 (到達) | 枝刈り無し: site 到達 | 枝刈り後: site 到達 | 判定 |
|---|---|---|---|---|
| c589b0 | 3477 → 468 | 12 / 12 | 0 / 12 | 12 site とも到達不能 → NO_CONSUMER |
| 128f9e0 | 3681 → 3681 | 12 / 12 | 12 / 12 (枝刈り無し) | 到達可能。判定は未 (§8-3) |

### 8-3 判定

- c589b0 の 12 site (`c592c2` `c5a6b4` `c5a705` `c5a750` `c5a811` `c5bc03` `c5bc54` `c5bc9f` `c5bd1d` `c5d121` `c5d172` `c5d1bd`): **NO_CONSUMER**。根拠行は `candidate_verdicts_1161.jsonl` の 12 行 (`ld104_reach.tsv` と対応)。意味は「実行経路に消費者なし」(到達不能の死んだ store)。IR に無いのは到達不能の正しい省略であり、drop ではない。→ TRUE_DROP 0 件 (drops_510 の和集合 69 は不変)。
- 128f9e0 の 12 site: **未判定**。枝刈り無しでも到達する。IR に K (0x11e0ab0) の読みが無いことは §3 のとおりだが、site の到達経路で IR の block 欠落が起きているかは未確認。次 run の入口は §8-4。

### 8-4 次の一手 (後続に渡す)

1. 128f9e0 の 12 site: 到達経路 (BFS の親を記録) を取り、経路上の IR block の欠落 (§8-1 と同型の c5d220 型 `br` の有無) を site ごとに見る。判定は根拠行付きで入れる。
2. §8-1 の欠落 store 2 本 (LVA `0x1104dd9`・`0x1104dda`) の後続読みを確認する。読みが無ければ「死んだ store」、読みが有れば欠落の類型を DEFECTS.md 形式で起票 (PM 判断)。
3. §8-2 の枝刈りの前提 (間接書込み無し) は config 関数区間の走査で確認した範囲。区間外のコードは未走査。

### 8-4 未解決 (本 run 時点)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 128f9e0 の 12 site の判定 (到達可能・IR 側の経路未確定) | spill 宛の脱落関数の和集合 69 の残り | #2288 (次 run) |
| §8-1 の欠落 store 2 本 (LVA `0x1104dd9`・`0x1104dda`) の後続読み | 新規類型の候補の確定 | #2288 (次 run) |
| 枝刈りの前提 (config 区間外・間接書込み) | c589b0 の NO_CONSUMER の完全性 | #2288 (次 run) |

### 8-5 検証

- `python3 tools/m11/ldfix/ld104_reach.py` → rc=0・1.2 s (CPU 1 core・load average 0.94)。
- `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (`RUNNER_TEMP=<作業用一時ディレクトリ>`): 2m44s・load average 0.94 で 1〜6/7 は完走。7/7 の `cmp` は 12 行差分 (c589b0 の 12 site: 未判定 → 確定) で rc=1 になった。差分は想定どおり (`diff` で 12 行のみ)。`results/spill178_1161.tsv` を新出力で置換し、`cmp` は OK。`drops_510.tsv` は cmp OK (脱落関数の和集合 69 不変)。
- 集計 (7/7 の出力): 確定 109 / 判定不能 16 / 未判定 53 (基点 927cd651 は 確定 97 / 判定不能 16 / 未判定 65)。
