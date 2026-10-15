# PY-180 (#3278): patterns の残り 2 件 (getActivePatternGroup・getPatternsInGroup) の PE 解析と実装

親: #3219 (PY-172)・#1804 (PY-48)。既知類型との関係: 該当なし (lift 作業ではない)。
前段: `REPORT_PY172.md` (件数 0 の仮置き・索引基準)。子: #4114 (PY-302・`getPatternsInGroup`)。
測定対象の commit: `3c0d1bf47` (コードを変えた最後の commit。本 REPORT の追加は後続)。

## 結論

- `getActivePatternGroup` は C・mock に実装した (戻り -1)。根拠は `.data` のグローバル int の初期値 -1 と、その参照箇所が -1 を番兵として比較すること (§1)。書込み元は PE 内で特定できず、仮置きである。
- `getPatternsInGroup` は未実装のまま (code 2)。索引 -1 の意味が PE だけでは確定できないため、推測実装しない。子 #4114 (PY-302) に分離した (§3)。

## 1. getActivePatternGroup (0xd66fe0)

逆アセンブル (`pe_disasm.py d66fe0`):

```
0xd66fe4 mov rax, qword ptr [rip + 0x87c5d5]   ; グローバル int* (slot VA 0x15e35c0)
0xd66feb mov ecx, dword ptr [rax]               ; int を読む
0xd66fed mov rax, qword ptr [rip + 0x87d28c]
0xd66ff4 call qword ptr [rax]                   ; 整数化 (検査なし)
```

- slot 0x15e35c0 の値は 0x1532e58 (`.data`)。その値 `dword` の初期値は `-1` (0xffffffff)。
- 0x1532e58 を rip 相対で読む箇所は 4 件 (0xec33cf・0xec3409・0xec3422・0xec3453)。すべて `cmp` で、比較相手は `-1` か、パターン構造体の群番号 (ストライド 0xc0・オフセット 0x10)。
- 書込み元: `.text` 内に 0x1532e58 への rip 相対の書込み (`mov [rip+..], reg`) は見つからなかった。`.text` 全体を capstone で走査して確認した (逆アセンブルできないバイトは 1 バイト送りで飛ばした)。間接参照 (ポインタ経由) での書込みは未確認。
- 解釈: 「-1 = 未選択 (番兵)」と読むのが最も自然。ただし値の意味は PE の比較式からの推定であり、確定ではない。

仮置き: 戻り -1。C (`provider/fl_engine.c`) と mock (`host/fl_mock.mjs`) で同じ値。

## 2. getPatternsInGroup (0xd67110) の確定範囲

PE 上で確定した事項 (REPORT_PY172 §1・§2 と同じ):

- 引数 `"i"` 1 個。範囲 `[-1, 件数-1]` を検査 (0xd67157・0xd67161)。外は status -4 (0xd671d4)。
- 件数 0 のとき範囲は `[-1, -1]` になり、索引 -1 だけが通る。
- 範囲内は ebx = 0..999 を走査し、先頭 dword が索引と等しい構造体の添字 ebx を list に追加する (0xd67181〜0xd671b3)。
- 索引は群番号と直接比較される (0xd67185)。0 始まり・1 始まりの変換は無い。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| getPatternsInGroup の索引 -1 の意味 (現在のグループか、群番号 -1 の構造体か) | 未実装 (code 2)。-1 の結果は未定義 | #4114 (PY-302) |
| パターン構造体の既定の群番号 (件数 0 の仮置きの根拠) | getPatternsInGroup の結果 | #4114 (PY-302) |
| getActivePatternGroup のグローバル int (0x1532e58) の書込み元 | -1 の仮置きが FL の実状態と一致するか未確認 | #4114 (PY-302) |

## 4. 実装・検証

| 検査 | 手順 (コマンド) | 結果 |
|---|---|---|
| 素材 | `tar --zstd -xf <artifacts>/fl-win64.tar.zst -C <展開先>` (`[WIN64]`・素材の取得は `docs/WORKFLOW.md` §11) | rc 0 |
| 入力 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` | rc 0 |
| CPython wasm | `bash build_cpython_wasm.sh` | rc 0 |
| flpy リンク | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 |
| provider ビルド | `bash provider/build.sh` | rc 0。`fl_table.c`: 435 関数・ハンドラ **196** |
| all_tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | rc 0・**48/48 ok** (`soft_error` 0・`raised` 0・`host_calls` 37425・`callback_roundtrip` true) |
| provider_check | `node tests/provider_check.mjs` | rc 0・PASS。`functions` 435・実装 **196** / 未実装 **239** |
| 差分検査 | `node tests/patterns_group_diff.mjs` | rc 0・14 呼出し・diffs 0・PASS |

測定時の load average は 1.7〜2.1。

コード差分 (測定 commit 以降の確認):

```
git diff 3c0d1bf47 HEAD -- tools/python/provider tools/python/host tools/python/tests
```

本 REPORT の追加以外に変更は無い (出力は 0 行)。

## 検証範囲 / 範囲外

- 範囲内: `getActivePatternGroup` の PE 解析 (参照箇所・初期値)、C と mock の一致、既存の provider_check と all_tools。
- 範囲外: `getPatternsInGroup` の実装、グループ・群番号の実値、実機の FL を動かした確認 (PE の静的解析のみ)。
- 製品 KPI: 起動・GUI に関わらないため記載しない。
