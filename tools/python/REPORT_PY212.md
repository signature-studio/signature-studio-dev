# tools/python REPORT: PY-212 mixer 残り関数の PE 意味論 (表順前半・#5238)

> 親: #4555 (PY-339)。子: #5238 (PY-4896)。後半は子 #5239 (PY-4897)。内部関数の追跡は子 #6087 (PY-5417)。
> 関連: `REPORT_PY205.md` (getTrackCount・getEqBandCount の確定)・`REPORT_PY118.md` §8 (wrapper 0xd5ec60 の idx<0)・`REPORT_PY87.md` (PE の読み方)・`REPORT_PY141.md` §0 (変換スロット `0x15e4280` = PyLong_FromLong)。
> 解析補助: `tools/python/analysis/flapi/pe_mixer_wrappers.py` (入口・呼出し先・書式の一覧。`--table` で件数と C 実装の有無を出す) と `pe_disasm.py`。

## 結論

- 表順前半の C 未実装 21 件の入口 (書式・dispatch 呼出し・範囲外の分岐) を PE で読んだ。**副作用は全件では確定していない**。
- 確定した事実は「入口の検査」「読む track フィールド」「dispatch への引数の渡し方」の 3 点。
- 書込み系 9 件 (setSlotColor・armTrack・enableTrack・setTrackStereoSep・setPluginMixLevel・setPluginMuteState・selectTrack・selectAll・deselectAll) の副作用は共通経路 `0xd843d0` と core が未読のため **未確認**。
- 変換スロット `0x15e4280` は PyLong_FromLong と同定済み (REPORT_PY141 §0)。本表の int 戻りはこれに従う。bool 戻りの扱いは各関数の「未確認」欄に残す。
- 推測で C 実装は書かない。本 REPORT は `provider/fl_engine.c` を変更しない。

## 1. 表 (表順前半・C 未実装 21 件)

測定 commit: `eb943cdde` (解析スクリプトは `eb943cdde`〜HEAD で差分 0)。VA は `block00031_PE.bin` 内の wrapper。
件数の確認: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_mixer_wrappers.py --table` の出力のうち `C=未` が 21 行 (表順 5〜32 の 28 行から、C 実装済みの soloTrack・muteTrack・getTrackVolume・setTrackVolume・getTrackPan・setTrackPan・isTrackSelected の 7 件を除いた数)。

| 関数 (VA) | fmt | 読めた内容 | 未確認 |
|---|---|---|---|
| getSlotColor (0xd5eef0) | ii | index 範囲 [0,N-1] と slot [0,9] を検査。範囲内は track+0x134c+8*slot の色を `0x12bae50` で取得し R/B 入替え + `\|0xff000000`。範囲外は 0 (警告なし) | `0x12bae50` の意味 |
| setSlotColor (0xd5f0d0) | iii | index/slot/value を dispatch `0xd843d0` へ渡す。範囲検査は wrapper に無い | core の中身 |
| isTrackArmed (0xd5f200) | i | 範囲内は byte track+0x1470。範囲外は警告 `0xd84510` のあと 0 | track+0x1470 の意味 |
| armTrack (0xd5f3a0) | i\|i | index と第 2 int (省略 -1) を dispatch へ | core (`0x12c18d0` を呼ぶ条件) |
| isTrackSolo (0xd5f4e0) | i | 範囲内は byte track+0x1a。範囲外は警告 + 0 | track+0x1a の意味 |
| isTrackAutomationEnabled (0xd5fe10) | ii | index だけ検査。**slot は未検査**で track+0x134c+8*slot を読み byte +0x148 を返す | 範囲外 slot の挙動 (OOB 読みの可能性) |
| isTrackEnabled (0xd5f7b0) | i | 範囲内は byte track+0x18 をそのまま返す | track+0x18 の意味 |
| enableTrack (0xd5f8c0) | i\|i | dispatch へ渡す (第 2 int 省略 -1) | core |
| isTrackMuted (0xd5fa00) | i | 範囲内は `byte track+0x18 == 0` (sete)。範囲外は警告 + 0 | track+0x18 の意味 |
| isTrackMuteLock (0xd5fc10) | i | 範囲内は byte track+0x1b。範囲外は警告 + 0 | track+0x1b の意味 |
| getTrackPluginId (0xd5fcb0) | ii | index だけ検査。範囲内は `0x12be250(index, slot)` の結果 | **slot 未検査**・`0x12be250` |
| isTrackPluginValid (0xd5fd50) | ii | index だけ検査。範囲内は `0x132f780(track+0x134c+8*slot)` の al | **slot 未検査**・`0x132f780` |
| getTrackStereoSep (0xd606c0) | i | 範囲内は `0x12be250(index,0)` → `0x1051300(code,0x7fffffff,1)` → double 変換。範囲外は既定定数 | `0x12be250`・`0x1051300` の意味・既定定数 (`[rip+X]`) の値 |
| setTrackStereoSep (0xd60930) | if\|i | index・float・第 3 int (省略 0) を dispatch へ | core |
| getPluginMixLevel (0xd60a80) | ii | index と slot [0,9] を検査。範囲内は `0x12be250` → `0x1051300` → float 丸め (cvtsd2ss/cvtss2sd)。範囲外は `-4` | `0x12be250`・`0x1051300` の意味 |
| setPluginMixLevel (0xd60f70) | iif\|i | 4 引数を dispatch へ | core |
| getPluginMuteState (0xd60b40) | ii | index と slot を検査。範囲内は `0x12be250` + `0x1046a30(code,0,2)`。範囲外は `-4` | `0x1046a30` の意味 (#2887 系) |
| setPluginMuteState (0xd60ce0) | iii | 3 int を dispatch へ | core |
| selectTrack (0xd61250) | i\|i | index と第 2 int (省略 -1) を dispatch へ | core |
| selectAll (0xd61400) | (NOARGS) | dispatch に第 1 引数 1。戻りは None | core |
| deselectAll (0xd614d0) | (NOARGS) | dispatch に第 1 引数 0。selectAll と**同じ core** (`lea r8` の解決先が一致) | core |

## 2. 確定した事実

- 21 件とも入口の書式・dispatch 呼出し・範囲外の分岐を読んだ。`--table` の `C=未` の 21 件と一致する。
- isTrackMuted と isTrackEnabled は同じ track+0x18 を読み、Muted だけ反転する (本体の命令で確認)。track+0x18 の意味は未確定。
- isTrackAutomationEnabled・getTrackPluginId・isTrackPluginValid は **slot の範囲検査が無い**。C 実装で範囲を決める前に確認が必要。
- selectAll と deselectAll は同じ core を 1 / 0 で呼ぶ。

## 3. 未確認 (推測で書かない)

- 書込み系 9 件 (setSlotColor・armTrack・enableTrack・setTrackStereoSep・setPluginMixLevel・setPluginMuteState・selectTrack・selectAll・deselectAll) の副作用。共通経路 `0xd843d0` と core が未読。
- `0x12be250`・`0x1051300`・`0x12bae50`・`0x132f780`・`0x1046a30` の意味。
- track の各フィールド (+0x18・+0x1a・+0x1b・+0x1470) の意味。
- 既定定数 (getTrackStereoSep の範囲外) の値。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 書込み系の共通経路 `0xd843d0` と core の副作用 (9 件) | 書込み系の副作用が未確定 | #5217 (PY-4888)・#5325 (PY-4911) と共通 |
| getter 系の内部関数 `0x12be250`・`0x1051300`・`0x12bae50`・`0x132f780`・`0x1046a30` の意味 | getTrackPluginId・isTrackPluginValid・getTrackStereoSep・getPluginMixLevel・getPluginMuteState・getSlotColor の値 | #6087 (PY-5417) |
| slot 範囲検査が無い 3 件 (isTrackAutomationEnabled・getTrackPluginId・isTrackPluginValid) | 範囲外 slot の挙動 (OOB 読みの可能性) | #6087 (PY-5417) |
| setter 系の表順後半 (`0xd61250` 以降の残り) | 表順後半の関数の確定 | #5239 (PY-4897) |

## 5. 再現

```
FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_mixer_wrappers.py <関数名 ...>
FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_mixer_wrappers.py --table
```

展開: `mkdir -p <展開先> && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` (展開後 `<展開先>/extracted/block00031_PE.bin`)。
