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

## 8. 3 回目 run: c589b0 の 12 site を到達不能と確定 (NO_CONSUMER)・128f9e0 は子 issue #2679 へ (LD-104 継続)

- 測定の基点: origin/main `927cd651`。測定 commit (コードを変えた最後の commit): `ee237f22` (`ld104_reach.py` の到達探索の上限を config endAddr にし、(d) の測定を追加。前版は `c00fa9f3`)。`git diff ee237f22 HEAD -- tools/m11/ldfix` は本 REPORT (`REPORT_2288.md`) だけ。コードと結果 TSV の差分は 0。
- 素材: `work-m11` を `M11_WORK=<主 checkout>/tools/m11/work` で読み取り専用に参照 (worktree には展開していない)。fl-win64 は未使用。

### 8-1 IR 側の欠落 (事実)

- c589b0 の IR は `dec_label_pc_c59201` (IR 391009 行) で、c59230 の store の直後に `br label %dec_label_pc_c5d220`。機械語は c59236〜c5928e (内部分岐 c5924a・c59253・c5925c、store 2 本、c5928e `jne c5d220`) を経由するが、IR に c59236〜c5928e の block は無い (`dec_label_pc_c59236`・`c5928e`・`c59299`・`c5a7e8` の label が無く、`c5d220` の preds に `c591cd` と `c59201` が直接入る)。
- この IR 欠落は 12 site の判定根拠ではない。12 site が届かないのは機械語の定数分岐による (§8-2・§8-3)。IR に無いことを根拠にしない。
- 欠落した到達可能な store 2 本: c59264 (VA 0x1504dd9 = LVA 0x1104dd9, `mov byte ptr [rip+..], al`) と c5926a (VA 0x1504dda = LVA 0x1104dda, `mov byte ptr [rip+..], 1`)。どちらも入口から c59271 より前に到達する (枝刈りに依らない)。config 関数内の rip 参照は、0x1504dd9 が c59264 の書込み 1 件のみ、0x1504dda が c5926a の書込み 1 件と c59255 の読み 1 件 (同じ欠落 block 内) (`results/ld104_checks.txt`)。

### 8-2 到達性 (枝刈りは c59271 の読み値 v から算出)

- c59271 `mov eax,[FLAG]` の後、eax は v-6 (c5927c `je c59299`)・v-10 (c59283 `je c5a7b8`)・v-11 (c5928e `jne c5d220`) で判定される。枝刈り (`prune_for_v`) は v から機械的に決める。v=8 は §8-3 (a) で確定する。
- 到達探索の上限は config の endAddr (c589b0: `c5d649`・128f9e0: `1294ab8`)。前版の固定 0x8000 を廃止した。site の到達は前版と変わらず (`ld104_reach.tsv` は cmp 一致)。c589b0 の CFG 到達命令数は枝刈り無し 3477→3470・枝刈り後 468→461 (endAddr 外へ出る 7 命令を除外)。
- 結果 (`results/ld104_checks.txt` から転記。12 site = c589b0 の site 数):

| 読み値 v / 枝刈り | 到達 site |
|---|---|
| 枝刈り無し | 12/12 |
| NC: c5927c の不成立枝 (fall) のみ枝刈り | 4/12 (c592c2 c5a6b4 c5a705 c5a750) |
| v=6 (c5927c 成立) | 4/12 (同上) |
| **v=8 (c59182 の書込み値)** | **0/12** |
| v=10 (c59283 成立) | 0/12 |
| v=11 (c5928e 不成立 → c59294) | 8/12 (c5a811 c5bc03 c5bc54 c5bc9f c5bd1d c5d121 c5d172 c5d1bd) |
| v=0x7fffffff (image 初期値) | 0/12 |

- 行ごとの経路: c592c2・c5a6b4・c5a705・c5a750 は c5927c `je c59299` の成立枝 (v=6) 配下。残り 8 site は c5928e `jne c5d220` の不成立枝 (fall; v=11) → c59294 `jmp c5a7e8` 配下。両群とも v=8 では届かない。
- 到達 (`results/ld104_reach.tsv`): c589b0 は枝刈り無し 12/12 → 枝刈り後 0/12。128f9e0 は 12/12 → 12/12 (枝刈りなし)。

### 8-3 v=8 の確定 (支配・書込み・外部分岐の測定)

- (a) 支配: 入口から c59271 は到達する (Y)。c59182 を除くと c59271 は到達しない (N)。c5918c も同様 (Y → N)。
- (b) c5918c〜c59271 の call: 0 件 (線形逆アセンブル)。
- (c) config 関数 8227 本 (`boot*.drc.config.json`・開始番地で統合) の全命令で、c5918c〜c59277 の外から内への直接分岐・call は 0 件 (直接分岐・call 61325 件を走査)。
- (d) 外から c589b0 本体 (c589b0〜c5d649) への直接分岐・call: 入口 c589b0 への呼出しが 1 件 (`125338d` の call・呼出し元は config 関数 1253260〜1253517)、入口以外の本体への分岐・call は 0 件。入口への呼出しは通常の呼出しで、(a) は入口を起点に測っているため結論は変わらない。間接分岐・call (config 内 4250 件) は範囲外。
- FLAG (VA 0x1504dd4) を rip 相対で指す命令 (config 全関数): 書込み 1 件 (c59182 `mov dword ptr [rip+..], 8`)、読み 4 件 (c591a9・c591d4・c59208・c59271)、アドレス取得 (lea) 0 件。
- 結論: c59271 が読む値は、そこへ至るどの経路でも c59182 の書込み値 8 である (c59182 が必ず先行し、その間に書込みも call も無い)。

範囲外 (未走査。判定はこの範囲に限る): config 外の image (`boot*.drc.config.json` の関数区間外)、間接分岐・間接 call (config 内 4250 件) による入口、FLAG のアドレスを値として持つ data 表経由の書込み。

### 8-4 判定

- c589b0 の 12 site: **NO_CONSUMER** (機械語で到達不能)。根拠 12 行は `results/candidate_verdicts_1161.jsonl` (経路を行ごとに記載)。TRUE_DROP 0 件 (drops_510 の和集合 69 は不変)。
- 128f9e0 の 12 site: 未判定のまま。子 issue #2679 (LD-120) に移した。

### 8-5 検証

- `M11_WORK=<主 checkout>/tools/m11/work python3 tools/m11/ldfix/ld104_reach.py`: 測定 commit `ee237f22` で rc=0。出力 `results/ld104_reach.tsv`・`results/ld104_checks.txt` と cmp 一致。
- 負の対照: v=6 の枝刈りで 4/12 が届き、v=8 で 0/12 になる (分岐の判定 1 件で到達が変わる)。
- e2e (`audit_lsf_ssa_e2e.sh`): 測定 commit `ee237f22` (HEAD 上で実行) で再実行。`RUNNER_TEMP=/home/runner/work/_temp`・`M11_WORK`・`LD_WORK` は主 checkout に展開済みの `tools/m11/work`・`tools/liftdiff/work` を読み取りだけに使った。rc=0・2m31s・7/7 完了・終了直後の 1 分 load average 0.83。`drops_510.tsv` と `spill178_1161.tsv` は `results/` と cmp 一致 (差分 0)。集計 (7/7): 確定 109 / 判定不能 16 / 未判定 53、脱落関数の和集合 69。
- spill178 の c589b0 の 12 行 (未判定 → 確定) は `c7f36256` の e2e で `results/` に反映済み (rc=1 → 新出力で置換 → cmp OK)。`candidate_verdicts_1161.jsonl` は `c7f36256` と HEAD の比較で evidence 文 (12 行) だけが変わり、evidence 以外の差分は 0 (verdict・status は不変)。
- e2e の 7 step は `ld104_reach.py` を呼ばない。

### 8-6 新類型候補 (DEFECTS.md 形式の行案・PM 判断)

| 候補 | 層 | 新旧 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|---|
| D?? (PM 採番) | fe | 新規候補 | 到達可能な条件分岐の block (store 2 本を含む) が IR から欠落し、直前の分岐が後続へ直接 `br` で飛ぶ (silent) | 未特定 (機械語 c59236〜c5928e の lift 出力が欠落) | c589b0: IR に `dec_label_pc_c59236`・`c5928e` が無い。落ちる store は 0x1104dd9・0x1104dda (§8-1) | 機械語の到達 block に対応する `dec_label_pc_<VA>` が IR に無い (c589b0 で 4 label) | 未定 |

PM agent の判断待ち: この欠落類型を `docs/DEFECTS.md` に登録し、原因特定 (c59236〜c5928e の lift 出力) を起票するか。既定案: 登録し、原因特定を子 issue として起票する (本 PR では起票しない)。

### 8-7 未解決 (本 run 時点)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 128f9e0 の 12 site の判定 (到達可能・IR 側の経路未確定) | spill 宛の脱落関数の和集合 69 の残り | #2679 (子・LD-120) |
| 欠落 store 2 本の類型 (§8-6) の登録と原因特定 | 新類型候補の確定 | PM agent の判断待ち (既定案: 登録し原因特定を子 issue) |
