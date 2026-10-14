# REPORT #2288 — spill 宛 未判定 `c589b0`・`128f9e0` 24 site の IR 側突合 (LD-104)

親: #2266 (LD-99) / #2244 (LD-92) / #1161 (LD-35)。本 run は判定を 1 件も入れず、機械語側の入口と IR 側の不一致を残した。

## 1. 測定

- 測定 commit: e53d845b (run 開始時の origin/main)。以後コード差分は 0 (`git diff e53d845b HEAD -- tools/m11/ldfix` が空)。
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (rc=0・所要 1m53s・7/7 完了・load average 0.42)
- 結果: `spill178_1161.tsv` と `drops_510.tsv` は results/ と一致 (cmp OK)。
- 集計 (step 7/7): spill 宛 unk site 178 / 71 関数。status 未判定 120 / 確定 51 / 判定不能 7。脱落関数の和集合 69 (変更無し)。
- 素材: `work-m11` は `tools/m11/work/`、`work-liftdiff` は `tools/liftdiff/work/` に展開 (tarball 内が `tools/m11/work/...` の相対パスのため、展開後に 1 段移動した)。

## 2. 機械語側の確認 (24 site)

- 対象 24 site は `spill178_1161.tsv` の status=未判定 (`c589b0` 12 / `128f9e0` 12) と一致。
- 全 24 site で、store 元 (`mov qword ptr [rbp+X], rax`) の直前に `mov rax,[rip+X]` → `mov rax,[rax]` (二段参照) があり、一段目の参照先が **LVA `0x11e0ab0` (10 進 18746032)** である。
- 同 slot は両関数の機械語から計 27 回参照される (`c589b0`・`128f9e0` とも rip 参照 44 セルのうち最多)。

## 3. IR 側の確認 (不一致)

- IR 本体は `function_c589b0` (390809〜391214) と `function_128f9e0` (76541〜77198) で、issue 記載と一致。
- **両関数の IR に、slot `0x11e0ab0` (定数 `18746032`) を読む命令は 1 件もない** (IR_refs=0)。
- `boot_final3.ll` 全体でも `18746032` は 8 件で、いずれも別関数 (`cf3790` 側などの inttoptr load)。
- 一方、既判定の TRUE_DROP 候補 `c5d2df`・`c5d343` が読む定数は `18751296` (LVA `0x11e1f40`) で、`0x11e0ab0` とは別セル。
- REPORT_2266 の「slot `0x11e0ab0` の 1 段 deref」という記述は、IR 側では確認できない。IR に読みが無いため、「deref が落ちている」か「値が別経路で作られる」かを site ごとに区別できない。

## 4. 判定の結果

- 本 run で確定させた判定: **0 site**。`candidate_verdicts_1161.jsonl` は変更なし。
- 理由: 24 site の判定根拠 (IR の store→load 対応) を IR 側で立てられなかった。IR に当該 slot の読みが無いため、TRUE_DROP / OK_LOAD / NO_CONSUMER のどれを付けても根拠にならない。根拠の無い判定は脱落集合を誤って確定させる。

## 5. 次の一手 (後続に渡す)

1. slot `0x11e0ab0` の値の出自を機械語側で確定する: 2 関数の外 (呼び出し元・初期化箇所) で書かれるか、グローバル初期値 (image 実データ) かを `m11_image.bin` の 0x11e0ab0 の内容から確認する。
2. その結果で IR 側の扱いを決める: IR が slot を一切読まない場合、24 site の store 元は IR の別経路 (`function_X__lifted` や inline 展開) を経ている可能性があり、関数の IR 本体の取り違えを先に確認する。
3. 判定は 1 と 2 の後に、site 単位で `candidate_verdicts_1161.jsonl` と同じ形式で入れる。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `c589b0` の未判定 12 site の IR 突合 (判定 0 件) | spill 宛の脱落関数の和集合 69 が未確定 | #2288 (本 PR は部分達成・Refs) |
| `128f9e0` の未判定 12 site の IR 突合 (判定 0 件) | 同上 | #2288 |
| slot `0x11e0ab0` の値の出自 (§5-1) | 上記 24 site の判定根拠が立たない | #2288 (次 run) |
