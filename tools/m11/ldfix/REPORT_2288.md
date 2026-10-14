# REPORT #2288 — spill 宛 未判定 `c589b0`・`128f9e0` 24 site の IR 側突合 (LD-104)

親: #2266 (LD-99) / #2244 (LD-92) / #1161 (LD-35)。本 run は判定を 1 件も入れず、機械語側の入口と IR 側の不一致を残した。

## 1. 測定

- 測定 commit: e53d845b (run 開始時の origin/main)。以後コード差分は 0 (`git diff e53d845b HEAD -- tools/m11/ldfix` が空)。
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (rc=0・所要 1m53s・7/7 完了・load average 0.42)
- 結果: `spill178_1161.tsv` と `drops_510.tsv` は results/ と一致 (cmp OK)。
- 集計 (step 7/7): spill 宛 unk site 178 / 71 関数。status 未判定 120 / 確定 51 / 判定不能 7。脱落関数の和集合 69 (変更無し)。
- 素材: `work-m11` は `tools/m11/work/`、`work-liftdiff` は `tools/liftdiff/work/` に展開 (tarball 内が `tools/m11/work/...` の相対パスのため、展開後に 1 段移動した)。
- 再現用の素材名: `oc_artifacts: fl-win64 work-m11` (`work-liftdiff` は `audit_lsf_ssa_e2e.sh` の 4/7・5/7 で使うため併せて指定する場合は `work-liftdiff` を足す)。

## 2. 機械語側の主張 (未再現・未確認)

- 対象 24 site は `spill178_1161.tsv` の status=未判定 (`c589b0` 12 / `128f9e0` 12) と一致 (§1 の集計で確認)。
- 以下は**未再現・未確認の主張**として扱う。当時の逆アセンブル出力・走査スクリプトは残っておらず、本 run でも fl-win64 の逆アセンブルは行っていない。
  - 全 24 site で、store 元 (`mov qword ptr [rbp+X], rax`) の直前に `mov rax,[rip+X]` → `mov rax,[rax]` (二段参照) があり、一段目の参照先が LVA `0x11e0ab0` (10 進 18746032) である。
  - 同 slot は両関数の機械語から計 27 回参照される。
- 再検証は §3-a の手順 3 (fl-win64 の逆アセンブル走査・生成元を `results/` に残す) で行う。

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
- **§2 (機械語側) は未再現**。当時の逆アセンブル出力・生成元スクリプトは記録が無く、本 run では検証していない。「二段参照 24 site」「計 27 回」は未確認の主張。
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

1. slot `0x11e0ab0` の値の出自を機械語側で確定する: 2 関数の外 (呼び出し元・初期化箇所) で書かれるか、グローバル初期値 (image 実データ) かを `m11_image.bin` の 0x11e0ab0 の内容から確認する。
2. その結果で IR 側の扱いを決める: IR が slot を一切読まない場合、24 site の store 元は IR の別経路 (`function_X__lifted` や inline 展開) を経ている可能性があり、関数の IR 本体の取り違えを先に確認する。
3. 判定は 1 と 2 の後に、site 単位で `candidate_verdicts_1161.jsonl` と同じ形式で入れる。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `c589b0` の未判定 12 site の IR 突合 (判定 0 件) | spill 宛の脱落関数の和集合 69 が未確定 | #2288 (本 PR は部分達成・Refs) |
| `128f9e0` の未判定 12 site の IR 突合 (判定 0 件) | 同上 | #2288 |
| slot `0x11e0ab0` の値の出自 (§5-1) | 上記 24 site の判定根拠が立たない | #2288 (次 run) |
| §2 (機械語側: 二段参照 24 site・計 27 回) が未再現 | 機械語側の入口が未確定。§3-a 手順 3 で再検証する | #2288 (次 run) |
