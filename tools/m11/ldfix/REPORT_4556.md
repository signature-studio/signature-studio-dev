# REPORT #4556 — audit の CELL_COLLAPSED 判定を site 単位にする (非既定の判定)  (LD-224)

親: #4418 (LD-213)。元の親: #3580 (LD-164)。依存: #5243 (LD-260, closed・PR #5259)。

## 0. 結論

- **受入 1 を達成**: site 単位の判定 `site_gran_4556.py` を非既定の追加ツールとして実装した。対応付けは #5243 の rmw 規則 (修復報告 `fixed[].ir_name` は使わない)。
- 既定の判定 (`audit_lsf_ssa.py` の関数 × K) は変えていない。`fix_d17_e2e.sh` は HEAD で PASS、spill 宛 CELL_COLLAPSED は 37 → 25 のまま。
- site 単位の判定では、修復後の spill 宛 CELL_COLLAPSED が **25 site → 24 site** (16 関数 → 15 関数)。減った 1 site は 100b890 cell 11e27f0 (`100b8d0`)。
- ネガコン (修復を外した判定) では減少が **0** (37 → 37)。判定が修復を見ていることを確かめた。
- 受入 2・3・4 は未達。§4 の未解決表に、起票先 (子 issue) を書いた。

## 1. 測定条件

- 測定 commit: `d3eea1421` (`feat(ldfix): site 単位の CELL_COLLAPSED 判定を非既定で追加 (#4556)`)。HEAD で `fix_d17_e2e.sh` と `site_gran_4556_e2e.sh` を再実行した。
- 素材: `work-m11` (`tools/m11/work/`)・`toolchain-emsdk` (emcc rc=0)。`$RUNNER_TEMP/m11art` に展開。
- 再現: `bash tools/m11/ldfix/site_gran_4556_e2e.sh` (foreground、約 31 秒、load 0.14)。既存の基準: `bash tools/m11/ldfix/fix_d17_e2e.sh` (foreground、63.5 秒、RESULT: PASS)。
- 差分: `git diff 59297153f HEAD -- tools/m11/ldfix/` は既存 2 本 (`audit_lsf_ssa.py`・`value_flow_5243.py`) の小変更と新規 2 本。

## 2. 方式 (受入 1)

`site_gran_4556.py` (修復前 IR・修復後 IR・image・audit 2 本を入力):

1. 修復前の audit で「frame かつ CELL_COLLAPSED」の site を集める (関数 × K の判定で残るもの。37 site)。
2. 修復前 IR で、site の機械語 chain (rip セル経由の `mov rA,[rip+X]; mov rD,[rA]`) を #5243 の rmw 規則で抽出する。site の命令アドレスで chain を 1 本に絞る。
3. 同一 dec_label ブロック内の K の IR i32 読み出しが 1 本・chain が 1 本・幅一致なら結べた (`1to1`)。結べなければ **UNLINKED** (CELL_COLLAPSED のまま残す)。
4. 結べた site は、修復後 IR の同じブロックに K の i32 読み出しが残っていなければ **REPAIRED**、残っていれば **REMAIN**。

判定の注意:

- `%cellps.<K>` (修復が作る `load ptr`。セルの中身を読む) は K 直接の読み出しではないので、残存の判定から外す。これを入れないと、修復が効いた site も REMAIN になる (実測で確認)。
- `audit_lsf_ssa.py` の `cell_check` の出力に `src` (rip セルの命令アドレス) を足した。既定の判定の値は変わらない (e2e の数値が同じことで確認)。

## 3. 結果 (受入 1)

修復前後の site 単位 (`site_gran_4556_e2e.sh` の出力、HEAD `d3eea1421`):

```
site 単位 (#4556・非既定): spill 宛 CELL_COLLAPSED 関数×K 判定の後 25 site / 16 関数 -> site 単位の後 24 site / 15 関数
修復後 audit 上の内訳: REPAIRED=1 REMAIN=9 UNLINKED=15
ネガコン: 修復を外した判定 -> 37 site / 22 関数 -> 37 site / 22 関数 (減少 0)
```

| 判定 | 修復前 (関数 × K) | 修復後 (関数 × K) | 修復後 (site 単位) |
|---|---|---|---|
| spill 宛 CELL_COLLAPSED の site 数 | 37 | 25 | 24 |
| 関数数 | 22 | 16 | 15 |

内訳 (修復後 audit に残る 25 site): REPAIRED 1 (100b890 `100b8d0`、cell 11e27f0)・REMAIN 9 (同じ K 読み出しが同ブロックに残る)・UNLINKED 15 (1to1 に結べない。保守側で残す)。

注意: 関数 × K の 37 → 25 の内訳 (修復 13 のうち 12 site が消えた) と、site 単位の 1 site (100b8d0) は別の数え方。site 単位の方が「修復が直した site」だけを数えるので、差は 1 件だけ大きく減る。

## 4. 未解決 (受入 2・3・4)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 2: `results/` の TSV を site 単位の判定で再生成し、`fix_d17_e2e.sh` の件数 assert (37 → 25 等) を新しい粒度に合わせる | 既定の数値は変えていない。assert の粒度は現行のまま | 子 issue [LD-293] |
| 受入 3: ネガコンを既存 e2e (`fix_d17_e2e.sh`) に組み込む | 本 PR のネガコンは `site_gran_4556_e2e.sh` 内だけ | 子 issue [LD-293] |
| 受入 4: 変更前後の件数の差 (関数 × K と site 単位) を REPORT に書く | §3 に 1 回書いた。`fix_d17_e2e.sh` の TSV への反映は [LD-293] | 子 issue [LD-293] |
| UNLINKED 15 site (1to1 に結べない) | 保守側で CELL_COLLAPSED のまま。見落としはない | #2072 (LD-76) の値の流れによる判定 |
| 100b890 cell 11e27f0 の mul 側 (`%15`・`%23`) | 単独測定では結べるが、audit の frame 判定で対象外 (#5243 §3) | #2072 (LD-76) |
| 修復の実行時の正しさ (FLEngine 起動) | 本 issue の範囲外 | 範囲外 |

## 5. 範囲外

- 既定の判定 (`audit_lsf_ssa.py` の出力と `results/` の TSV) は変えない。
- 修復 pass (`fix_spill_2794.py`・`link_d17.py`) は変えない。
- 起動・GUI に関わらない IR 修復のため、製品 KPI は測っていない。
