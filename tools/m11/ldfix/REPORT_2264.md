# REPORT #2264 — spill 宛 未判定 関数群 C 前半 (19 関数・23 site) の消費者分類 (LD-97)

親: #2246 (LD-94) / 上位: #1161 (LD-35)。測定では判定を 0 件確定させた。残りの分類は未解決として残す。

## 1. 測定の前提

- 測定 commit: `25d2cdc0` (origin/main 取得時点)。e2e はこの commit の tree で実行した。以降の HEAD との差分は測定後に追加した REPORT のみ (§7)。
- 素材: work-m11 / work-liftdiff を `tools/m11/work/`・`tools/liftdiff/work/` に展開 (`tar --zstd -xf`, 8 秒)。fl-win64 は `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` を機械語の PE 正本として使用。
- 既知類型との関係: 該当 ID なし (`docs/DEFECTS.md` D1a〜D22 を全件確認。新類型は観測していない。LD-35・LD-94 の spill 宛 unk 分類の延長)。
- e2e 実測: 前回 run (測定 commit `25d2cdc0` の tree で実施) の実測。本 fix では再実行していない。`bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` を 1 回実行 → rc=0・所要 1m58s (user 1m57s)・load average 0.91 (実行後の uptime)・7/7 完了。`[1]`〜`[6]` の集計は results/ と一致 (`spill178_1161.tsv` cmp OK)。#2246 の実測 (2m29s) との差は機械の差と推定 (未検証)。

## 2. 対象の確認

- 対象 19 関数・23 site は `results/spill178_1161.tsv` の status=未判定 と一致 (`410770 4120c0 412ee0 415610 415c30 417310 417b70 41a5d0 41a670 41ba50 41bfa0 41e490 44f440 45a2a0 45b170 45c290 45d0a0 45d610 45f560`)。
- spill 宛 unk site の未判定は 120 件 (全 178 件中)。測定対象の 23 site は、そのうち群 C 前半。
- IR の所在: `410770` は `function_410770` が wrapper (`function_410490` と `function_4104d0` を呼び、`stack_var_-16.0.reg2mem` 経由で返す)。他の対象の本体は `function_X` (直接定義) 側で、`__lifted` 定義は `boot_final3.ll` に 12 件のみ (`grep -c __lifted` = 12)。対象 19 関数の本体行数は 25〜797 行 (`awk` で `define` から `}` まで実測)。

## 3. 機械語の後続読み出し (PE 経路・実測)

`audit_lsf.py --pe block00031_PE.bin --only <19 関数>` で 19 関数すべて機械語を辿れた (`mach_fns=19`・所要 0.45 秒)。
config 経路 (`boot1.drc.config.json`) では 17 関数が `NO DESCEND` (関数区間表に無い) で、後続読み出しを取れなかった (残り 2 関数 `415610`・`415c30` は取れた)。本 fix (差し戻し対応) では `tools/m11/work` を展開していないため、この件数は再実測していない (前回 run の実測値。本 fix では未再測定)。

対象 23 site について、同じ `[rbp/rsp + disp]` を後続で参照する命令の件数 (descend 経路・線形でなく CFG を辿る):

| 関数 | site | 後続の同 slot 参照 | 備考 |
|---|---|---|---|
| 410770 | 4107c7 | 1 (4107ec mov rax) | IR wrapper: reload → ret |
| 4120c0 | 4120da | 2 (cmp eax) | CELL_DEEP |
| 412ee0 | 412ef6 | 2 (cmp / mov rcx) | |
| 415610 | 415751 | 4 | |
| 415c30 | 415d43 / 415d87 | 3 / 1 | |
| 417310 | 417355 | 4 | |
| 417b70 | 417c35 | 12 | |
| 41a5d0 | 41a5fa / 41a618 | 1 / 1 | 41a618 は CELL_DEEP |
| 41a670 | 41a6e2 | 1 | |
| 41ba50 | 41ba8a | 同 slot 無し (`[rbp]` は基底形式のため未照合) | |
| 41bfa0 | 41bfb7 / 41bfd1 | 4 / 1 | |
| 41e490 | 41e513 | 同 slot 無し (`[rbp]` 形式) | |
| 44f440 | 44f50a | 0 (`[rsp+0x20]`) | 後続読み出し無し |
| 45a2a0 | 45a577 | 1 (lea のみ) | CELL_DEEP |
| 45b170 | 45b1bf | 5 | |
| 45c290 | 45c6dd | 17 | |
| 45d0a0 | 45d570 / 45d581 | 6 / 5 | |
| 45d610 | 45d754 | 4 | |
| 45f560 | 45f938 | 14 | |

読み出し件数は「同じ変位の後続参照」の数で、経路の到達性は示さない (線形でなく CFG 降下だが、IR 側の突合は未実施)。`[rbp+0x40]` のような広い slot は別の変数と共有される可能性がある。

## 4. 判定

- 測定で確定させた判定: **0 site**。
- 理由: 判定には機械語の後続読み出しと IR 側の reload (同 slot の値の流れ) の両方の突合が必要。対象の IR 本体は 25〜797 行あり、残り時間では 23 site を突合できなかった。根拠の無い判定を jsonl に書いて脱落集合を確定させることは避けた。
- `candidate_verdicts_1161.jsonl` と `spill178_1161.tsv` は変更していない (`git diff` 空)。

## 5. 再現

```sh
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh   # 前回 run の実測 1m58s。spill178_1161.tsv の 未判定 120 件を確認
PE=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
python3 tools/m11/ldfix/audit_lsf.py tools/m11/work/boot_final3.ll tools/m11/work/m11_image.bin \
  'tools/m11/work/boot*.drc.config.json' --pe "$PE" --only 410770,4120c0,412ee0,415610,415c30,417310,417b70,41a5d0,41a670,41ba50,41bfa0,41e490,44f440,45a2a0,45b170,45c290,45d0a0,45d610,45f560
```

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 前半 23 site の機械語 + IR 両面の分類 (測定時点で 0 件確定) | spill 宛の脱落関数の和集合 69 が未確定。前半 19 関数が和集合に入るかが未判定 | #2264 (open のまま。次 run で分類を継続) |
| 後半 23 site の分類 | 同上 | #2265 (LD-98) |
| UNDETERMINED 7 site の IR 側再検証 | 同上 | #2253 (LD-95・既存) |
| 群 A / 群 B の分類 | 同上 | #2244 / #2245 (既存) |
| config 経路で 17 関数が `NO DESCEND` (関数区間表の欠落。§3 と同じ件数) | 機械語の後続読み出しを config 経路で取れない。PE 経路 (`--pe`) が必要 | #2264 (本文の注意に追記) |

## 7. 鮮度の証跡

- 測定 commit: `25d2cdc0` (e2e・§3 の audit はこの tree で実行)。
- 測定 commit から HEAD までの差分 (`git diff 25d2cdc0 HEAD -- tools/m11/ldfix`) は本 REPORT の追加のみ。判定ファイル (`candidate_verdicts_1161.jsonl`・`results/spill178_1161.tsv`) の差分は 0。
- 差分の範囲は `tools/m11/ldfix/REPORT_2264.md` のみ (docs 追加)。REPORT は自身の commit hash を内部に書けないため、最終 HEAD での `git diff --stat 25d2cdc0 HEAD -- tools/m11/ldfix` の出力は PR コメントに載せる。

