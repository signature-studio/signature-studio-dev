# PY-280 (#3978): provider_check.mjs の per-PR 期待集合を provider_expect/ に移す

既知類型との関係: 該当なし (lift 作業ではない)。起動・GUI に関わらないため製品 KPI は対象外。

## 0. 結論

- `tests/provider_check.mjs` の per-PR 期待集合を `tests/provider_expect/<tag>.json` (1 PR = 1 ファイル) に移した。移行時 **31 集合・116 関数**。main 取り込み後の現 head では **35 ファイル・134 関数** (`provider_expect/` の内訳は pe* 32 + pl61・stub41・stub89)。本体に残るのは mcp・dev・mig の 3 集合と検査ロジックだけ。
- 手書きの件数 assert は、期待集合からの導出 (`impl === |和集合|`・`unimpl === ids.length - impl`) に変えた。表に無い id は FAIL する。
- 現 head (測定 commit `780159860`) の実測: 実装 **204** / 未実装 **231** / 全 435。`origin/main` (`0555fa7c2`) の実装集合と `provider_impl_dump.mjs` の出力は **差分 0 行**。`provider_check.mjs` PASS、`FL_ENGINE=wasm all_tools.mjs` は **48/48 ok**。
- 競合の実測 (現 head 基準・疑似ブランチ 2 本): 新方式 **0 件** (`merge-tree` rc 0)。旧方式 (同じ 2 本を `provider_check.mjs` 本体へ書いた場合) は **3 ファイル・うち `provider_check.mjs` に 2 ハンク** (rc 1)。

## 1. 測定 commit と差分の証跡

- 測定 commit: **`780159860`** (`origin/main` (`0555fa7c2`) の取り込み merge)。REPORT の commit 自体は `tools/python` の `*.md` 以外を変えない。
- `git diff 780159860 HEAD -- tools/python ':!*.md'` の出力は **0 行** (測定後に変えたのは本 REPORT と PR 本文だけ)。
- 直前の code commit `07a6880ab` (`provider_expect_sim.mjs` の old モード修正) の後、`origin/main` 取り込みで `tools/python/analysis/flapi/pe_py183_probe.py` (解析用 probe・テストから呼ばれない) が 30 行増えた。このため全測定を `780159860` で取り直した。

## 2. 移行の対象 (実測)

| 項目 | 値 | 数え方 |
|---|---|---|
| 移行時の集合 | 31 (commit `4f256b0be`) | `provider_check.mjs` の `const X = new Set([...])` のうち mcp・dev・mig 以外 |
| 移行時の関数 | 116 | 集合の要素の総数。重複 0 |
| 現 head の集合 | 35 | 移行時 31 + main 取り込みで追加された pe128・pe135・pe206・pe215 (`git diff --diff-filter=A 4f256b0be HEAD`) |
| 現 head の関数 | 134 | 集合の要素の総数。重複 0 (`node` で確認) |
| 本体に残した集合 | 3 (mcp は表から導出 60、dev 5、mig 5) | issue の指定どおり |
| 削除した行 | 集合定義 (説明コメント込み)・OR 連鎖の 1 行・内訳コメントの 1 行 | `git diff 592f4c8e0 4f256b0be -- tools/python/tests/provider_check.mjs` |
| 説明コメント | JSON の `note` に保持。`refs` は `note` 内の `#N` を抽出 | `pe100` だけ元の const に説明コメントが無く、`note` は空 (出典は未確認) |

issue 本文の『33 個の const peNNN』は概数。移行時の実測は 31 集合 (pe* 28 + 3)。

## 3. 移行前後の実装集合 (受入 3)

`tests/provider_impl_dump.mjs` (新規・実装 id を 1 行ずつ出し、末尾に件数行を出す) で比べた。

| 時点 | 件数行 | 差分 |
|---|---|---|
| `origin/main` (`0555fa7c2`・main 側の手書き集合 `provider_check.mjs`) | `implemented=204 unimplemented=231 total=435` | — |
| 現 head (`780159860`) | `implemented=204 unimplemented=231 total=435` | `diff` 0 行 |

- 現 head の `provider_check.mjs` の出力: `{"functions":435,"implemented":204,"unimplemented":231,"mcp_static":60,"PASS":true}`。
- 件数は期待集合の和集合 (mcp 60 + dev 5 + mig 5 + JSON 134 と重複除去) と一致する (`assert.equal(impl, new Set([...mcp, ...dev, ...mig, ...pe]).size)` が通る)。
- 注: `origin/main` 側には `provider_impl_dump.mjs` が無いため、現 head の同ファイルを `origin/main` の worktree にコピーして実行した。

## 4. 検証 (受入 6)

環境: `nproc` 4。測定時 load average (uptime) 0.08 / 0.56 / 0.45 (測定開始時)。

| 検証 | コマンド | 結果 (現 head `780159860`) |
|---|---|---|
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0 |
| 素材 | `fl-win64`・`toolchain-emsdk` の `.tar.zst` を `tar --zstd -xf` で展開 (展開先は runner の一時 dir) | fl-win64 8.5 s・emsdk 3.7 s |
| 入力配置 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` | rc 0 |
| CPython wasm | `EMSDK=$RUNNER_TEMP/emsdk-x/emsdk bash build_cpython_wasm.sh` | rc 0。直前の commit で同じ成果物が既にあり増分扱いのため 1 s。clean ビルドの時間は**本測定では未取得** (前回 3 min 20 s は別 commit の clean 測定) |
| flpy リンク | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 (4 s) |
| 期待集合 (本件) | `node tests/provider_check.mjs` | **PASS**・`{"functions":435,"implemented":204,"unimplemented":231,"mcp_static":60,"PASS":true}` |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | **48/48 ok**・soft_error 0・raised 0・no_args 0・host_calls 37425・callback 往復 true |
| device | `node tests/device_diff.mjs` | PASS (calls 21・diffs 0) |
| 実装集合の一致 | `provider_impl_dump.mjs` を `origin/main` (`0555fa7c2`) と現 head で実行して比較 | 差分 0 行 (件数 204 / 231) |

### ネガティブコントロール (受入 6 の検査が効くことの確認・現 head で実施)

| 操作 (`provider_expect/pe100.json` を一時的に変更) | 結果 |
|---|---|
| `channels.getStepParam` を集合から削除 | **FAIL**: `AssertionError [ERR_ASSERTION]: 実装済みのはず` 系 (実装済みの関数が期待集合に無い) |
| 表に無い `channels.noSuchFn` を追加 | **FAIL**: `AssertionError: provider_expect に表に無い関数 id がある` |
| 両方を元に戻す | PASS (`implemented 204`)。`pe100.json` は元のバイト列に戻した |

## 5. 競合の実測 (受入 4・現 head 基準)

方法: `git worktree add --detach` で疑似ブランチを 4 本作り、`tests/provider_expect_sim.mjs` で別 family の関数を 1 件ずつ足した。新方式の基点は現 head (`780159860`)、旧方式の基点は `origin/main` (`0555fa7c2`)。

- 新方式: `provider_expect/pe901.json` (`general.getRecPPB`) と、`fl_engine.c` の screen 側・`fl_mock.mjs` の screen 行の前に実装行を足す / `provider_expect/pe902.json` (`transport.continuousMove`) と、`fl_engine.c` の channels 側・`fl_mock.mjs` の channels 行の前に実装行を足す。
- 旧方式: 同じ 2 関数を `provider_check.mjs` 本体に書く (`const` 1 行・OR 連鎖の 1 語・手書き件数 assert の 2 語)。

`git merge-tree --write-tree --name-only <A> <B>` の結果:

| 方式 | 基点 | merge-tree rc | 競合ファイル | `provider_check.mjs` の競合ハンク |
|---|---|---|---|---|
| 新 (`provider_expect/`) | 780159860 | 0 | なし | 0 |
| 旧 (本体編集) | 0555fa7c2 | 1 | 1 ファイル (`tools/python/tests/provider_check.mjs`) | 2 |

- 旧方式の競合ファイルは `provider_check.mjs` の 1 つだけ (`merge-tree --name-only` の結果)。2 ハンク: (1) `const` 行の挿入 (`let impl` の直前)、(2) OR 連鎖の行 (`|| peNNN.has(id)` の追加位置が両方とも末尾)。件数行は 2 本とも同じ置換先のため、この疑似では競合していない (実際の PR は件数が異なるため、件数行も競合し得る = 本測定の下限)。
- C・mock の疑似実装は**ビルドしていない** (競合の有無だけを測る)。同じ family・同じ行への実装追加の競合は**未測定** (§7)。

## 6. 変更内容

| ファイル | 変更 |
|---|---|
| `tests/provider_check.mjs` | 集合定義 (約 60 行) を `provider_expect/` の読込 (約 10 行) に置換。手書き件数を導出に変更。内訳コメントの 1 行を削除 |
| `tests/provider_expect/*.json` (移行時 31 件・現 35 件) | 移した集合。`tag`・`refs`・`note`・`functions` |
| `tests/provider_impl_dump.mjs` | 新規。実装集合を出す (§3) |
| `tests/provider_expect_sim.mjs` | 新規。競合実測の疑似ブランチ作成 (§5)。`old` モードの件数行の置換を現本体に合わせた (`07a6880ab`) |
| `tools/python/BRIDGE.md` §5 D | 運用の規約 (関数を足す PR は `provider_expect/<tag>.json` を 1 つ足す) |
| `tools/python/REPORT.md` 111 行 | 古い件数 (`60/375`) を、件数の正本 (本 REPORT) への参照に置換 |
| `docs/DOC_MAP.md` | `tools/python/REPORT_PY280.md` の登録 |

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 同じ family・同じ行への `fl_engine.c`・`fl_mock.mjs` の追加の競合は未測定 (§5 の疑似は別の挿入位置) | 別 PR 同士で C・mock の競合が残り得る。issue 範囲外 | 本 issue の範囲外 (issue 本文の『範囲外』)。残れば PM へ |
| `pe100.json` の `note` が空 (元の const に説明コメントが無い。出典未確認) | 出典の追跡だけ | PR 本文の未解決表 (子 issue は作らない) |
| 旧方式の open PY PR の追随 (`origin/main` の取込みと集合の移行) | 本 PR の merge 後に各 PR が 1 回の解消を要する | PM (issue 本文の『進め方』どおり) |
