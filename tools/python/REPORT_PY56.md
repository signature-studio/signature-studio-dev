# PY-56 (#1934): playlist 38 関数の逆アセンブル確定 (部分: selectTool・scrollTo)

親: #1671 (PY-44)。前段の所属確定は `tools/python/REPORT_PY44.md`。

## 結論

- 38 関数のうち、本 run で確定したのは **2 件** (`selectTool` 0xd58670・`scrollTo` 0xd58490) のみ。
- 残り 36 件の戻り値・範囲 code は未確定。子 issue (下記「未解決」) に分割した。
- `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/provider_check.mjs` は変更していない。
  確定した 2 件も C 実装は行っていない (範囲 code の根拠が未確定のため。推測では実装しない)。

## 測定

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C` で展開。
  実測 5.5 秒 (user 3.5 s / sys 7.1 s)。load 測定なし。
- 対象: `extracted/block00031_PE.bin` (`flstudio_win64_26.1.7.5653.exe` と同梱)。
- 解析補助: `analysis/flapi/pe_disasm.py` (capstone + pefile)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- 測定 commit: 本 PR の commit (`git log -1 --oneline` 参照)。解析に使ったのは `00083cdb` (main) 時点の表。

## 確定 1: `selectTool` (0xd58670)

| 項目 | 根拠 (VA) |
|---|---|
| 引数書式 | PyArg 書式文字列 `"i"` (`0xd58784` の `lea rdx,[rip+0xd5]` 先の文字列 `i\0trackCount\0...`)。引数は **int 1 個**。 |
| 引数名 | 表は sig=null。書式が `i` の 1 引数 → `index:int` 相当 (名前は表に無い)。 |
| 呼び出し先 | 実装本体 `0xd585f0`。`call qword ptr [rax+0x98]` で ready 判定後、`0 <= index <= 10` (`cmp rax,0xa; jg`) の範囲チェック。 |
| 戻り側の状態 | `[rbx+0x60]` に `0`(成功) / `-2`(初期値 `0xfffffffffffffffe`) / `-4`(`0xfffffffffffffffc`・範囲外または不成立)を書く。 |
| 未確定 | `-2`/`-4` と repo の error code (`RANGE`/`WRONG_PARAM`) の対応。`call 0xe4f1a0` の意味 (ツール選択の本体) |

- 表の戻り型 (`(不明)`) は本 run でも未確定。`[rbx+0x60]` は内部状態で、Python 側の戻り値そのものかは未確認。
- **REPORT_PY34 で指摘した「書式 `i` と flapi `() -> None` が合わない」は解消**。書式は `i` で確定 (1 引数)。
  flapi 側の sig が null であることは変わらない。

## 確定 2: `scrollTo` (0xd58490)

| 項目 | 根拠 (VA) |
|---|---|
| 引数書式 | PyArg 書式文字列 `"iiii"` (`0xd585c4` 付近)。引数は **int 4 個**。 |
| 引数名 | 表は `a, b, c, d (int)`。書式上も int 4 個で一致。 |
| 引数の受け渡し | `[rbp+0xac]`・`[rbp+0xa8]`・`[rbp+0xa4]`・`[rbp+0xa0]` に受け、`[rsp+0x20..0x38]` へ詰め直して `0xd843d0` を呼ぶ (4 引数を順に渡す)。 |
| 実装本体 | `0xd58210`。`call qword ptr [rax+0x98]` の判定後、`[rsi+0x50]` (非 0 で処理) を見る。 |
| 未確定 | `a/b/c/d` の**意味** (スクロール先の座標か・時間か・ビュー種別か)。本 run では `0xd843d0` 以下を読んでいない。 |

- 表の `a/b/c/d` は名前だけで意味が無い。意味は `0xd843d0` の 4 引数の使われ方から決める必要があり、本 run の範囲外。

## 未確定 36 件 (今回未着手)

REPORT_PY44 の表の残り 36 件 (`selectTool`・`scrollTo` を除く) は、戻り値・範囲 code・引数の意味が未確定。
推測で実装しない (規範)。子 issue で逆アセンブルから決める。

## 検証

- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_disasm.py 0xd58670 60` / `0xd58490 40`。
  foreground・数秒。書式文字列は `pefile` で `.rdata` から直接読んだ (コマンドは PR 本文に記載)。
- コード差分: 本 PR は `tools/python/REPORT_PY56.md` と `tools/python/REPORT_PY44.md`・`docs/DOC_MAP.md` の REPORT 索引行のみ。
  C provider・mock・テストは無変更のため、`all_tools.mjs` 48/48 は再測定しない (`docs/WORKFLOW.md` §6)。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 36 関数の戻り値・範囲 code・引数の意味 (playlist 表 42 件のうち確定 2 件を除く) | C 実装が決まらない | 子 issue #1971 (PY-57) |
| `selectTool` の `-2`/`-4` と error code の対応・`0xe4f1a0` の意味 | `selectTool` の C 実装が決まらない | 子 issue #1971 (PY-57) |
| `scrollTo` の `a/b/c/d` の意味 (`0xd843d0` の引数の使われ方) | `scrollTo` の C 実装が決まらない | 子 issue #1971 (PY-57) |
| `fl_engine.c` 実装・`provider_check.mjs` 件数更新・mock 差分 0・`all_tools` 48/48 | 受入条件の残り | 子 issue #1971 (PY-57) |
