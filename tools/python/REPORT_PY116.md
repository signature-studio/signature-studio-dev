# PY-116 (#2952): flapi 表の kwlist 無し引数の書式を wrapper の逆アセンブルで照合し、名前の確定可否を判定する

親: #2927。前段: `tools/python/REPORT_PY70.md` (引数個数の一致)・`tools/python/REPORT.md` §12 (kwsig 復元)。
既知類型との関係: 該当なし (lift 作業ではない。書式文字列と wrapper の引数設定の照合)。

## 結論

- **書式は表のとおり。`screen.addTextLine` の必須 5 は正しい。** 書式文字列 `siiii` は wrapper が `rdx` に渡す文字列そのもの (`0xd7acf8` のバイト列を確認)。抽出 (`analysis/flapi_kwargs.py` の `lea` 解析) は誤っていないので、抽出は直していない。stub の 2 個 (`text, line`) が食い違う。
- **`plugins.getPresetCount` は kw 形式で呼ぶ flags=1 の 1 件。前版の誤りを直した (§3)。** 前版 (`a68d59f5`) は flags=1 を非 kw 形式と仮定し、書式を null・出力を 5 個と数えて、照合から黙って外れていた。修正後は書式 `i|ii`・出力 3 個・kwlist `index`・`slotIndex`・`useGlobalIndex` で、表 (必須 1・最大 3) と一致する。表の変更はこの関数の `kwsig` 1 件だけ。
- **wrapper は書式より 1 個多く出力ポインタを渡す** (`screen.addTextLine`・`screen.addMeter` の 2 件、§2)。書式が消費するのは 5 個で、6 個目は解析されない。表の 5 は解析個数どおりなので変えない。6 個目の意味は実機でしか確定できず、未解決 (§6)。
- **名前は新たに 0 件確定。** `getPresetCount` の 3 位置は、バイナリの kwlist が表の stub 名と一致することを確認した (表の名前は変えていない)。残りの `flags=1` は書式だけの呼出しで、名前はバイナリに無い (§4)。未確定の 42 位置は `arg{i}` のまま。
- **bind の挙動は変わらない。** `getPresetCount` の kwsig に `required`・`max` を足したが、20 通りの呼出しで修正前後の結果は同一 (§3)。`kwsig_bind_check.py` (103 関数・6122 ケース) は PASS のまま。
- **受入条件 `node tests/sig_arity_probe.mjs`: 未実行。** ファイルは `origin/main` (`46f5a007`・#2927 の commit) に入って repo にあるが、前提の provider wasm (`provider/build.sh`) に emsdk (`toolchain-emsdk`) が要り、この run の素材には無い (§6)。

## 測定

- 測定 commit: `273191b4` (コード変更の最後の commit。`origin/main` (`ae46c71a`) を取り込んだマージ)。その前の修正 commit は `cea9a64e`。PR の base は `origin/main`。
- 差分 0 の証跡: `git diff 273191b4 HEAD -- tools/python/analysis tools/python/tests` の出力は 0 行 (本 REPORT と `docs/DOC_MAP.md` の commit だけが増える)。
- 環境: GitHub Actions runner (4 コア)。測定時の load average は `uptime` で 1 分 0.51・5 分 0.27。
- 素材: `fl-win64` を `tar --zstd -xf fl-win64.tar.zst --wildcards '*block00031_PE.bin' '*block24429_DATA.bin' '*block24430_DATA.bin' '*block25159_DATA.bin' '*block24618_DATA.bin'` で `FL_WIN64_DIR=<fl-win64 展開先>` に展開 (`toolchain-emsdk` は本検証の対象外)。`tools/python/fetch_inputs.sh` で stubs と DATA を `work/` に配置 (gitignore)。

| 検証 | 実行 | 結果 |
|---|---|---|
| 生成器の決定性 | `FL_WIN64_DIR=… python3 analysis/flapi_kwargs.py` を `cea9a64e` で 2 回、`273191b4` で 1 回 | md5 は 2 回で一致 (`flapi_kwargs.json` 9f3f1196・`flapi_table.json` (merge 後) a7603c19)。再生成物と追跡中の 2 ファイルは `git status` 差分 0 |
| 書式と出力ポインタ数の照合 | `python3 tests/kwsig_check.py` | OK。照合 304 件・不一致 2 件 (`screen.addMeter` 5/6・`screen.addTextLine` 5/6、既知)。書式無し かつ 出力 >0 は 0 件 (件数と名前を assert) |
| 表の再生成 | `bash tests/flapi_table_check.sh` | PASS。再生成 3 ファイル差分 0/3・`win_pair_verified` 388 件・ネガコン 6/6 (2.3 s) |
| bind | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6122 ケース・misbind 0・mismatch 0) |
| 引数個数 | `python3 analysis/flapi/sig_arity_check.py <origin/main の表> analysis/flapi/flapi_table.json` | `origin/main`: 対象 273・一致 273・不一致 0。`273191b4`: 対象 274・一致 274・不一致 0。変化は `getPresetCount` が対象に入って一致の 1 件 |
| `getPresetCount` の bind 前後 | 一時スクリプト (repo 外)。位置のみ・kw のみ・混在・未知 kw・必須欠落の 20 呼出しを、修正前の表 (`a68d59f5`) と `273191b4` の表で実行 | 20 件すべて同一 |
| 受入条件の名指し検査 | `node tests/sig_arity_probe.mjs` | 未実行 (§6)。前提の `provider/build.sh` に emsdk が要り、この run では無い |

## 1. 再確認した書式 (wrapper の逆アセンブル)

`PyArg_Parse*` の呼出し直前 (前の `call` より後) に渡す非 0 の出力ポインタ数 (`outs`) と、書式が消費する数 (`ptrs`) を全 304 関数で照合した。`outs`・`ptrs` は `flapi_kwargs.json` に入る。表の `kwsig` の変更は `plugins.getPresetCount` の 1 件だけ (§3)。

| 関数 (fn_va) | 書式 | 表 (必須/最大) | ptrs | outs | 判定 |
|---|---|---|---|---|---|
| screen.addTextLine (0xd7abb0) | `siiii` | 5/5 | 5 | **6** | 表は正。§2 |
| screen.addMeter (0xd7ada0) | `iiii\|i` | 4/5 | 5 | **6** | 表は正。§2 |
| plugins.getPresetCount (0xd808d0) | `i\|ii` | 1/3 | 3 | 3 | 一致 (kw 形式。§3) |
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

全 304 関数のうち 302 件が一致 (残り 2 件が上の 2 行)。

## 2. screen.addTextLine / screen.addMeter の 6 個目

- **addTextLine (0xd7abb0)**: `PyArg_Parse*(args, "siiii", &[rbp+0x80], &[rbp+0x9c], &[rbp+0x98], &[rbp+0x94], &[rbp+0x90], &[rbp+0x8c])`。書式は 5 単位 (`s` + `i`×4) なので、解析されるのは最初の 5 個。6 個目 `&[rbp+0x8c]` は呼出し前に一度も書かれず、呼出し後に `mov r9d, [rbp+0x8c]` で読まれる (未初期化)。
- **addMeter (0xd7ada0)**: `PyArg_Parse*(args, "iiii|i", …)` の 6 個目 `&[rbp+0x58]` は関数の先頭で `mov dword [rbp+0x58], 0` により 0 に初期化され、解析されない。後段 `mov eax, [rbp+0x58]; mov [rsp+0x28], eax` で 0 のまま渡る。
- **判定**: 表の必須・最大 (5 と 4/5) は PyArg の解析個数どおりで、これを正とする。6 個目は解析されない余剰ポインタで、表の個数には入れない。addTextLine の 6 個目が未初期化のままなのは FL 側の不整合 (書式の 1 個不足か、呼出しの余剰か) で、どちらかは実機の呼出しでしか確定できない (§6)。
- 2 件の不一致は `kwsig_check.py` (11) で固定した。これ以外の不一致が出たら検査が落ちる。

## 3. plugins.getPresetCount (kw 形式)

- **逆アセンブル (0xd808d0)**: `mov rdx, r8` (kwargs を 2 番目の引数へ) → `lea r8` が書式 `i|ii` (0xd80a08) → `lea r9` が kwlist (0x151f158。`index`・`slotIndex`・`useGlobalIndex`・NULL 終端) → 出力 `[rsp+0x20]`=&[rbp+0x5c] (index)・`[rsp+0x28]`=&[rbp+0x58] (slotIndex。初期値 -1)・`[rsp+0x30]`=&[rbp+0x54] (useGlobalIndex。初期値 0) → `call qword ptr [rax]`。引数の並びは `PyArg_ParseTupleAndKeywords(args, kw, fmt, kwlist, 出力…)` の呼出し規約と一致する。
- **前版の誤り**: flags=1 を非 kw と仮定したため、書式を `rdx` (実際は kwargs の値) と見なして null にし、出力を `r8`・`r9`・スタックから 5 個と数えた (正は 3)。`kwsig_check.py` (11) は書式 null の関数を飛ばすので照合されなかった。REPORT の「flags=1 は kwlist を持たない」も、この関数については誤りだった。
- **同じ呼出し形式の数**: `mov rdx, r8` を持つ関数は全 36 件。flags=3 の 35 件と、flags=1 の本関数 1 件。残りの flags=1 は kw 形式を持たない。
- **修正**: 生成器の呼出し形式の判定 (`kw_form`) を、`flags & 2` だけでなく「PyArg 呼出し直前の `mov rdx, r8`」で行う。出力数 (`outs`) も同じ判定で数える。flags=3 の結果は変わらない (103 件)。
- **表の変更 (1 関数)**: `plugins.getPresetCount` の `kwsig` を `{flags:1, fmt:null}` → `{flags:1, fmt:"i|ii", required:1, max:3}` にした。他の 434 関数の `kwsig` は変わらない。
- **kwlist を kwsig に載せない理由**: `flags&2` (METH_KEYWORDS) の関数だけ、kwsig に kwlist を載せる。flags=1 (METH_VARARGS のみ) では CPython が kwargs を `TypeError` で拒否するので、kwlist から kw 受理を作らない。kwlist は `flapi_kwargs.json` に記録だけする。
- **PyMethodDef との不整合 (記録のみ)**: flags=1 (METH_VARARGS のみ) なのに kw 形式で呼んでいる。CPython は VARARGS 呼出しで r8 を設定しないため、この関数の kwargs (r8→rdx) は呼出し元の不定値になる。FL 実機でこの関数がどう動くかは未確認 (§6)。
- **bind への影響**: `fl_api._make` は `required` を、既定値が不明な省略位置 (gap) の判定にだけ使う。`getPresetCount` の index (既定値なし) は i=0 < required=1 で従来どおり `TypeError`。slotIndex・useGlobalIndex は既定値 (-1・False) があるので従来どおり省略時に埋まる。一時スクリプト (repo 外) で 20 呼出し形の結果を修正前後で比べ、全件同一。`kwsig_bind_check.py` は `getPresetCount` を対象に含まないので、PASS の結果は変わらない。

## 4. 名前の確定可否

- **新たに確定した名前: 0 件。** `getPresetCount` の 3 位置は、バイナリの kwlist (`index`・`slotIndex`・`useGlobalIndex`) が表の stub 名と一致することを確認した。表の名前は変えていない。
- **非 kw 形式の flags=1 は名前を持たない。** `PyArg_ParseTuple` 相当で書式だけを受け、kwlist を渡さない。mac の raw 表 (`analysis/flapi/raw_mac_*.json`) も doc だけで、引数名は無い。
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

- **表へ `arg{i}` を入れない理由**: `sig.params` に名前を入れると `fl_api.bind` が `arg1=` のような名前での kw 呼出しを受け入れてしまう (`src/fl_api.py` の `_make` は `sig.params` の名前を kw 名に使う)。kwlist 無しの関数は今も kwargs を拒否する前提で、それを変える挙動変更は本 issue の範囲外。そのため表の名前の変更は 0 件。

## 5. 同定の前提 (未確認の点)

- 間接 call の呼出し先 (`PyArg_Parse*` 系) は PE の import 表に名前が無く、未確認 (実行時に解決される)。引数の形は PyArg 系の呼出し規約と一致する: 非 kw は `PyArg_ParseTuple` (rdx=書式)、kw は `PyArg_ParseTupleAndKeywords` (rdx=kwargs・r8=書式・r9=kwlist)。PY-9b の前提を踏襲。
- 書式の消費数は Python C API の規則 (単位 1 つ = ポインタ 1 個、`#`・`!`・`&` は +1、`:`・`;` 以降は無視) で数えた。
- PyArg 呼出しを検出できなかった flags=1 は `screen.update` の 1 件 (outs None・書式無し)。0xd7b0a0 は PyArg を呼ばず、直接 call 0xd843d0 に固定引数を渡すだけなので、書式無しが正しい。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `screen.addTextLine` の 6 個目 (未初期化) と `screen.addMeter` の 6 個目 (0 固定) の意味 | 表の個数 5 は解析個数どおり。6 個目が呼出しに効くかは未確定 | #2952 (open。コメント済み) |
| 未確定の 42 位置 (issue 範囲) と 73 位置 (flags=1 全体) の引数名 | 名前付き呼出しは今も不可。名前は FL の公式資料か実機の呼出しが要る | #2952 (open。コメント済み) |
| `plugins.getPresetCount` の kw 形式と flags=1 の不整合 (§3) | 実機で kwargs がどう扱われるか未確認。表は kwlist を載せていないので bind への影響は無い | #2952 (open。追記済み) |
| 受入条件 `node tests/sig_arity_probe.mjs` | 前提の provider wasm に emsdk (`toolchain-emsdk`) が要る。この run の素材に無く未実行 | #2952 (open。追記済み。`oc_artifacts: toolchain-emsdk` で再実行) |
| 呼出し先の関数名 (§5) | PE に名前が無い | 未確認。PY-9b の前提を踏襲 (#2952 で扱う) |
