# REPORT #3753 — spill 宛 UNDETERMINED 5 site のうち 4 site を IR と機械語のブロック単位で確定 (LD-175)

既知類型との関係: D17 (`docs/DEFECTS.md`)。rip 相対セルの値 (ポインタ) を読んでから deref する 2 段の読みが、IR では
セルの 1 段読み (`load i32 @cell`) に潰れている。

親: #2253 (LD-95)。本 issue は #2253 の子 B。範囲は #2253 本文の 5 site (128d495・1284dab・dcdeee・c3460e・12900c4)。
1284dab は判定できなかったため、子 #3793 (`[LD-178]`) に移した (範囲縮小: AGENTS.md 規約 11)。

## 1. 結論 (実測)

- 4 site を TRUE_DROP に確定: **128d495・dcdeee・c3460e・12900c4**。1284dab は UNDETERMINED のまま (子 #3793)。
- `results/candidate_verdicts_1161.jsonl` の変更は 5 行のみ (4 行を TRUE_DROP、1 行 (1284dab) は根拠文だけ更新)。他の 113 行は変えていない (`git diff` で確認)。
- `results/spill178_1161.tsv` (spill 宛 178 site の分類表) の状態件数 (第 5 列):

| 状態 | 変更前 (bb6bdcf41) | 変更後 (91d5c5ca4) |
|---|--:|--:|
| 確定 | 148 | **152** (+4) |
| 判定不能 | 29 | **25** (-4) |
| 未判定 | 1 | 1 |

  変わったのは上記 4 行のみ (`diff` で確認。1284dab の行は UNDETERMINED のまま)。

## 2. 測定条件

- 測定 commit: `91d5c5ca4` (`fix(m11): resolve 4 spill UNDETERMINED sites by machine-IR block link (#3753)`)。コードと結果を変えた最後の commit。
  以後の commit は本 REPORT と `docs/DOC_MAP.md` のみ。
- 差分 0 の証跡 (本 REPORT を書いた時点の HEAD で実行): `git diff 91d5c5ca4 HEAD -- tools/m11/ldfix` の出力は空 (§7)。
- 素材: `work-m11` と `work-liftdiff` を `tar --zstd -xf` で展開 (gitignore 対象の `tools/m11/work/`・`tools/liftdiff/work/`)。
  判定は `m11_image.bin`・`boot_final3.ll`・`boot*.drc.config.json` だけを使う。fl-win64 (PE) は使わない。
- 測定実行: worktree `ws-3753` (branch `3753-ld175-spill-sites`) の HEAD で `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` を前景で 1 回。
  `M11_WORK`・`LD_WORK` は主 worktree の展開先を指す。`TMPDIR=$RUNNER_TEMP`。

## 3. 判定の根拠 (site ごと)

機械語 (capstone 正本) の `[rip+X]` の参照先セル K = X − 0x400000 (IR の絶対アドレス)。
IR は `boot_final3.ll` の行番号 (1 始まり)。消費ブロックは直前の `dec_label_pc_<VA>` で対応づけた。

| 関数 | site | 機械語 (2 段 deref・セル内容) | IR の 1 段読み (行・ブロック) | 機械語の消費ブロック → IR の対応 | 判定 |
|---|---|---|---|---|---|
| 128c320 | 128d495 | 128d48c `mov rax,[rip+0x35733d]`→128d493 `mov eax,[rax]`→128d495 `mov [rbp+0x5c],eax`。セル 0x15e47d0 の内容 0x153fb24 (ポインタ) | 75414 `%713 = load i32 @18761680` (blk 128d48c)→75419 `store` → `storemerge25.reg2mem`→75481 reload (blk 128d539) | 消費 128d73c・128d896・128d990・128db40 (blk 128d6d9・128d799・128d920・128dad4) = IR の reload の使用ブロックと一致。別経路 128d4ce〜128d4d9 も同セルを 2 段 (`mov rcx,[rip+0x3572fb]`→`mov ecx,[rcx]`) で読み、IR 75442 `%731 = load i32 @18761680` (1 段) を使う | **TRUE_DROP** |
| dcdde0 | dcdeee | dcdee5 `mov rax,[rip+0x815664]`→dcdeec `mov eax,[rax]`→dcdeee `mov [rbp+0x58],eax`。セル 0x15e3550 の内容 0x156ec54 (ポインタ) | 420357 `%45 = load i32 @18756944` (blk dcdee5) | 機械語 dcdf24 `sub [rbp+0x58],eax`→dcdf40 `ecx=[rbp+0x58]`→call 1311e70 = IR 420378 `%65 = sub %45,%64`→420383 `zext %65`→`function_1311e70`。後続の dcdfc8・dcdfe0 (blk dcdfa8) = IR 420449 `sub`・420461 `add` (%65 の派生値、blk dcdfa8) | **TRUE_DROP** |
| c343f0 | c3460e | c34605 `mov rax,[rip+0x9afd2c]`→c3460c `mov eax,[rax]`→c3460e `mov [rbp+0xa4],eax`。セル 0x15e4338 の内容 0x12bca00 (ポインタ) | 383953 `%100 = load i32 @18760504` (blk c345c4)。同ブロックに 383950 `%98 = load ptr` (store 先のポインタとして正しく使用) | 機械語 c34614 `mov ebx,[rbp+0xa4]; shl ebx,2; call 0x409410` = IR 383954 `%101 = mul %100,4`→`function_409410`。機械語 c346fc `mov edx,[rbp+0xa4]; lea r8,[..]; call 0x7769e0` = IR 383996 `%__m11c_3446 = zext %100` (第 2 引数)。機械語 c3464e (間接 call の引数) は IR 383970 `%113 = load i32` (同ブロック、cvtsi2sd 383971) と同ブロック。行単位の対応は未確定 | **TRUE_DROP** |
| 128f9e0 | 12900c4 | 12900bb `mov rax,[rip+0x3525de]`→12900c2 `mov eax,[rax]`→12900c4 `mov [rbp+0x59c],eax`。セル 0x15e26a0 の内容 0x153fa10 (ポインタ) | 76650 `%8 = load i32 @18753184` (blk 12900bb) | 機械語 12902d6 `mov ecx,[rbp+0x59c]; mov edx,0x1a; call 0x128ade0` = IR 76806 `%106 = zext %8`→76809 `call function_128ade0(%106,i64 26,…)`。機械語 12902f0・1290308 の `cmp ecx,[rax]` = IR 76811 `%111 = icmp eq %8,%110` (blk 129028d) | **TRUE_DROP** |
| 1280530 | 1284dab | 1284da2 `mov rax,[rip+0x35d39f]`→1284da9 `mov eax,[rax]`→1284dab `mov [rbp+0xc8],eax`。セル 0x15e2148 の内容 0x153fb20 (ポインタ) | 71086 `%3213 = load i32 @18751816` (blk 1284d72) | 消費 1284ea6・1284fb3 は IR 71145・71189 と対応。**消費 1284dc1 (1284dcf・1284ddf) は対応なし**: IR のブロック 1284dc1 は %3213 を使わず、`*(%.pre300)+148` (71097-71104 の %3224 − %3227) から読む。残り 12857c8・1285907・1285a0a・1285dba・1285e8e も対応なし | **UNDETERMINED** (子 #3793) |

判定の要点: 機械語は 2 段 (セル → ポインタ → 値)、IR は 1 段 (セルの内容 = ポインタの下位 32 bit を読む)。
4 site とも、機械語の消費ブロックが IR で同じ 1 段の値を使うブロックと一致した。
1284dab は消費ブロックの一部が IR に無いため、判定しなかった。

## 4. 検証

- e2e (測定 commit `91d5c5ca4`・前景 1 回): `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` → **rc 0**・**real 180 s**・load average (uptime 1 分) 0.91 (開始) → 1.01 (終了)。
  7/7 `spill_classify_1161.py` の出力が `results/spill178_1161.tsv` と一致 (`cmp`)、8/8 (LD-143 修復後 IR の再生成) も一致。
  同 e2e の `negctl_510.sh` (NC0〜NC7) は全て出力し、`FAIL` は 0 件 (`grep -c FAIL` = 0)。
  参考: 同じ内容 (`91d5c5ca4` の内容) を主 worktree で先に 1 回実行 (rc 0・real 179 s)。
- 突合スクリプト: `python3 tools/m11/ldfix/ld175_site_link.py` (約 2.5 s・素材は work-m11 のみ)。
  出力の要約 (測定 commit):
  - 128d495 / dcdeee / c3460e / 12900c4: `機械語 2 段=True / 機械語の消費ブロックが IR に無い: なし -> TRUE_DROP 候補`
  - 1284dab: `機械語の消費ブロックが IR に無い: 1284dc1 12857c8 1285907 1285a0a 1285dba 1285e8e -> UNDETERMINED`
- ネガティブコントロール: 判定式は 4 site を TRUE_DROP 候補にする一方、1284dab は消費 6 ブロックの欠落で UNDETERMINED になる
  (判定式が常に TRUE_DROP を返すわけではないことの確認)。

## 5. 限界と注意

- 突合は**ブロック単位**。行単位の対応は、機械語 c3464e (間接 call) と IR 383970 `%113` の関係で未確定。
  判定の根拠は「機械語 2 段 × IR 1 段 × 消費ブロックの一致」で、c3464e 単独では根拠にしていない。
- `ld175_site_link.py` の IR 側は forward slice (演算・ext・reg2mem を 4 段まで) の使用ブロックで、過大に数える。
  包含の成立だけを根拠にせず、§3 の行を目視で突き合わせた (dcdeee の dcdfa8 は %65 派生の使用ブロックとして確認)。
- 判定外の観察 (別 site として判定が必要。子 #3793 の本文に記載):
  (a) dcdeee: 機械語 dcdf1b `mov rax,[rip+0x81562e]`→dcdf22 `mov eax,[rax]`→dcdf24 `sub [rbp+0x58],eax` の減数は、別セル 0x81562e の 2 段 deref。
  IR 420378 の減数 %64 は site と同じセル (1 段) を読む。
  (b) 12900c4: 機械語 12902f0・1290308 の比較の右辺は同セル 0x15e26a0 の 2 段 deref。IR 76811 の %110 は 1 段。
  (c) 同じセル 0x15e26a0 の別の 2 段読み (12902b7 `mov rcx,[rip+0x3523e2]`→12902be `movsxd rcx,[rcx]`) は IR 76801 `%101` (1 段) に対応する。本 site の判定外。

## 6. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
python3 tools/m11/ldfix/ld175_site_link.py        # §3 の根拠の表示 (1 コマンド)
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh         # 7/7・8/8 の TSV 一致を含む e2e
```

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1284dab の判定 (消費 6 ブロックの IR 対応が取れない。1284dc1 は IR の構造体フィールド `*(%.pre300)+148` から読む) | spill 宛 UNDETERMINED 1 site (`candidate_verdicts_1161.jsonl`) | 子 #3793 (`[LD-178]`) |
| 判定外の観察 (a) dcdeee の減数の別セル・(b) 12900c4 の比較右辺の 1 段読み・(c) 12902b7 系の別読み | 別 site の判定対象 (TRUE_DROP 候補の追加) | 子 #3793 の本文 (判定外の観察) |

## 8. 差分 0 の証跡

本 REPORT の測定 commit からの差分 (コード・結果の範囲):

```
$ git diff 91d5c5ca4 HEAD -- 'tools/m11/ldfix/*.py' 'tools/m11/ldfix/*.sh' tools/m11/ldfix/results | wc -l
0
```

測定 commit から HEAD までの変更ファイルは `docs/DOC_MAP.md` (REPORT 索引の 1 行) と本 REPORT の 2 つだけ
(`git diff --name-only 91d5c5ca4 HEAD`)。
