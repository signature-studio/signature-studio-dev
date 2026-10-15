# PY-180 (#3278): patterns の残り 2 件 (getActivePatternGroup・getPatternsInGroup) の PE 解析と実装

親: #3219 (PY-172)・#1804 (PY-48)。既知類型との関係: 該当なし (lift 作業ではない)。
前段: `REPORT_PY172.md` (件数 0 の仮置き・索引基準)。子: #4114 (PY-302・`getPatternsInGroup`)。
測定対象の commit: `4147df576` (コードを変えた最後の commit = main 取り込み merge・`provider_expect/` 移行後)。以後は本 REPORT の追加のみ。
実装の commit は `3c0d1bf47`。main 取り込み後の現 head で全検査を再測定した (§4)。

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

測定 HEAD: `4147df576` (runner・2026-10-15 08:20〜08:29 UTC。`6a7d2634e` 以降に `origin/main` (`9721869b7`) を取り込んだ merge `4147df576` を含む。測定後の commit はこの REPORT の追加だけ)。emsdk は `$RUNNER_TEMP/emsdk` に `emsdk install 6.0.12` で入れ、`[EMSDK]` の既定位置に symlink を張った (`build_cpython_wasm.sh` / `provider/build.sh` が既定位置の `emsdk_env.sh` を直接 source するため。`toolchain-emsdk` 素材は本 run に無い)。fl-win64 は `$ARTIFACTS_DIR` から展開した。

| 検査 | 手順 (コマンド) | 結果 (測定 HEAD `4147df576`) |
|---|---|---|
| 素材 | `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` (`[WIN64]`・`docs/WORKFLOW.md` §11) | rc 0 (5.6 s) |
| 入力 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` | rc 0 |
| CPython wasm | `bash build_cpython_wasm.sh` | rc 0 (2 分 45 秒・real。python.wasm 5,926,953 B) |
| flpy リンク | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 (6.4 s・flpy.wasm 5,923,675 B) |
| provider ビルド | `bash provider/build.sh` | rc 0 (1.5 s)。`fl_table.c`: 435 関数・ハンドラ **205**。`flprov.wasm` 71,680 B |
| all_tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | rc 0 (2.2 s)・**48/48 ok** (`soft_error` 0・`raised` 0・`no_args` 0・`host_calls` 37425・`callback_roundtrip` true) |
| provider_check | `node tests/provider_check.mjs` | rc 0 (0.4 s)・PASS。`functions` 435・実装 **205** / 未実装 **230**・`mcp_static` 60 |
| 差分検査 | `FL_ENGINE=wasm node tests/patterns_group_diff.mjs` | rc 0 (0.05 s)・14 呼出し・diffs 0・PASS |

測定時の load average は 1.5 (4 コア・測定開始時 1.54)。検査は順次実行した。

コード差分 (測定 commit 以降): 測定 commit `4147df576` の後は本 REPORT の追加のみ。

参考 (測定 commit の前段): 実装の変更が入った範囲の差分。
- `git diff --stat 6a7d2634e 4147df576 -- tools/python/provider tools/python/host` は 0 行 (provider/host は不変)。
- `git diff --stat 6a7d2634e 4147df576 -- tools/python/tests` は 39 files / 282 insertions / 73 deletions。これは `provider_check.mjs` の `provider_expect/` 移行 (PY-280・#3978) と本 PR の `pe180.json` 登録によるもので、測定 commit `4147df576` に含まれる。測定はこの差分の後の HEAD で行った。

旧 REPORT の 196/239 (`3c0d1bf47` 時点)・`9facb33bb` 時点の 204/231・`6a7d2634e` 時点の 205/230 は、いずれも現 HEAD の実測 205/230 で置き換えた (`provider_check.mjs` の期待数は `provider_expect/` の和集合から導出され、実測と一致)。

## 検証範囲 / 範囲外

- 範囲内: `getActivePatternGroup` の PE 解析 (参照箇所・初期値)、C と mock の一致、既存の provider_check と all_tools。
- 範囲外: `getPatternsInGroup` の実装、グループ・群番号の実値、実機の FL を動かした確認 (PE の静的解析のみ)。
- 製品 KPI: 起動・GUI に関わらないため記載しない。
