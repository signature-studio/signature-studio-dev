# PY-123 (#3028): boot 停止時点の undo 管理オブジェクトと安全判定の実行時値を実測する

親: #2998 (PY-123)。前段: #2978 (PY-120)・PE 解析は #2998 の issue コメント (2026-10-14 21:08Z)。
既知類型との関係: 未判定。boot 中に `.data` の undo 系スロットが 0 に戻る原因は未特定で、`docs/DEFECTS.md` の既知類型に当たるかは確認していない (lift 由来の silent miscompile の疑いを含む)。

## 結論

- **受入条件 1〜3 は未達。** boot 停止時点 (unit 209/942、`exit`) で、undo 管理 global `0x15e1c78`・安全判定 global `0x15e4790`・成功時戻り値 singleton `0x16b82e0` の 3 つとも **0**。読むべき undo オブジェクトが存在しないため、起動直後の `+0x20` (pos)・`+0x24` (count)、安全判定述語の関数 VA、singleton の中身は測れなかった。
- **値は boot の途中で消えている。** image 敷設直後 (`_fle_data_install`) は `0x15e1c78 = 0x16bb068`・`0x15e4790 = 0x141d6b8` (PE の `.data` の値と一致)。`_fle_init` では消えない (実測)。boot 本体の途中で 0 に戻る。戻す箇所は未特定。
- **このため、boot 停止点の値は実 FL の起動直後の状態として使えない。** #2998 の実装 (`restoreUndoLevel`・`getUndoLevelHint` の C 実装) は、この 0 の原因が分かるまで再開しない。
- 測定 harness に boot 後の probe を足した (`tools/flelift/boot/fle_boot.mjs`)。boot の挙動は変わらない (units_run 209/942 は FLE-9 と同じ)。

## 受入条件の判定

| # | 受入条件 (issue #3028) | 判定 | 根拠 |
|---|---|---|---|
| 1 | undo 管理オブジェクトの起動直後の `+0x20` (pos)・`+0x24` (count) を実測 | **未達** | slot `0x15e1c78` = 0 のためオブジェクトが無い (§2)。 |
| 2 | 安全判定述語 (`[obj+0x98]`・`[obj+0x88]`、`obj = [[0x15e4790]+8]`) の関数 VA | **未達** | `0x15e4790` = 0 のため `obj` を辿れない (§2)。 |
| 3 | 成功時戻り値 singleton `[0x16b82e0]` が `None` か | **未達** | 値は 0 (未設定)。`None` か否かは判定できない。 |
| 4 | 上 3 件を本ファイルに書き、#2998 の実装を再開する | **部分** | 本ファイルに書いた。実装は未再開 (1〜3 が未達のため)。 |

## 1. 静的な値 (PE 直読み・実測)

`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`fl-win64` を `tar --zstd -xf` で展開。7 秒)。`block00031_PE.bin` (22,227,016 B、ImageBase `0x400000`)。

| VA | セクション | file 内の u64 | 備考 |
|---|---|---|---|
| `0x15e1c78` (undo 管理 global) | `.data` (raw `0x11e0678`) | `0x16bb068` | 非 0 |
| `0x15e4790` (安全判定 global) | `.data` (raw `0x11e3190`) | `0x141d6b8` | 非 0 |
| `0x141d6b8` | `.data` | `0x0` | `obj` の候補先は file 上 0 |
| `0x16b82e0` (戻り値 singleton) | `.bss` | (file 実体無し) | 静的には決まらない |

- `analysis/flapi/pe_xref.py 15e1c78` (`.text` 全域・5,022,467 命令・35.0 秒): 読出し 768 件・**書込み 0 件** (`stores=0`)。`mov [rip+slot], reg` の直接書込みは PE に無い。
- `analysis/flapi/pe_slot_writers.py 15e1c78` (36.0 秒): `[reg+8]` への書込み候補 1 件 (`0xf698af`)。`0xf698af` の周辺は `call 0xf82530` で得た確保先に `[rax+8]`・`[rax+0x10]` を書く別レコードの初期化と読め、undo 管理オブジェクトへの書込みとは断定しない (逆アセンブル確認: `tools/python/analysis/flapi/pe_disasm.py 0xf69840 70`)。

## 2. boot 停止時点の実行時値 (測定)

測定 commit: **`3064340a`** (`feat(flelift): probe undo slots after boot (PY-123, #3028)`)。コードを変えた最後の commit。
`git diff 3064340a HEAD -- tools/flelift/boot` の出力は空 (差分 0)。

測定コマンド (コミット済み HEAD で実行):

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
time timeout 900 bash tools/flelift/boot/fle6_measure.sh
```

- 所要: 実測 real 2 分 13.8 秒 (user 3 分 12.6 秒・sys 19.7 秒)。工程: gen-A 5 s・lift 51 s (x64c・closure 2・8 shard)・clang-plain 48 s (8 shard・peak RSS 2.2〜2.7 GB/本)・boot 15 s・negctl 14 s。
- load average: 開始時 `0.22 0.59 0.37`、clang 中 `1.61 0.94 0.52`、boot 中 `1.54 0.96 0.53`。並列 1 本 (1 回のみ)。
- n=2。コミット済み HEAD での測定 (上) と、同じコードを未コミットの作業ツリーで回した 1 回目 (2 分 20.8 秒) の値が一致した。

| 実行 | units_run / total | boot_threw | slot `0x15e1c78` | pos `+0x20` / count `+0x24` | slot `0x15e4790` | `[0x16b82e0]` | IPP 判定 |
|---|---|---|---|---|---|---|---|
| shim 有 (`FLE_IPP=1`) | 209 / 942 | `exit` | `0x0` | null / null | `0x0` | `0x0` | `ok:false` (既知 NG) |
| ネガコン (`FLE_IPP=0`) | 209 / 942 | `exit` | `0x0` | null / null | `0x0` | `0x0` | `ok:true` |

- 判定: **boot 停止時点で 3 つの global とも 0。** shim の有無で変わらない。
- `FLEBOOT_IPP_CHECK ok:false` (shim 有) は既知の NG。FLE-9 (`tools/flelift/boot/REPORT.md` §9) の「shim 有の IPP 判定は NG (#2702 が追う)」と同じ結果。本変更は IPP 判定の式に触れていない (差分は `fle_boot.mjs` の undo probe と出力行の追加のみ)。
- 停止点は unit 209 の `MessageBoxA` → `exit(0)`。`FLE-9` の記録と同じ。

### 2-1. 正の対照 (probe が非 0 を読めることの確認)

`tools/flelift/boot/undo_probe_check.mjs` (コミット済み) を `tools/flelift/work/boot/fleboot_plain.cjs` に対して実行。

```sh
FLE_BOOT_VARIANT=plain node tools/flelift/boot/undo_probe_check.mjs "$PWD/tools/flelift/work/boot/fleboot_plain.cjs"
```

| 時点 | slot `0x15e1c78` | slot `0x15e4790` |
|---|---|---|
| 敷設前 | `0x0` | `0x0` |
| `_fle_data_install` 直後 | `0x16bb068` | `0x141d6b8` |
| `_fle_init` 直後 | `0x16bb068` | `0x141d6b8` |

- 判定: 敷設直後には PE の値が読める (probe は非 0 を検出できる)。`_fle_init` では消えない。
- つまり、boot 停止時点の 0 は「probe が読めない」ではなく「boot の途中で 0 に戻った」結果。

## 3. 0 に戻る箇所の絞り込み (未特定)

- `fle_boot_enter` の順序は `fle_data_install` → `fle_textwin_install` → `fle_init` → (boot 本体: DllMain → `_InitLib` → InitUnits)。`fle_data_install` と `fle_init` は値を消さない (§2-1)。
- 残る候補: `fle_textwin_install` (`.text` 内データ窓の敷設。`.data` 外のはずだが未確認)・boot 本体の unit 1〜209 のいずれか (`_InitLib`・InitUnits の中で `.data` の一部を 0 にする処理)。
- 絞り込みには unit 単位の測定 (`_fle_run` で 1 unit ずつ実行し、各後に slot を読む) が要る。本 run では未実施 (時間不足)。

## 4. 変更内容 (本 PR)

| ファイル | 変更 |
|---|---|
| `tools/flelift/boot/fle_boot.mjs` | boot 後に undo 系の probe を読み、`FLEBOOT_UNDO {...}` を出す。`boot.undo_probe` として summary JSON にも入る。既存の出力・判定 (`FLEBOOT_RESULT`・`FLEBOOT_IPP_CHECK`) は変えない |
| `tools/flelift/boot/undo_probe_check.mjs` | 正の対照 (§2-1) の再現スクリプト |
| `tools/flelift/boot/results/boot_summary_fle6.json`・`boot_summary_fle6_negctl.json` | 上の測定 (3064340a) の summary。`undo_probe` を含む |
| `tools/python/REPORT_PY123.md` | 本ファイル |
| `docs/DOC_MAP.md` | 本ファイルの索引行 |

- KPI (起動・GUI に関わる変更のため。`docs/WORKFLOW.md` §7): FLEngine 起動の dispatch 数 (units_run) は **前 209 / 後 209** (`tools/flelift/boot/REPORT.md` §2・§9 の値と一致)。最初のウィンドウ: **無し** (boot は `MessageBoxA` → `exit(0)` で停止し、ウィンドウに届かない)。boot の挙動は probe の追加で変わらない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| boot 中に `0x15e1c78`・`0x15e4790` が 0 に戻る箇所 (§3) | 起動直後の undo 値・安全判定の実体が測れない。lift 由来の silent miscompile か、実機でも 0 かが不明 | #3028 に残す (次の run で unit 単位の測定から絞り込む。子 issue は起票しない) |
| 安全判定述語の関数 VA (`[obj+0x98]`・`[obj+0x88]`) | `restoreUndoLevel` の成功・-2 の分岐が決まらない | #3028 (上と同じ原因が解消されれば測れる) |
| `[0x16b82e0]` の中身 (`None` か) | 成功時戻り値の判定ができない | #3028 (boot が Python 初期化まで届いていない可能性が高い。未確認) |
| boot が unit 209 の `MessageBoxA` → `exit(0)` で止まる | 起動直後の状態に届かない | 既存の追跡: `tools/flelift/boot/REPORT.md` §9 (#2700 系) |
| shim 有の IPP 判定 NG (`ok:false`) | 本測定の shim 有の判定が通らない (変更前から) | #2702 (`tools/flelift/boot/REPORT.md` §9 の記録どおり) |

## 6. 検証範囲

- 範囲内: boot 停止時点 (unit 209) の undo 系 3 slot の値 (shim 有・無 の 2 条件、各 1 回)。敷設直後・init 直後の値 (正の対照)。PE の静的値と xref・writer 候補。
- 範囲外: 起動直後 (boot 完了後・ウィンドウ表示後) の値。安全判定の実体。singleton の中身。boot 中のどの処理が 0 にするか。主張は boot 停止点に限る。
- 未実施: `provider/build.sh` (emcc)・`node tests/general_diff.mjs`・`node tests/provider_check.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs` (実装が無いため走らせていない)。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
bash tools/flelift/boot/fle6_measure.sh              # 約 2 分 14 秒 (§2)
FLE_BOOT_VARIANT=plain node tools/flelift/boot/undo_probe_check.mjs "$PWD/tools/flelift/work/boot/fleboot_plain.cjs"   # §2-1
python3 tools/python/analysis/flapi/pe_xref.py 15e1c78            # §1 (FL_WIN64_DIR 必須)
python3 tools/python/analysis/flapi/pe_slot_writers.py 15e1c78   # §1
```

- 生成物は `tools/flelift/work/boot/` (gitignore)。結果 JSON は `tools/flelift/boot/results/` にコミット済み。
