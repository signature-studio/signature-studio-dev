# tools/python REPORT: PY-152 arrangement 残り 8 件の PE 確定と C provider 実装 (#2983, 親 #2832)

> 正本: `tools/python/REPORT_PY87.md` (PE 解析の手順・方式)。本付録は PY-152 の実測のみ。
> 番号: 題名の `[PY-152]` (#2983) に揃えた。`REPORT_PY119.md` は #2980 (ui 6 件) の別 REPORT で、番号が衝突していたため本 REPORT を改名した。

## 結論

- 対象 8 件のうち **6 件** (`currentTime`・`addAutoTimeMarker`・`jumpToMarker`・`liveSelection`・`selectionClear`・`selectionSet`) を mock と C に実装した。呼出し構造と PyArg 書式は PE で確定した。個数は flapi 表 (fl_table) に合わせた暫定。mock と C の差分は 0 (`tests/arrangement_diff.mjs` 25 呼出し)。
- **`jumpToMarker` は PE と個数が不一致**。PE の書式は `i|i` (必須 1)、表は必須 2。mock と C は表どおり必須 2 にしている (既定・挙動は変えない)。PE (1) に寄せるかは **PM agent の判断待ち** (下の未解決表)。
- **値と副作用は未確定**。`currentTime` は仮置き 0。選択・マーカーの 5 件は呼出し経路 (共通ラッパー `0xd843d0` とコールバック) まで確認したが、コールバックの中身は未同定のため状態を変えず、引数検査だけ行う。
- 変換スロット `0x15e4280` の先は **`PyLong_FromLong`** と同定した。`long` は Win64 では 32 bit なので、`-1` は Python の int `-1` になる。
- 残り 2 件 (`currentTimeHint`・`getMarkerName`、str を返す) と、副作用・引数個数の確定は子 issue に分けた (下表)。
- 前提の不一致: #2983 は #2832 (PY-96) の 4 件 (`selectionStart`・`selectionEnd`・`liveSelectionStart`・`selectionIsActive`) を「確定済み」としているが、main には `REPORT_PY96.md` も該当する mock・C 実装も無い。本 PR はそれに触れない。

## 手段

- 素材: `$ARTIFACTS_DIR` の `fl-win64.tar.zst` から `extracted/block00031_PE.bin`・`block24429_DATA.bin`・`block24430_DATA.bin`・`block24618_DATA.bin`・`block25159_DATA.bin` を `tar --zstd -xf` で展開し、`FL_WIN64_DIR=<展開先>` とした。`toolchain-emsdk` は `$ARTIFACTS_DIR` に実在したが、ビルドは runner 既存の emsdk (`EMSDK_DIR` 既定) で行った。
- ハンドラ探索: `analysis/flapi/pe_handler_probe.py` (entry・fn・flags・PyArg 書式)。関数本体は `ret` まで逆アセンブルして人手で読んだ (手動同定)。その出力を作った補助スクリプトは未コミットで、`$RUNNER_TEMP` 配下にあった。下の「本体の要点」は再現コマンドを持たない手動同定の値である。
- 呼出し先の同定: `analysis/flapi/pe_rip_refs.py` でスロットの参照を列挙し、書込み元の前後で `lea rdx` が指す名前を読んだ。スロットの値は `.data` の初期値 (cell の番地)、cell の中身は `.bss` で実行時に埋まる。cell の名前は UTF-16 の初期化文字列 (`0x4235f0` の GetProcAddress 相当の呼出し) として `.text` に残っていた。

## PE 確定 (対象 8 件 + liveSelectionStart)

| 関数 | entry | fn | flags | 引数 (PyArg 書式) | 戻り | 本体の要点 (手動同定) |
|---|---|---|---|---|---|---|
| currentTime | 0x151dcd0 | 0xd78520 | 1 | `i` (snap) | int (`PyLong_FromLong`) | `0xd77e20()` → `0xe43fa0(obj, snap==1)` の int を変換 |
| currentTimeHint | 0x151dcf0 | 0xd785a0 | 1 | `ii\|ii` (mode, time, setRecPPB, isLength) | str (`PyUnicode_FromString`) | setRecPPB の既定値 = `[[0x15e4558]]+0xb20` の dword。`0xe4b8b0` で文字列を作る |
| getMarkerName | 0x151dc50 | 0xd78030 | 1 | `i` (index) | str | `[0x15e35c8]` の obj に `0xe53c90(obj, &out, index, 1)`、`0x414000` で char* にして変換 |
| addAutoTimeMarker | 0x151dc70 | 0xd781e0 | 1 | `is` (time, name) | None | `0xd78c80` で engine object → `0xd843d0` (cb `0xd78130`) |
| jumpToMarker | 0x151dc30 | 0xd77eb0 | 3 | `i\|i` kwlist (delta, select) | None | `0xd843d0` (cb `0xd77e50`) |
| liveSelection | 0x151dc90 | 0xd783c0 | 1 | `ii` (time, stop) | None | `0xd843d0` (cb `0xd78360`)、末尾引数 bool 1 |
| selectionClear | 0x151dd70 | 0xd787b0 | 4 (NOARGS) | なし | None | `0xd843d0` (cb `0xd78750`) |
| selectionSet | 0x151dd90 | 0xd78940 | 3 | `ii\|iii` kwlist (selStart, selStart, selectNotes, updateSongLoop, scroll) | None | `0xd843d0` (cb `0xd78880`) |
| liveSelectionStart (#2832 の範囲の確認) | 0x151dcb0 | 0xd78500 | 1 | PyArg を通さない (引数を読まない) | int | `0xd77e20()+0xd74` の dword を変換 |

- 5 件の書込み系は、共通の `0xd843d0` に「コールバック」を渡す形。各コールバックは先頭で `[0x15e4790]` の vtable `+0x98` を呼び、真のときだけ `0xe43ff0`・`0xe43d30`・`0xe7e290`・`0xe546a0`・`0x1180ef0` などを呼ぶ。これらの中身は未同定。
- 全 8 件の先頭は `0xd78c80` で self → engine object (`mov rbx, [rax]`)。`0xd77e20` の object は未同定。

## 変換スロットの同定

| スロット (VA) | `.data` の初期値 (cell) | cell への書込み元 | 初期化文字列 (UTF-16) | 用途 |
|---|---|---|---|---|
| 0x15e4280 | 0x16b8298 | 0xc396c5 | PyLong_FromLong | int 変換 (currentTime・liveSelectionStart。bool 戻りの 4 件も同じ slot を使う) |
| 0x15e3d50 | 0x16b82c0 | 0xc39761 | PyUnicode_FromString | str 変換 (currentTimeHint・getMarkerName) |
| 0x15e1e58 | 0x16b82f0 | 0xc397fd | PyArg_ParseTuple | flags 1 の引数解析 |
| 0x15e45a8 | 0x16b82f8 | 0xc39817 | PyArg_ParseTupleAndKeywords | flags 3 の引数解析 |

- **負値**: 変換は `mov ecx, eax` (32 bit) で渡す。Win64 の `long` は 32 bit なので、未選択の `-1` は Python の int `-1` になる (PE 上の根拠は変換関数の型のみ。実機の戻り値は未実測)。
- **int と bool**: `PyLong_FromLong` 1 本で返すため、PE からは bool 戻りの関数 (PY-87 の `general.getUseMetronome`・`getPrecount`・`transport.isPlaying`) と int 戻りを区別できない。Python 上で `True` になるか `1` になるかは、この経路からは確定しない (子 #B)。

## 実装の範囲 (6 件)

- `provider/fl_engine.c` と `host/fl_mock.mjs` で、同じ個数・型検査と同じ戻り値に揃えた。
- 個数・型は `provider/gen/fl_table.c` (stub 由来) の値で dispatch (`fl_dispatch.c`) が検査する。`selectionClear`・`selectionSet` は `np = -1` のため handler の `NARGS` で検査する。
- 表と PE の書式の差: `jumpToMarker` は個数 (表 2・PE 1)。`liveSelection` は型 (表 `ib`・PE `ii`)。`fl_dispatch.c` の `type_ok` は `i`・`b` のどちらも int と bool を受理するので、この型差は挙動に出ない。
- `currentTime` は仮置きの状態 `arr_time` (mock の `st.arrTime`) を返す。値は未実測で、既定値 0 は PE から決めていない。
- 選択・マーカーの 5 件は副作用を持たない。呼出しは mock の `record` (既存の呼出し記録) に残る。

## 検証

### PR 作成時 (`3a0f9b9a`)

測定 commit: `3a0f9b9a` (コードを変えた最後の commit。`feat(python): arrangement の PE 確定 6 件を mock と C provider に実装`)。測定は同 commit の作業ツリー (`git status` 空) で、`provider/build.sh` を再実行してから行った。runner の load average は測定開始時 0.20 (`uptime`)。

前提の生成物 (gitignore): `bash fetch_inputs.sh` (rc 0)・`bash build_cpython_wasm.sh` (rc 0、4 分 4 秒)・`FLPY_SKIP_TABLE=1 bash build_flpy.sh` (rc 0)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 89 | 0.93 秒 |
| `node tests/arrangement_diff.mjs` | calls 25、diffs 0、PASS | 0.05 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 89 / 未実装 346 / MCP 静的 60) | — |
| `node tests/general_diff.mjs` | calls 9、diffs 0、PASS | — |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425 (実装前と同値)、callback 往復 true | — |

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `arrTime` 既定値 (0) を 1 にすると、`node tests/arrangement_diff.mjs` は `AssertionError: arrangement 差分 3 件` で rc 1 (FAIL)。元に戻すと calls 25・diffs 0・PASS。

### main 取り込み後の再測定 (`4f1ca1a3`)

`origin/main` (`940c0d6a`) の取り込みで `tools/python` のコードが変わったため、上の `3a0f9b9a` の値はこの節の値で置き換える。測定 commit は `4f1ca1a3` (コードを変えた最後の commit。merge と、`provider_check.mjs`・`DOC_MAP.md` の競合解消)。測定は同 commit の作業ツリー (`git status` 空) で行った。runner の load average は測定開始時 0.74 (`uptime`)。

前提の生成物 (gitignore): `fetch_inputs.sh` (`FL_WIN64_DIR` = fl-win64 の展開先、rc 0)・`build_cpython_wasm.sh` (rc 0、4 分 26 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0。追跡済みの表を使い、表は再生成しない)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 92 | 1.5 秒 |
| `node tests/arrangement_diff.mjs` | calls 25、diffs 0、PASS | 1 秒未満 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 92 / 未実装 343 / MCP 静的 60) | 0.7 秒 |
| `node tests/general_diff.mjs` | calls 9、diffs 0、PASS | 1 秒未満 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425 (実装前と同値)、callback 往復 true | 2.4 秒 |
| `node tests/*_diff.mjs` (9 本) | 全て rc 0・diffs 0 (channels 161・device 8・ilmcp 32・midi_path 30・mixer 57・transport 7・ui 17 呼出し。arrangement 25・general 9 は上表と同じ) | 各 1 秒未満 |

ネガティブコントロール (`docs/WORKFLOW.md` §5) の再測定: `host/fl_mock.mjs` の 24 行目 `arrTime: 0,` を 1 に変えると、`node tests/arrangement_diff.mjs` は `AssertionError: arrangement 差分 3 件` で rc 1 (FAIL)。元に戻すと `git diff` は空で、calls 25・diffs 0・PASS。

取り込みで増えたコード差分 (`3a0f9b9a` から `4f1ca1a3` まで、`tools/python` の .md 以外):

```
$ git diff --stat 3a0f9b9a 4f1ca1a3 -- tools/python ':!*.md'
 17 files changed, 1900 insertions(+), 466 deletions(-)
```

測定 commit から HEAD までのコード差分 (`git diff 4f1ca1a3 HEAD -- tools/python ':!*.md'`) は空。この節の後の commit は REPORT の追記だけ。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `currentTimeHint`・`getMarkerName` (str 返し) の PE 確定と C 実装 (`0xe4b8b0`・`0xe53c90` の同定) | 2 件が未実装 | 子 #3041 [PY-143] |
| 選択・マーカーの副作用 (`0xd843d0` のコールバック 5 件・`0xd77e20` の object・`[0x15e4790]+0x98` のゲート) | 5 件の状態変化が未モデル | 子 #3043 [PY-144] |
| `jumpToMarker` の必須個数: PE は `i\|i` (必須 1)、flapi 表は必須 2 (stub 由来) | mock と C は表どおり必須 2 (現行、挙動は変えない)。PE (1) と不一致のまま。PM agent の判断待ち: jumpToMarker の必須個数を PE (1) に寄せるか、表 (2) のままか。既定案: 表どおり 2 | 子 #3043 [PY-144]・PM 判断 |
| `liveSelectionStart` の引数個数: PE は引数を読まず、表は 0 件 | 個数の確定は未了 | 子 #3043 [PY-144] |
| int と bool の区別 (`PyLong_FromLong` 1 本)、負値 `-1` の実機値 | PY-87 の bool 4 件の Python 型が未確定 | 子 #3043 [PY-144] |
| #2832 (PY-96) の 4 件が main に未実装 (`REPORT_PY96.md` も無い) | #2983 の前提が成立していない | 親 #2832 (PM 判断) |
