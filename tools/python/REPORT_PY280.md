# PY-280 (#3978): provider_check.mjs の per-PR 期待集合を provider_expect/ に移す

既知類型との関係: 該当なし (lift 作業ではない)。起動・GUI に関わらないため製品 KPI は対象外。

## 0. 結論

- `tests/provider_check.mjs` の per-PR 期待集合 **31 個 (116 関数・重複 0)** を `tests/provider_expect/<tag>.json` (1 PR = 1 ファイル) に移した。本体に残るのは mcp・dev・mig の 3 集合と検査ロジックだけ。
- 手書きの件数 assert は、期待集合からの導出 (`impl === |和集合|`・`unimpl === ids.length - impl`) に変えた。表に無い id は FAIL する。
- 移行前後の実装集合は **差分 0** (実装 186 / 未実装 249 / 全 435)。`provider_check.mjs` PASS、`FL_ENGINE=wasm all_tools.mjs` は **48/48 ok**。
- 競合の実測 (疑似ブランチ 2 本): 新方式 **0 件** (`merge-tree` rc 0・ハンク 0)。旧方式 (同じ 2 本を `provider_check.mjs` 本体へ書いた場合) は **1 ファイル・2 ハンク** (rc 1)。
- issue 本文の『impl 176 / unimpl 259』は PR #3765 (pe136 の 10 件を追加) の取込み前の値。現 main (`32e6f8b46`) は **186 / 249**。本 REPORT は現 main の値を基準にした。

## 1. 測定 commit と差分の証跡

- 測定 commit: **`4e61b24bb`** (`origin/main` (`32e6f8b46`) を取り込んだ merge)。取り込みで `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/device_diff.mjs` が変わったため、全測定を取り込み後の HEAD で取り直した。
- 移行の code commit は `4f256b0be` (取り込み前)。その時点の測定 (同じ数値) は同じ結果だった。
- `git diff 4e61b24bb HEAD -- tools/python ':!*.md'` の出力は 0 行 (本 REPORT の commit は文書だけ)。

## 2. 移行の対象 (実測)

| 項目 | 値 | 数え方 |
|---|---|---|
| 移した集合 | 31 | `provider_check.mjs` の `const X = new Set([...])` のうち mcp・dev・mig 以外 |
| 内訳 | pe* 28 + pl61・stub41・stub89 各 1 | 変数名が tag (ファイル名と一致) |
| 移した関数 | 116 | 集合の要素の総数。重複 0 (`node` で確認) |
| 本体に残した集合 | 3 (mcp は表から導出 60、dev 5、mig 5) | issue の指定どおり |
| 削除した行 | 集合定義 (説明コメント込み)・OR 連鎖の 1 行・内訳コメントの 1 行 | `git diff 592f4c8e0 4f256b0be -- tools/python/tests/provider_check.mjs` |
| 説明コメント | JSON の `note` に保持。`refs` は `note` 内の `#N` を抽出 | `pe100` だけ元の const に説明コメントが無く、`note` は空 (出典は未確認) |

issue 本文の『33 個の const peNNN』は概数。実測は上の 31 集合 (pe* 28 + 3)。

## 3. 移行前後の実装集合 (受入 3)

`tests/provider_impl_dump.mjs` (新規・実装 id を 1 行ずつ出し、末尾に件数行を出す) で比べた。

| 時点 | 件数行 | 実装 id 行数 | 差分 |
|---|---|---|---|
| 移行前 (origin/main `32e6f8b46`・その provider_check.mjs は PASS) | `implemented=186 unimplemented=249 total=435` | 186 | — |
| 移行後 (HEAD `4e61b24bb`) | `implemented=186 unimplemented=249 total=435` | 186 | `diff` 0 行 (187 行 = 186 id + 件数行) |

- 移行前の main 本体 (`32e6f8b46` の `provider_check.mjs`) を同じ環境で実行: `{"functions":435,"implemented":186,"unimplemented":249,"mcp_static":60,"PASS":true}`。
- 移行後の件数は、期待集合の和集合 (mcp 60 + dev 5 + mig 5 + JSON 116) と一致する (`assert.equal(impl, new Set([...mcp, ...dev, ...mig, ...pe]).size)` が通る)。

## 4. 検証 (受入 6)

環境: `nproc` 4。load average (uptime) 0.25 / 0.95 / 0.63 (CPython wasm ビルドの後)。node は直列 1 並列。

| 検証 | コマンド | 結果 |
|---|---|---|
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0 (取り込み後 HEAD でも rc 0) |
| 前提の素材 | `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` | 7 s・`extracted/block00031_PE.bin` 実在 |
| 入力配置 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` | 1.2 s (`work/` に midi.py・utils.py・MCPTools.pyc) |
| CPython wasm | `bash build_cpython_wasm.sh` | 3 min 20 s・成果物 (`libpython3.12.a`・`python.wasm`) 生成 |
| flpy リンク | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | 4.7 s・rc 0。追跡済みの `flapi_table.json` を使い、表は再生成していない (`git status` 差分 0) |
| 期待集合 (本件) | `node tests/provider_check.mjs` | **PASS**・0.28 s・`{"functions":435,"implemented":186,"unimplemented":249,"mcp_static":60,"PASS":true}` |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | **48/48 ok**・soft_error 0・raised 0・no_args 0・host_calls 37425・callback 往復 true・1.26 s |
| 実装集合の一致 | `node tests/provider_impl_dump.mjs` を移行前 (origin/main) と HEAD で比較 | §3 の通り差分 0 |

### ネガティブコントロール (受入 6 の検査が効くことの確認・HEAD で実施)

| 操作 (`provider_expect/pe100.json` を一時的に変更) | 結果 |
|---|---|
| `channels.getStepParam` を集合から削除 | **FAIL**: `AssertionError: channels.getStepParam は未実装のはず` (実装済みの関数が期待集合に無い) |
| 表に無い `channels.noSuchFn` を追加 | **FAIL**: `AssertionError: provider_expect に表に無い関数 id がある` |
| 両方を元に戻す | PASS (`implemented 186`)。`git status` 差分 0 |

## 5. 競合の実測 (受入 4)

方法: `git worktree add --detach` で疑似ブランチを 4 本作り、`tests/provider_expect_sim.mjs` で別 family の関数を 1 件ずつ足した。新方式の基点は本ブランチの HEAD (`4e61b24bb`)、旧方式の基点は origin/main (`32e6f8b46`)。

- 新方式: `provider_expect/pe901.json` (`general.getRecPPB`) と、`fl_engine.c` の screen 側・`fl_mock.mjs` の screen 行の前に実装行を足す / `provider_expect/pe902.json` (`transport.continuousMove`) と、`fl_engine.c` の channels 側・`fl_mock.mjs` の channels 行の前に実装行を足す。
- 旧方式: 同じ 2 関数を `provider_check.mjs` 本体に書く (`const` 1 行・OR 連鎖の 1 語・件数 assert の 2 語)。

`git merge-tree --write-tree --name-only <A> <B>` の結果:

| 方式 | 基点 | merge-tree rc | 競合ファイル | 競合ハンク (`<<<<<<<` 数) |
|---|---|---|---|---|
| 新 (`provider_expect/`) | 4e61b24bb | 0 | なし | 0 |
| 旧 (本体編集) | 32e6f8b46 | 1 | `tools/python/tests/provider_check.mjs` | 2 |

- 新方式の結果の tree には `provider_expect/` が 33 ファイル (31 + 疑似 2) 入り、`provider_check.mjs` に競合マーカーは無い。
- 取り込み前の基点 (`4f256b0be`・`592f4c8e0`) でも同じ結果 (新 rc 0・0 ハンク / 旧 rc 1・2 ハンク)。
- 旧方式の 2 ハンクの中身: (1) `const` 行の挿入 (`let impl` の直前)、(2) OR 連鎖の行 (`|| peNNN.has(id)` の追加位置が両方とも末尾)。件数行は 2 本とも同じ値 (187/248) に置いたため競合しなかった。実際の PR は件数が異なるので、件数行も 3 つ目のハンクになる (本測定の下限)。
- C・mock の疑似実装は**ビルドしていない** (競合の有無だけを測る)。同じ family・同じ行への実装追加の競合は**未測定** (§7)。

## 6. 変更内容

| ファイル | 変更 |
|---|---|
| `tests/provider_check.mjs` | 集合定義 (約 60 行) を `provider_expect/` の読込 (約 10 行) に置換。手書き件数 (`186`/`249`) を導出に変更。内訳コメントの 1 行を削除 |
| `tests/provider_expect/*.json` (31 件) | 移した集合。`tag`・`refs`・`note`・`functions` |
| `tests/provider_impl_dump.mjs` | 新規。実装集合を出す (§3) |
| `tests/provider_expect_sim.mjs` | 新規。競合実測の疑似ブランチ作成 (§5) |
| `tools/python/BRIDGE.md` §5 D | 運用の規約 (関数を足す PR は `provider_expect/<tag>.json` を 1 つ足す) |
| `tools/python/REPORT.md` 111 行 | 古い件数 (`60/375`) を、件数の正本 (本 REPORT) への参照に置換 |
| `docs/DOC_MAP.md` | `tools/python/REPORT_PY280.md` の登録 |

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 同じ family・同じ行への `fl_engine.c`・`fl_mock.mjs` の追加の競合は未測定 (§5 の疑似は別の挿入位置) | 別 PR 同士で C・mock の競合が残り得る。issue 範囲外 | 本 issue の範囲外 (issue 本文の『範囲外』)。残れば PM へ |
| `pe100.json` の `note` が空 (元の const に説明コメントが無い。出典未確認) | 出典の追跡だけ | PR 本文の未解決表 (子 issue は作らない) |
| 旧方式の open PY PR の追随 (`origin/main` の取込みと集合の移行) | 本 PR の merge 後に各 PR が 1 回の解消を要する | PM (issue 本文の『進め方』どおり) |
