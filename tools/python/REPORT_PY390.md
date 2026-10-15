# PY-390 (#4830): findEventID・isDoubleClick の戻り値・status 経路を PE (VA) で確定する

親: #3840 (PY-260)。前段: `tools/python/REPORT_PY215.md` §1 (両関数を「未確定」と記録した表)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。
製品 KPI: 対象外 (起動・GUI に関わらない)。

## 結論

- **isDoubleClick (fl_table 348・本体 0xd76060)**: 経路を全て確定した。戻り status は 3 種。
  - 準備不可 (`0x11d1430` の判定が偽) → status **-2** (unsafe)。
  - device 無し (sub object が 0) → status **-7** (Device not assigned)。
  - 成功 → status 0。戻り値は [rbp+0x88] を変換器 (global 0x15e4280 の指す関数) に通した PyLong。status ≠ 0 は 0xd82c20 へ渡す。
- **findEventID (fl_table 331・本体 0xd75b60)**: 成功経路 (PyArg `i|i` 成功 → helper 0xf8c8e0(a, b) → 変換器) と失敗経路 (0xd82c20(eax)) は確定した。helper 0xf8c8e0 の「見つからない時」の値 (`-1`) の後段 (fallback 0xf78640) の戻りは未確定 (§3)。
- 残り未確定は §3 に分けた。本 PR は確定分の VA 表と再確認スクリプトだけを入れ、C provider・mock には書かない (issue の指示どおり)。

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
| 変換器 (global 0x15e4280 の指す関数) | 静的初期値は 0x16b8298。実行時の値はこの静的データからは決まらない | findEventID・isDoubleClick の PyLong 化の型 (`i`) は fl_table どおりと仮置き |
| 0xf8c8e0 の「見つからない」戻り (-1) の後段 | `or edi,-1` (0xf8c965) は fallback 0xf78640 (→0xf784c0) を通す。fallback 全体の戻り値の意味は未読 | findEventID の成功値の範囲は未確定 |
| 0xf82660 の二分探索 (0x16bacb8 の表) | 0x7fffffff を未発見の戻りに使う (0xf826d4)。表の供給元は未確定 | 同上 |
| 0x11d1430 の global と vtbl+0x88 の意味 | 報告判定と同じ global の +8 object と同一スロットだが、オブジェクトの型は未確定 | REPORT_PY61 §4-1 と同じ未解決 |

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| findEventID の fallback 0xf78640 → 0xf784c0 の戻り値の意味 | findEventID の未発見時の値 | #4870 (親: #4830) |
| 変換器 (0x15e4280 の指す関数) の正体 | isDoubleClick・findEventID の値の型変換 | #4870 (親: #4830) |

## 5. 検証

測定 commit: `60534394a` (`fix(python): pe_py390_probe の展開手順の表記を repo 外パスから外す (PY-390, #4830)`)。コードを変えた最後の commit。

- 再現: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py390_probe.py`
- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 9.241 秒・user 2.722 秒・sys 5.471 秒)。
- 実測: real **0.069 秒**・user 0.052 秒・sys 0.017 秒。実行前の load average (1 分) は 0.00。確認 14 件 OK・rc 0。
- 逆アセンブル: `analysis/flapi/pe_disasm.py` (capstone + pefile) の方式。

## 6. 差分

`git diff 60534394a HEAD -- tools/python/analysis/flapi/pe_py390_probe.py` の出力は 0 行 (スクリプトは測定 commit と同一)。`git diff 60534394a HEAD -- tools/python/REPORT_PY390.md docs/DOC_MAP.md` は本 REPORT の commit (REPORT と索引) だけ。
