# tools/python REPORT: PY-96 arrangement の選択範囲読出し 4 件の PE 確定と C provider 実装 (#2738 の子 #2832)

> 正本: `tools/python/REPORT_PY87.md` (保留 146 件の出自と、状態読出しの方式)。本付録は PY-96 の実測のみ。

## 結論

- 親 #2832 の 52 件 (screen 28・arrangement 12・launchMapPages 12) は 1 run に収まらないため、**arrangement の選択範囲読出し 4 件** (`selectionStart`・`selectionEnd`・`liveSelectionStart`・`selectionIsActive`) の範囲に縮めた。
- 4 件は PE で「状態 field を読み、変換スロット `0x15e4280` に渡す」と確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/arrangement_diff.mjs` 8 呼出し)。
- **値は未確定**。初期値 `-1` (未選択) は仮置き。未選択が負値で表されることは PE 0xe43e80 で確認したが、負値が Python に何として返るかは変換先 `0x15e4280` が未同定のため未確定。
- 残り 48 件は子 issue 3 件に分けた: arrangement 残り 8 件 #2983 (`[PY-152]`)・launchMapPages 12 件 #2984 (`[PY-153]`)・screen 28 件 #2985 (`[PY-154]`)。いずれも親 #2832 の子。(題名の番号は、同じ番号の題名が他の issue と重複していたため付け替えた。issue 番号は変えていない)

## 手段

- handler の所在: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_handler_probe.py <名前...>` (`block00031_PE.bin` のみ)。PyMethodDef の entry VA と関数先頭 VA (`fn`)・flags を得る。`length`・`init` は他モジュールと名前が重なるため、entry VA で切り分けた (arrangement 0x151dc30〜0x151dd90、launchMapPages 0x151e058〜0x151e1b8、screen 0x151e5b8〜0x151e918)。
- 検算: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_selection_check.py` (本 PR 追加。4 関数の RIP 相対参照先・field offset・共通ヘルパの呼出しを再計算して照合)。
- 戻り型: `analysis/flapi/flapi_table.json` の `sig.returns`。`selectionIsActive` だけ stub 署名が無い (`None`) ため、bool は PE の `movzx` と `0xe43e80` の戻り値から推定した (推定と明記)。

## 確定した 4 関数 (PE 根拠)

| 関数 | entry | fn (VA) | flags | 読む状態 | 変換 | stub の戻り型 |
|---|---|---|---|---|---|---|
| `arrangement.selectionStart` | 0x151dd10 | 0xd786e0 | 4 (NOARGS) | `mov ecx, dword [obj+0xd74]` | `call [0x15e4280]` | int |
| `arrangement.selectionEnd` | 0x151dd30 | 0xd78700 | 4 (NOARGS) | `mov ecx, dword [obj+0xd78]` | `call [0x15e4280]` | int |
| `arrangement.liveSelectionStart` | 0x151dcb0 | 0xd78500 | **1 (VARARGS)** | `mov ecx, dword [obj+0xd74]` | `call [0x15e4280]` | int |
| `arrangement.selectionIsActive` | 0x151dd50 | 0xd78720 | 4 (NOARGS) | `call 0xe43e80(obj)` → `movzx rcx, al` | `call [0x15e4280]` | なし (bool 推定) |

- 4 件とも先頭で `call 0xd77e20` を行い、その戻り値を状態オブジェクト (`obj`) とする。`pe_selection_check.py` が `0xd77e20` の呼出しを 4 件とも確認。
- 変換スロット `0x15e4280` は 4 件とも RIP 相対の絶対アドレスとして一致 (`0xd786ef`・`0xd7870f`・`0xd7850f`・`0xd78735` の次命令 + disp で計算)。PY-87 の 4 件と同じスロット。
- **未選択の表現**: `0xe43e80` は `dword [rcx+0xd74] >= 0` かつ `dword [rcx+0xd78] >= 0` のときだけ `al = 1` を返す (`jl` で負値を弾く)。よって `start`・`end` の負値が「未選択」の表現と読める。mock/C の初期値 `-1` はこれに従った仮置き。`0xe43e80` の offset (`+0xd74`・`+0xd78`) と分岐は手読み。`pe_selection_check.py` は `cmp dword ptr [rcx` の個数 (2) だけを見るため、offset と分岐の正しさは保証しない。
- **int の変換の注意**: `mov ecx, dword ...` は 32bit 値を zero-extend して渡す。`-1` は `0x00000000FFFFFFFF` として変換スロットに届く。Python 上で `-1` と見えるか `4294967295` と見えるかは、変換先 (0x15e4280 の先) の実装が決める。未同定。
- **共通ヘルパ `0xd77e20`**: `cmp qword [*A], 0` が偽なら `*(*B)`、真なら `*(*C)` を返す (A・B・C は global の slot)。どの slot がどの arrangement 状態かは未同定。
- **liveSelectionStart**: 読む field は `selectionStart` と同じ `+0xd74`。したがって返す値も同じと PE から読める。ただし flags=1 (METH_VARARGS) で、先頭 40 命令に引数の解析 (PyArg 系) が無い。実機は引数を読まず、余計な引数を無視すると読める。provider は `NARGS(0,0)` で引数付きを code 5 にする (下の未解決)。

## 検証

測定 commit: `8fa9b315` (コードを変えた最後の commit。`tests/arrangement_diff.mjs` のコメント 1 行の追加)。その前のコード差分の最終 commit は `bb06a6f5` (`origin/main` (`0064cfbc`) を取り込んだ merge)。`bb06a6f5` より前の実装本体は `caad77f6` (mock・C・試験・件数)、検査スクリプトは `7e16e54a`。main の取り込みは 2 回あり (`8787ed04`・`0064cfbc`)、衝突はどちらも `tests/provider_check.mjs` の期待値だけだった。main 側で増えた集合は `pe115` (`mixer.getTrackColor`・PY-115) と `pe100` (`channels.getStepParam`・`channels.getCurrentStepParam`・PY-100)。両側の集合を併せ、期待値を 実装 90 / 未実装 345 にした。

環境: runner 4 core。ビルドの前提の生成物は gitignore 対象 (`tools/python/work/`・`tools/python/dist/`)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。素材 `fl-win64` の `extracted/` から `block00031_PE.bin`・`block24429_DATA.bin`・`block24430_DATA.bin`・`block25159_DATA.bin`・`block24618_DATA.bin` を展開 (tar の member 名は `extracted/...`)。emsdk は `[EMSDK]` (`provider/build.sh` が `emsdk_env.sh` を source)。

前提の生成物 (`8fa9b315` の worktree で新規に作成): `bash fetch_inputs.sh` (rc 0)・`bash build_cpython_wasm.sh` (rc 0・CPython 3.12.1・3 分 24.3 秒)・`FLPY_SKIP_TABLE=1 bash build_flpy.sh` (rc 0・4.9 秒)・`bash provider/build.sh` (rc 0)。

測定は `8fa9b315` の作業ツリー (未コミットの変更なし) で、開始時の load average 1.59 (1 分値)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 90 | 1.02 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 90 / 未実装 345 / MCP 静的 60) | 0.43 秒 |
| `node tests/arrangement_diff.mjs` | calls 8、diffs 0、PASS | 0.04 秒 |
| `node tests/general_diff.mjs` | calls 9、diffs 0、PASS (PY-87 の回帰) | 0.04 秒 |
| `node tests/mixer_diff.mjs` | calls 57、diffs 0、PASS (main 取り込みの回帰) | 0.04 秒 |
| `node tests/channels_diff.mjs` | calls 161、diffs 0、PASS (main 取り込みの回帰) | 0.04 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback_roundtrip true | 1.29 秒 |
| `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_selection_check.py` | PASS (4 関数 ok、0xe43e80 の比較 2 件) | 4.89 秒 (pefile の読込み込み) |

件数の変化: main (`0064cfbc`) 単独は 実装 86 / 未実装 349 (`pe100`・`pe115` を含む)。本 PR は `pe96` 4 件を加え 実装 90 / 未実装 345 (total 435)。内訳: MCP 60 + device 5 + mig 5 + pe39 1 + stub41 6 + pe100 2 + stub89 2 + pe87 4 + pe96 4 + pe115 1 = 90。

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `selEnd` 初期値を `-1` から `0` にすると、`node tests/arrangement_diff.mjs` は `AssertionError: arrangement 差分 1 件` で rc 1 (FAIL)。元に戻すと calls 8・diffs 0・PASS (rc 0)。比較は測定 commit `8fa9b315` で行った (`selEnd` を一時変更して検査し、元に戻した。`git status` は clean)。

コード差分 (測定 commit から PR HEAD まで、`tools/python` の .md 以外):

```
$ git diff 8fa9b315 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 変換スロット `0x15e4280` の先 (int と bool の区別、負値 `-1` の Python 上の値) が未同定 (PY-87 から持ち越し) | 未選択時の `selectionStart`・`selectionEnd`・`liveSelectionStart` の Python 値が、実機と違う可能性 (mock/C は `-1`) | 子 #3043 (`[PY-144]`・親 #2983)。int と bool の区別と負値の確定は #3043 の受入条件。arrangement 残り 8 件と同じ変換を使うため、同じ親の子で同定する |
| `liveSelectionStart` は flags=1 (VARARGS) で引数を読まない。provider は引数付きを code 5 にする | 引数付き呼出しの挙動が実機と違う可能性 | 子 #3043 (`[PY-144]`・引数個数の確定) |
| 共通ヘルパ `0xd77e20` が選ぶ 2 つの状態 slot (A・B・C) の所有者 (どの arrangement 状態か) が未同定 | 選択値が何を指すかの意味論は未確定 | 子 #3043 (`[PY-144]`・`0xd77e20` の object を同定) |
| 4 件の値 (初期値 `-1`) は実機未測定 | mock の値をそのまま正として扱えない | 再測定は子を起票しない。本表に残す |
| 残り 48 件 (arrangement 8・launchMapPages 12・screen 28) | 未実装のまま | 子 #2983 (`[PY-152]`)・#2984 (`[PY-153]`)・#2985 (`[PY-154]`) (親 #2832)。各子は範囲を縮め、残りを #3041・#3043 (arrangement)、#3027・#3029・#3030 (launchMapPages)、#3021・#3022・#3025 (screen) へ移した (各子の本文) |

## 検証範囲 / 範囲外

- 検証範囲: arrangement の選択範囲 4 件の mock/C 差分 (既定値の戻り値・引数個数違い)、provider の表・件数、既存 general の回帰 (`general_diff`)、main 取り込み後の `mixer_diff`、全 48 件の wasm 経路 (`all_tools`)。
- 範囲外: 選択状態を変える経路 (本 provider に setter 無し。既定値の 1 通りだけを比べた)、実機の値、`liveSelectionStart` の引数付き呼出し。
