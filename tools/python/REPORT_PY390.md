# PY-390 (#4830): findEventID・isDoubleClick の戻り値・status 経路を PE (VA) で確定する

親: #3840 (PY-260)。前段: `tools/python/REPORT_PY215.md` §1 (両関数を「未確定」と記録した表)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。
製品 KPI: 対象外 (起動・GUI に関わらない)。

## 結論

- **isDoubleClick (fl_table 348・本体 0xd76060)**: 経路を全て確定した。戻り status は 3 種。
  - 準備不可 (`0x11d1430` の判定が偽) → status **-2** (unsafe)。
  - device 無し (sub object が 0) → status **-7** (Device not assigned)。
  - 成功 → status 0。戻り値は [rbp+0x88] を変換器 (global 0x15e4280 の指す関数) に通した PyLong。status ≠ 0 は 0xd82c20 へ渡す。
- **findEventID (fl_table 331・本体 0xd75b60)**: 成功経路 (PyArg `i|i` 成功 → helper 0xf8c8e0(a, b) → 変換器) と失敗経路 (0xd82c20(eax)) は確定した。helper 0xf8c8e0 の未発見時の値は **-1** (fallback 0xf78640 → 0xf784c0 も未発見で -1 を返す。§7)。
- **変換器 (global 0x15e4280 の指す関数)** は `PyLong_FromLong` (§7)。findEventID・isDoubleClick の PyLong 化は `PyLong_FromLong` で確定した。
- 残りの未確定は §3 の表 (0xf82660 の表の供給元のみ)。本 PR は確定分の VA 表と再確認スクリプトだけを入れ、C provider・mock には書かない (issue の指示どおり)。

## 1. 2 関数の VA 表

| 関数 (fl_table 行) | 本体 VA | PyArg 書式 (VA) | 分岐 → 戻り値・status | 状態 |
|---|---|---|---|---|
| findEventID (331) | 0xd75b60 | `i\|i` (0xd75bb8) | PyArg 成功 (rax > 0, 0xd75b8d〜0xd75b90) → `call 0xf8c8e0(a=[rbp+0x2c], b=[rbp+0x28])` (0xd75b98) → 変換器 `[0x15e4280]` (0xd75b9f〜0xd75ba6) → PyLong。PyArg 失敗 → `call 0xd82c20(eax)` (0xd75baa〜0xd75bac) | 成功・失敗は確定。helper の戻りの意味は §3 |
| isDoubleClick (348) | 0xd76060 | `i` (0xd76184) | device 取得 `call 0xd77da0` (0xd76088〜0xd7608c) → PyArg 成功 (0xd760b2〜0xd760b5) → dispatch `call 0xd843d0` (0xd76109)。status [rbp+0x80] == 0 (0xd76118) → [rbp+0x88] を変換器 `[0x15e4280]` (0xd7611a〜0xd76127) → PyLong。status ≠ 0 → `call 0xd82c20(ecx=eax)` (0xd7612f〜0xd76131) | 経路は確定。値の変換器の正体は §3 |

## 2. 下位 helper の確定事項

| helper | 確定した内容 (VA) |
|---|---|
| 0xd843d0 (dispatch) | 結果構造体 `*rdx` の初期値 **-2** (0xd843e9)。`[rbx+0x50]` が有効なら `0xd84f30` の判定 (0xd843f7〜0xd84403)。成功後 `*rdx = [job+0x60]` (status, 0xd844d7〜0xd844db)。 |
| 0xd76000 (job core) | 準備判定 `call 0x11d1430` (0xd76010) が真 → status 0 (0xd76019) → sub object (`[rbx+8]+0x50`) があれば `call [vtbl+0x80]` の結果 (movsx) を値 (0xd76037〜0xd76041)。sub object が無い → **status -7** (0xd76047)。判定が偽 → status -2 (0xd7604f 直前で初期値のまま)。 |
| 0x11d1430 (準備判定) | global `0x1…413355` の `+8` object の `call [vtbl+0x88]` の戻り (0x11d1448)。報告判定 (0xd82c7e) と同じ global の `+8` object の vtbl+0x88 と**同じスロット**。 |
| 0xd82c20 (status → PyObject) | `REPORT_PY61.md` §4-1 のとおり。status < 0 は報告判定 (vtbl+0x88) で None か文言付き例外に分かれる。 |
| 0xd77da0 (device 取得) | `call qword ptr [global]` の薄いラッパー (0xd77da4)。IAT ではない。 |
| 0xd84f30 (dispatch 前の判定) | `[rcx+0x2d8]`・`[rcx+0x3b8]`・`[rcx+0x2da]`・`[rcx+0x2d9]`・`[rcx+0x410]` の bool を見て al を返す (0xd84f30〜0xd84f63)。 |

## 3. 未確定事項

| 項目 | 状態 | 扱い |
|---|---|---|
| 変換器 (global 0x15e4280 の指す関数) | **確定 (PY-400)**: `PyLong_FromLong` を解決した関数ポインタ。§7 | — |
| 0xf8c8e0 の「見つからない」戻り (-1) の後段 | **確定 (PY-400)**: fallback 0xf78640 → 0xf784c0 も未発見で -1 を返す。§7 | — |
| 0xf82660 の二分探索 (0x16bacb8 の表) | 0x7fffffff を未発見の戻りに使う (0xf826d4)。表の供給元は未確定。0xf8c8e0 は 0x7fffffff の index を範囲外として扱い (0xf8c941 `jl`)、fallback 側へ進む | 未発見の最終値 (-1) は、表検索 0xf78660 が 0 を返す (未発見) 前提で fallback 0xf784c0 が -1 を返す。0xf77340 の未発見時の戻りは未確認 (§7)。見つかった場合の値域だけが未確定 |
| 0x11d1430 の global と vtbl+0x88 の意味 | 報告判定と同じ global の +8 object と同一スロットだが、オブジェクトの型は未確定 | REPORT_PY61 §4-1 と同じ未解決 |

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0xf82660 の表 (0x16bacb8) の供給元 | 見つかった場合の findEventID の値域 (未発見時の値には影響しない) | #3840 (PY-260) に未解決としてコメント済み (https://github.com/signature-studio/signature-studio-dev/issues/3840#issuecomment-6199925267) |

## 5. 検証

測定 commit: `60534394a` (`fix(python): pe_py390_probe の展開手順の表記を repo 外パスから外す (PY-390, #4830)`)。コードを変えた最後の commit。

- 再現: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py390_probe.py`
- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 9.241 秒・user 2.722 秒・sys 5.471 秒)。
- 実測: real **0.069 秒**・user 0.052 秒・sys 0.017 秒。実行前の load average (1 分) は 0.00。確認 14 件 OK・rc 0。
- 逆アセンブル: `analysis/flapi/pe_disasm.py` (capstone + pefile) の方式。

## 7. PY-400 (#4870) で確定した VA 表

再確認: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py400_probe.py` (rc 0・全 14 件 OK)。

| 項目 | VA | 確定した内容 |
|---|---|---|
| findEventID の未発見時 (helper) | 0xf8c8e0 | 初期値 `edi=-1` (0xf8c8ed)。表を引いても未発見なら fallback (0xf8c95c)。fallback も無ければ `or edi,-1` (0xf8c965) → 戻り -1 |
| fallback | 0xf78640 | `call 0xf784c0` の戻り (eax) をそのまま返す (0xf7864c) |
| 0xf784c0 の戻り | 0xf784c0〜0xf78608 | 戻り値 `[rbp+0x3c]` の初期値 -1 (0xf784dd)。対象 object が 0 なら -1 のまま返す (0xf78573) |
| 変換器の参照 | 0xd75b9f・0xd76120 | findEventID・isDoubleClick とも global 0x15e4280 を読み `call [rax]` |
| 変換器の静的内容 | 0x15e4280 (.data) | 格納場所 0x16b8298 (.bss) を指す |
| 変換器の登録 | 0xc396c0・0xc396c5 | 名前解決 `call 0x4235f0` の戻りを 0x16b8298 に格納 (0xc396c5) |
| 登録の名前 | 0xc3a292 | UTF-16 文字列 `PyLong_FromLong` |
| 名前解決の経路 | 0x4235f0 → 0x4235e0 | 0x4235e0 は IAT slot 0x1971600 (`kernel32.dll!GetProcAddress`) の jmp |

結論: 表 0x16bacb8 の中身が空と仮定すると、未発見時の findEventID は **-1** を PyLong で返す (変換器 = `PyLong_FromLong`)。0xf77340 の未発見時の戻りは未確認のため、この結論は前提付き (下段)。

前提の範囲 (未発見の -1 がどこに依存するか): 0xf784c0 の未発見時の -1 は、3 箇所の表検索 0xf78660 (0xf7850e・0xf78551・0xf7856d) がいずれも 0 を返すことに依存する。0xf78660 は `call 0xf77340` の戻りが 0 なら rbx=0 のまま返す (0xf78681〜0xf78689)。0xf77340 の未発見時の戻りは本 probe で固定していない (未確認)。したがって「表の中身に依らない」とは言わない。表の中身が見つかる場合の値域は §4 の未解決のとおり。

測定 commit: `63651e534` (`feat(python): findEventID の未発見時の値 (-1) と変換器 (PyLong_FromLong) を PE で確定 (PY-400, #4870)`)。コードを変えた最後の commit。
- 実測: real **0.09 秒**・user 0.06 秒・sys 0.02 秒。実行前の load average (1 分) 0.07。確認 14 件 OK・rc 0。
- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 5.595 秒・user 4.587 秒・sys 5.817 秒)。

## 8. PY-260 (#3840) の実装 (C provider と mock)

PE で確定した分だけを `provider/fl_engine.c` と `host/fl_mock.mjs` に入れた。推測の値は書いていない。

| 関数 | 実装 | 根拠 | 未確定 (仮置き) |
|---|---|---|---|
| findEventID (fl_table 331) | 引数 1〜2 (`i\|i`) の型だけ見て **-1** を返す。device・link の割当は見ない | §7 (表 0x16bacb8 の中身が空と仮定した上での PE 確定。0xf77340 の未発見時の戻りは未確認) | 表 0x16bacb8 の中身が空と仮定 (上記の前提)。見つかった場合の値域は未確定 (§4) |
| isDoubleClick (fl_table 348) | device 無し (`dev_assigned` 0) → **-7** ("Device not assigned")。device 有りは Unspecified error (code 2) | §1・§2 (-7 は PE 確定) | 準備判定 0x11d1430 は真と仮定。device 有りの値 (plugin の vtbl+0x80) は未実装 |

- 検査: `tests/device_diff.mjs` に両関数の呼出し (device 割当 1/0 × 引数有無) を追加し、mock と C の code・戻り値が一致することを見る。期待値は PE 確定の code で固定。
- 件数: `tests/provider_expect/pe390.json` を追加 (2 関数)。`provider_check` の implemented は PE 件数から導出される。
- 測定 commit: `839cfc5e4` (コードを変えた最後の commit)。
- 実測値 (測定 commit `839cfc5e4` 時点の PR 本文の記録。コマンドは `tools/python/` 配下で実行):
  - `node tests/device_diff.mjs`: diffs 0・PASS (calls 21・link 9・rejects 13・midi_out 10)
  - `node tests/provider_check.mjs`: PASS (functions 435・implemented 231・unimplemented 204・mcp_static 60)
  - `FL_ENGINE=wasm node tests/all_tools.mjs`: 48/48 ok (host_calls 37425)。mock 経路も 48/48 ok
- 再現状況: 上の数値は修正 run (round 1) では再実行していない。`toolchain-emsdk` が取得できず `dist/` が未ビルドのため。再測定は emsdk を素材に含めた run で行う。
- 差分: `839cfc5e4..HEAD` の provider / host / tests / analysis 差分は 0 (REPORT_PY390.md の 1 行のみ)。

## 6. 差分 (PY-390 時点)

`git diff 60534394a HEAD -- tools/python/analysis/flapi/pe_py390_probe.py` の出力は 0 行 (スクリプトは測定 commit と同一)。`git diff 60534394a HEAD -- tools/python/REPORT_PY390.md docs/DOC_MAP.md` は本 REPORT の commit (REPORT と索引) だけ。
