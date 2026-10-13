# #1134 (LD-34): 消費者形 pure 残 23 関数の支配関係つき修復・tracker-no-deref・動的確認 — 部分達成

**判定: 部分達成 (原因の記録のみ)**。修復 (entry 外 deref の 18 関数) と動的確認 (7/7) は未着手。本 PR は受入条件 2 (tracker-no-deref の理由) と 4 (5c44b0 の理由) の一部を取った。

先行: #930 (`REPORT_930.md`)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| first-deref-not-entry 18 関数の修復・不能理由 | **未着手**。#1325 (LD-46) に分割 (§4) |
| tracker-no-deref (75a180・db6480・dc27c0) の理由 | **一部**。理由の機構を §2 に記録。修正は未着手 (#1324 (LD-45)) |
| §2.1 survey 到達の再測定 | **未着手** (本 PR は IR・wasm を再生成していない。#930 の `reach_930.json` は PR #1281 で測定済み)。#1325 |
| 5c44b0 (none) の理由 | **一部**。§3 に記録。確定は #1324 |
| 修復の wasm を survey で比較 (7/7) | **未着手** (修復が無いため比較対象無し)。#1325 |

## 2. tracker-no-deref の機構

測定: `python3 ldfix/trk_probe_1134.py` (`work/boot_final3.ll` / `work/m11_image.bin` / `work/boot*.drc.config.json`、`use_residual_509.py` と同じ `F3C_ARITY` 設定)。

| 関数 | entry 直線部の sslot (1 回書き home) | f3c_track の deref | 機械語の実際の deref |
|---|---|---|---|
| 75a180 | `[rbp+0x100]`=arg1・`[rbp+0x110]`=arg3・`[rbp+0x118]`=arg4 | 0 | arg4 の値を `[rbp+0x60]` へ写し、ループ内で `mov rax,[rbp+0x60]; mov rdx,[rax]` |
| db6480 | `[rbp+0x80]`=arg3・`[rbp+0x88]`=arg4 | 0 | arg4 を `[rbp+0x30]` へ写し、`mov r8,[rbp+0x30]; mov r8d,[r8]` (2 段) |
| dc27c0 | `[rbp+0xa0]`=arg1・`[rbp+0xa8]`=arg2・`[rbp+0xb0]`=arg3 | 0 | arg2 を `[rbp+0x38]` へ写し、ループ内で `add [rbp+0x38],4` のあと `mov edx,[rdx]` |

読み取り (現象の機構):
- 75a180・dc27c0: 引数を写す frame slot (`[rbp+0x60]`・`[rbp+0x38]`) が**ループ内で書き換えられる** (`add qword ptr [rbp+0x60], 8` / `add qword ptr [rbp+0x38], 4`)。`_f3c_static_state` の「1 回だけ書かれる home」条件を満たさず、ブロック記号実行の初期状態に載らない。
- db6480: 引数を写す slot `[rbp+0x30]` は 1 回だけ書かれるが、store 先の値が「argN を base にした load の結果」ではなく「frame slot の内容」であるため、2 段目の deref が `_f3c_note_uses` の「base が直接 argN の reg」条件に掛からない。
- 3 関数とも、深さ 1 の deref (`mov rdx,[rdx]` 型) を見ている audit (`suspects_use`) との差は、この機構で説明できる。修正は ldfix.py の `_f3c_static_state` / `_f3c_note_uses` の拡張を要する。**本 PR では修正していない。**

## 3. 5c44b0 (none) の理由

- 5c44b0 の entry 直線部は `mov rax,[rdx]` (arg2 の deref) が**先頭 (5c44bf)** にあり、`f3c_track` は arg2 の deref 1 本を正しく記録する (`deref=[5c44bf, arg2, 64, entry=True]`)。
- `use_residual_509.py` で `none` と判定されるのは、arg2 の生の使用 (`raw`) が deref より後に無いため。すなわち `fix_f3c_use` の門 (a)(b)(c)(d) を全て通るが、**門 (c) (IR に argN からの zero-offset load が 1 本も無い) の判定が 5c44b0 では満たされ、置換対象が無い**、と読める。
- 理由の確定 (門 (c) か置換の空振りか) は `fix_f3c_use` の `rep_idx` を出力する必要がある。**本 PR では未確認。**

## 4. 残件と起票先

| 残件 | 起票先 |
|---|---|
| first-deref-not-entry 18 関数の支配関係つき修復 | #1325 (LD-46) |
| tracker-no-deref 3 関数の記号実行の修正 (§2) | #1324 (LD-45) |
| 5c44b0 の門 (c) / 置換空振りの確定 (§3) | #1324 (LD-45) |
| survey 到達の再測定と修復前後の動的比較 (7/7) | #1325 (LD-46) |

#1325 は #1324 の後に着手する (前提: LD-45 の結果で分類が変わりうる)。
PR 本文にある「全体 30 関数 / 33 引数が REPORT_930 の 23 / 24 と一致しない」件は未調査で、本 PR の範囲外。原因の切り分けは #1325 の着手前に行う。

## 5. 再現

`python3 tools/m11/ldfix/trk_probe_1134.py` (入力は work-m11 の展開物。`tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst`)。
