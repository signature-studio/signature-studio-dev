# PY-116 (#2952): flapi 表の kwlist 無し引数の書式を wrapper の逆アセンブルで照合し、名前の確定可否を判定する

親: #2927。前段: `tools/python/REPORT_PY70.md` (引数個数の一致)・`tools/python/REPORT.md` §12 (kwsig 復元)。
既知類型との関係: 該当なし (lift 作業ではない。書式文字列と wrapper の引数設定の照合)。

## 結論

- **書式は表のとおり。`screen.addTextLine` の必須 5 は正しい。** 書式文字列 `siiii` は wrapper が `rdx` に渡す文字列そのもの (`0xd7acf8` のバイト列を確認)。抽出 (`analysis/flapi_kwargs.py` の `lea` 解析) は誤っていないので、抽出は直していない。stub の 2 個 (`text, line`) が食い違う。
- **wrapper は書式より 1 個多く出力ポインタを渡す** (`screen.addTextLine`・`screen.addMeter` の 2 件、§2)。書式が消費するのは 5 個で、6 個目は解析されない。表の 5 は解析個数どおりなので変えない。6 個目の意味は実機でしか確定できず、未解決 (§5)。
- **名前は新たに 0 件確定。** `flags=1` の引数名はバイナリに無い (kwlist は `flags=3` だけが持つ)。表の名前は stub 由来の位置だけ。残りは `arg{i}` のまま (§3・未確定 42 位置)。`analysis/flapi/flapi_table.json` は変更していない。
- **受入条件 `node tests/sig_arity_probe.mjs`: そのファイルは repo に無い** (`git ls-files` と全文検索で 0 件)。代替は `python3 analysis/flapi/sig_arity_check.py` (before/after 同一) と `python3 tests/kwsig_check.py` (本 PR で照合を追加)。

## 測定

- 測定 commit: `f6f0bbe3` (コード変更の最後の commit。base は `origin/main` `2899945e`)。
- 差分 0 の証跡: `git diff f6f0bbe3 HEAD -- tools/python/analysis tools/python/tests` の出力は 0 行 (本 REPORT と `docs/DOC_MAP.md` の commit だけが増える)。
- 環境: GitHub Actions runner (4 コア)。測定時の load average は 20:41 時点で 1 分 0.10・5 分 0.21 (`uptime`)。
- 素材: `fl-win64` を `tar --zstd -xf fl-win64.tar.zst --wildcards '*block00031_PE.bin' '*block24429_DATA.bin' '*block24430_DATA.bin' '*block25159_DATA.bin' '*block24618_DATA.bin'` で `FL_WIN64_DIR=<fl-win64 展開先>` に展開 (`toolchain-emsdk` は本検証の対象外)。`tools/python/fetch_inputs.sh` で stubs と DATA を `work/` に配置 (gitignore)。

| 検証 | 実行 | 結果 |
|---|---|---|
| 生成器の決定性 | `FL_WIN64_DIR=… python3 analysis/flapi_kwargs.py` を 2 回 | `flapi_kwargs.json` の md5 が 2 回で一致。`flapi_table.json` は不変 |
| 書式と出力ポインタ数の照合 | `python3 tests/kwsig_check.py` (本 PR で (11) を追加) | OK (0.04 s)。照合 303 件・不一致 2 件 (`screen.addMeter` 5/6・`screen.addTextLine` 5/6、既知) |
| 表の再生成 | `bash tests/flapi_table_check.sh` | PASS。再生成 3 ファイル差分 0/3・`win_pair_verified` 388 件・ネガコン 6/6 (2.3 s) |
| bind | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6122 ケース・misbind 0・mismatch 0) |
| 引数個数 | `python3 analysis/flapi/sig_arity_check.py <HEAD の表> analysis/flapi/flapi_table.json` | before 一致 249・不一致 24、after 同じ。署名の個数が変わった関数 0 件 (0.02 s) |
| 受入条件の名指し検査 | `node tests/sig_arity_probe.mjs` | 実行不可 (ファイル無し) |

## 1. 再確認した書式 (wrapper の逆アセンブル)

`PyArg_Parse*` の呼出し直前 (前の `call` より後) に渡す非 0 の出力ポインタ数 (`outs`) と、書式が消費する数 (`ptrs`) を全 303 関数で照合した。`outs`・`ptrs` は `flapi_kwargs.json` に追加した (表の `kwsig` は変えていない)。

| 関数 (fn_va) | 書式 | 表 (必須/最大) | ptrs | outs | 判定 |
|---|---|---|---|---|---|
| screen.addTextLine (0xd7abb0) | `siiii` | 5/5 | 5 | **6** | 表は正。§2 |
| screen.addMeter (0xd7ada0) | `iiii\|i` | 4/5 | 5 | **6** | 表は正。§2 |
| screen.drawText (0xd7bcb0) | `isiiii` | 6/6 | 6 | 6 | 一致 |
| screen.drawRect (0xd7af40) | `iiiii` | 5/5 | 5 | 5 | 一致 |
| screen.eraseRect (0xd7bec0) | `iiii` | 4/4 | 4 | 4 | 一致 |
| screen.findTextLine (0xd7b2d0) | `iiii` | 4/4 | 4 | 4 | 一致 |
| screen.removeTextLine (0xd7ad00) | `i\|i` | 1/2 | 2 | 2 | 一致 |
| screen.animateText (0xd7c460) | `i` | 1/1 | 1 | 1 | 一致 |
| screen.blank (0xd7c600) | `ii` | 2/2 | 2 | 2 | 一致 |
| screen.unBlank (0xd7c740) | `i` | 1/1 | 1 | 1 | 一致 |
| screen.setScreenActiveCounter (0xd7c8c0) | `i` | 1/1 | 1 | 1 | 一致 |
| playlist.muteTrackLock (0xd565c0) | `i\|i` | 1/2 | 2 | 2 | 一致 |
| playlist.selectTrack (0xd56b60) | `i\|i` | 1/2 | 2 | 2 | 一致 |

全 303 関数のうち 301 件が一致 (残り 2 件が上の 2 行)。

## 2. screen.addTextLine / screen.addMeter の 6 個目

- **addTextLine (0xd7abb0)**: `PyArg_Parse*(args, "siiii", &[rbp+0x80], &[rbp+0x9c], &[rbp+0x98], &[rbp+0x94], &[rbp+0x90], &[rbp+0x8c])`。書式は 5 単位 (`s` + `i`×4) なので、解析されるのは最初の 5 個。6 個目 `&[rbp+0x8c]` は呼出し前に一度も書かれず、呼出し後に `mov r9d, [rbp+0x8c]` で読まれる (未初期化)。
- **addMeter (0xd7ada0)**: `PyArg_Parse*(args, "iiii|i", …)` の 6 個目 `&[rbp+0x58]` は関数の先頭で `mov dword [rbp+0x58], 0` により 0 に初期化され、解析されない。後段 `mov eax, [rbp+0x58]; mov [rsp+0x28], eax` で 0 のまま渡る。
- **判定**: 表の必須・最大 (5 と 4/5) は PyArg の解析個数どおりで、これを正とする。6 個目は解析されない余剰ポインタで、表の個数には入れない。addTextLine の 6 個目が未初期化のままなのは FL 側の不整合 (書式の 1 個不足か、呼出しの余剰か) で、どちらかは実機の呼出しでしか確定できない (§5)。
- 2 件の不一致は `kwsig_check.py` (11) で固定した。これ以外の不一致が出たら検査が落ちる。

## 3. 名前の確定可否

- **新たに確定した名前: 0 件。** 理由: `flags=1` は `PyArg_ParseTuple` 系で書式だけを受け、kwlist (名前) を持たない。PE 内の文字列は説明文だけ (`PyMethodDef` の doc 例: "Add text line")。mac の raw 表 (`analysis/flapi/raw_mac_*.json`) も doc だけで、引数名は無い。
- **表に残っている名前** (stub 由来・変更なし): `screen.addTextLine` の `text`・`line` (1〜2 位置)、`playlist.muteTrackLock`・`playlist.selectTrack` の `index` (1 位置)。
- **未確定の位置 (`arg{i}` のまま)**: 下表。issue の範囲は 42 位置。`flags=1` 全体では 36 関数・73 位置 (`ilmcp` 15・`screen` 34・`patterns` 8・`mixer` 6・`general` 3・`playlist` 3 ほか)。

| 関数 | 未確定の位置 | 関数 | 未確定の位置 |
|---|---|---|---|
| screen.addMeter | arg1〜arg5 | screen.findTextLine | arg1〜arg4 |
| screen.drawRect | arg1〜arg5 | screen.removeTextLine | arg1〜arg2 |
| screen.drawText | arg1〜arg6 | screen.animateText・unBlank・setScreenActiveCounter | arg1 |
| screen.eraseRect | arg1〜arg4 | screen.blank | arg1〜arg2 |
| screen.addTextLine | arg3〜arg5 | playlist.muteTrackLock・selectTrack | arg2 |
| mixer.getPluginMixLevel・getPluginMuteState・setCurrentTempo | arg1〜arg2 | | |

- **表へ `arg{i}` を入れない理由**: `sig.params` に名前を入れると `fl_api.bind` が `arg1=` のような名前での kw 呼出しを受け入れてしまう (`src/fl_api.py` の `_make` は `sig.params` の名前を kw 名に使う)。kwlist 無しの関数は今も kwargs を拒否する前提で、それを変える挙動変更は本 issue の範囲外。そのため表の変更は 0 件。

## 4. 同定の前提 (未確認の点)

- 呼出し先が `PyArg_ParseTuple` であることは PE から確認できていない。PE の import 表に `PyArg_Parse*` は無く、文字列も無い (実行時に解決される)。`flags=1` (VARARGS のみ) で `rdx` が書式である点は `REPORT.md` §12 と同じ前提 (PY-9b)。
- 書式の消費数は Python C API の規則 (単位 1 つ = ポインタ 1 個、`#`・`!`・`&` は +1、`:`・`;` 以降は無視) で数えた。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `screen.addTextLine` の 6 個目 (未初期化) と `screen.addMeter` の 6 個目 (0 固定) の意味 | 表の個数 5 は解析個数どおり。6 個目の値が呼出しにどう効くかは未確定 | #2927 (親) に判断を依頼 |
| 未確定の 42 位置 (issue 範囲) と 73 位置 (flags=1 全体) の引数名 | 名前付き呼出しは今も不可。名前を決めるには FL の公式資料か実機の呼出しが要る | #2927 (親) に判断を依頼 |
| 受入条件 `node tests/sig_arity_probe.mjs` | 対象ファイルが repo に無い | PM が受入条件を直す (代替検査は本 PR で実行済み) |
| 呼出し先の関数名 (§4) | PE に名前が無い | 未確認。PY-9b の前提を踏襲 |
