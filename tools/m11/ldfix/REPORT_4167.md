# REPORT_4167 — FRAME_IN_ESCAPED 漏出 store の別名判定: 694c80・c3b340 (#4167 / 親 #3225 子 B)

## 1. 測定条件

- 測定 commit: `64eea9eac` (main 取り込み後の HEAD。判定器のコードは `origin/main` と同一)。store 基底の出どころを機械語から出す `alias_evidence_4167.py` と結果 `results/alias_evidence_4167.json` は `fbd89e0d7` で作り、`64eea9eac` で再実行して byte 一致を確認した。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211 と同じ)。PE は fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`)。素材は fl-win64 (`docs/REFERENCES.md` `[WIN64]` の展開物。`tar --zstd -xf` で `extracted/block00031_PE.bin` だけ展開。2.3 秒)。
- 判定器の現 HEAD 値: `DROP 3・LIVE-IN 1・UNDETERMINED 44` (関数)、`DROP 3・LIVE-IN 1・UNDETERMINED 46・PTR_READ 1` (site)。判定器の実行は 0.23 秒 (`real 0m0.230s`)。
- #2211 の値 (`DROP 3・LIVE-IN 35・UNDETERMINED 10` / `LIVE-IN 36・UNDETERMINED 11・PTR_READ 1`) とは一致しない。差は main #4090 の判定器変更 (`frame_derived` が lea を F に入れる・`leak_sites` が複数化) による。判定 JSON は `results/frame_store_verdict_4090.json` と byte 一致する。

## 2. 対象 site の機械語の根拠 (受入 1)

store 基底の値の出どころを `alias_evidence_4167.py` で機械的に追った (`results/alias_evidence_4167.json`)。

| 関数 | 打ち切り store (機械語) | 基底 | 基底の直前の定義 | その slot への書き | slot への他の参照 |
|---|---|---|---|---|---|
| 694c80 | `695163 mov qword ptr [rax + 0x94], rcx` | rax | `695155 mov rax, [rbp+0xe0]` | `[rbp+0xe0]` への書きは `694c98 mov [rbp+0xe0], rcx` の 1 回だけ | 20 箇所 (読みのみ) |
| c3b340 | `c3b3f5 mov byte ptr [rcx + 0x20], al` | rcx | `c3b3ee mov rcx, [rbp+0xc0]` | `[rbp+0xc0]` への書きは 3 回: `c3b368 mov [rbp+0xc0], rcx` (入口引数)・`c3b399` (call 410320 の戻り値)・`c3b597` (call 410360 の戻り値) | 17 箇所 (読みと `cmp`) |

- 694c80: `[rbp+0xe0]` の値は入口引数 rcx。入口から `694c98` までに rcx は書かれない。`695163` の store 先は入口引数が指す先。
- c3b340: `[rbp+0xc0]` の値は入口引数 rcx か、入口引数を渡した call (410320・410360) の戻り値。

## 3. 判定 (受入 2)

判定器の結果 (測定 commit `64eea9eac`)。#2211 版からの差は、main #4090 による `frame_derived` の変更 (lea を F に入れる) で、c3b340 の `c3b3f5` の barrier が LEAK_STORE から ALIAS_FRAME_PTR に変わったこと。

| 関数 | 判定器の結果 (`64eea9eac`) | 打ち切り | 判定 |
|---|---|---|---|
| 694c80 | UNDETERMINED (BARRIER(LEAK_STORE)) | `695163` (LEAK_STORE) | 未判定のまま |
| c3b340 | UNDETERMINED (BARRIER(ALIAS_FRAME_PTR)) | `c3b3f5` (ALIAS_FRAME_PTR。#2211 版では LEAK_STORE) | 未判定のまま |

- ネガティブコントロール (受入 4): 現 HEAD の `--negctl-glk` (全関数の漏出を強制 True) は、関数判定・site 判定とも通常実行と**同一** (関数 `DROP 3・LIVE-IN 1・UNDETERMINED 44`、site 51 件の判定が全て一致)。判定を変えないので、判定器が漏出規則に依存していることの確認にはならない。`--negctl-nosync` も関数判定は同一で、site 判定のみ 8 件が変わる。#2211 の「壊す 1 と一致」は現 HEAD では成り立たないため削除する。ネガコンとして判定を変えるのは `--negctl-nosync` のみ。

## 4. 残る理由 (DROP / LIVE-IN にできない理由)

- 694c80 の `695163` の store 先は入口引数 (`[rbp+0xe0]`) の指す先。入口引数の値そのものは frame の address ではないので、この store が直接 frame を書く根拠は機械語からは出ていない。ただし frame の address は同じ関数内で `lea rcx, [rbp+0x68]` (694d35) などにより call 引数へ渡される。渡された先の関数が引数の指す memory を経由して frame を書く経路の有無は、判定器が見ていない (#3228 の範囲)。この経路の有無は本 REPORT では確かめていない。
- c3b340 の `c3b3f5` は、`[rbp+0xc0]` が call 戻り値を含むため、戻り値の provenance を見る必要がある。これも call 越えの解析で、#3228 の範囲。
- 以上より、判定器の範囲 (call を越えない) では 2 site とも確定しない。これは #2211 REPORT §4 の子 #3225 (store の別名判定) と #3228 (call 越え) の残件そのもの。

## 5. 差分 (WORKFLOW §6)

- 測定 commit: `64eea9eac` (判定器・結果 JSON・ネガコンの実行はこの commit で行った)。
- `git diff fbd89e0d7 64eea9eac -- tools/m11/ldfix` は 12 ファイル・5059 行の追加・24 行の削除 (うち判定器 `audit_frame_store_alias_2211.py` は 14 行追加・10 行削除)。これは main 取り込み (#4090 ほか) による差分で、本 PR の変更ではない。本 PR で判定器は変えていない。
- 本 PR の追加は `REPORT_4167.md` (51 行)・`alias_evidence_4167.py` (103 行)・`results/alias_evidence_4167.json` (95 行) の 3 ファイル・249 行の追加のみ。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼び出し先が caller の frame を書く経路 (leaked frame address 経由) | 694c80 の `[rbp+0xe0]` の値の確定。site 695163 が LIVE-IN / DROP にならない | #3228 [LD-151] |
| c3b340 の `[rbp+0xc0]` の call 戻り値の provenance | c3b3f5 の判定 | #3228 [LD-151] |
| 判定器の provenance 規則 (入口引数を保存した slot の値は frame 別名にならない) の実装 | 694c80 の `695163`・c3b340 の `c3b3f5` の LEAK_STORE を外す | #3225 [LD-150] |
