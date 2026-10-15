# PY-272 (#3926): 0x45c290 の戻り値 eax (= [rbp+0x3c]) の意味

親: #3617 (PY-221)。前段: `tools/python/REPORT_PY203.md` §3 (書込み 36 件の内訳)・`tools/python/REPORT_PY269.md` (第 1 引数 [rbp+0x30] の所属)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- **0x45c290 は `Variant*` を受けて int32 に変換する関数**。戻り値 eax は、型ワード (`word [arg+0]`) で分岐した先の変換結果。値の写像は次の表。
  - 第 1 引数 rcx は `[rbp+0x50]` に保存され、型ワードは `movzx rax, word [rax]` で読む。ペイロードは `[arg+8]` (VARIANT の値部)。
  - 戻り値は全経路で `[rbp+0x3c]` 経由 (ret は 0x45c8d0 と 0x45c8ed の 2 箇所、0x45c8c8 で `mov eax, [rbp+0x3c]`)。
- **型ごとの写像** (0x45c290 内の確定した命令):

  | 型 (word) | 飛び先 | 戻り値の式 (eax) |
  |---|---|---|
  | 0 (VT_EMPTY) | 0x45c3d8 | 0 |
  | 1 (VT_NULL) | 0x45c3e4 | 0 (先に大域バイト `[rip+0xf522d3]` が非 0 なら 0x459f60 を呼ぶ。型フラグではない) |
  | 2 (VT_I2) | 0x45c406 | `movsx rax, word [arg+8]` |
  | 3 (VT_I4) | 0x45c417 | `mov eax, [arg+8]` |
  | 4 (R4) | 0x45c426 | `cvtss2sd` → 0x40c660 (`cvtsd2si`) → 32bit 符号つき範囲を検査、外れたら 0x40f540 |
  | 5 (R8) | 0x45c455 | `movsd` → 0x40c660 → 同上 |
  | 6 (CY) | 0x45c483 | `[arg+8]` を rcx に渡して 0x40c670 → 同上 |
  | 7 (DATE) | 0x45c4b0 | `movsd` → 0x40c660 → 同上 |
  | 8 (VT_BSTR) | 0x45c4de | 0x45c040 の戻り値 |
  | 9・0xd | 0x45c5a4 | 0x45c170 の戻り値 |
  | 0xa・0xe・0xf・0x16〜 (フラグ無しの未知の型、計 32746 語) | 0x45c889 | `0x45c230(src, &out)` が真なら 0x45c8c8 へ (戻り値は `out`)、偽なら 0x45c170 の戻り値。0x45c230 の内部は未確認 |
  | 0xb (VT_BOOL) | 0x45c4ef | `movsx rax, word [arg+8]` |
  | 0xc (VT_VARIANT) | 0x45c58f | 内側の `Variant*` ([arg+8]) を 0x45c290 へ再帰 |
  | 0x10 (VT_I1) | 0x45c500 | `movsx rax, byte [arg+8]` |
  | 0x11 (VT_UI1) | 0x45c511 | `movzx rax, byte [arg+8]` |
  | 0x12 (VT_UI2) | 0x45c522 | `movzx eax, word [arg+8]` |
  | 0x13 (VT_UI4) | 0x45c532 | `mov eax, [arg+8]`。負なら 0x40f540 (`test`/`jge`) |
  | 0x14 (VT_I8) | 0x45c54a | `mov rax, [arg+8]` → 32bit 符号つき範囲を検査、外れたら 0x40f540 |
  | 0x15 (VT_UI8) | 0x45c572 | `mov rax, [arg+8]`、`cmp rax, 0x7fffffff`、外れたら 0x40f540 |
  | 0x100 | 0x45c5b5 | 0x45c040 の戻り値 (`rcx` = `Variant*`) |
  | 0x101 | 0x45c5d7 | 0x45c1c0 の戻り値 |
  | 0x102 | 0x45c5c6 | 0x45c040 の戻り値 |
  | 0x4000 のフラグ付きで byref 表に無い語 (0x4000・0x4001・0x4009・…、計 32753 語) | 0x45c87b | 0x45c170 の戻り値 (0x45c230 は通らない) |
  | 0x4002 (VT_I2\|byref) | 0x45c6bf | `movsx rax, word [[arg+8]]` |
  | 0x4003 (VT_I4\|byref) | 0x45c6d3 | `mov eax, [[arg+8]]` |
  | 0x4004 (R4\|byref) | 0x45c6e5 | `cvtss2sd` ([[arg+8]]) → 0x40c660 → 範囲検査、外れたら 0x40f540 |
  | 0x4005 (R8\|byref) | 0x45c717 | `movsd` ([[arg+8]]) → 0x40c660 → 同上 |
  | 0x4006 (CY\|byref) | 0x45c748 | `[[arg+8]]` を rcx に渡して 0x40c670 → 同上 |
  | 0x4007 (DATE\|byref) | 0x45c778 | `movsd` ([[arg+8]]) → 0x40c660 → 同上 |
  | 0x4008 (VT_BSTR\|byref) | 0x45c7a9 | 0x45c040 の戻り値 |
  | 0x400b (VT_BOOL\|byref) | 0x45c7ba | `movsx rax, word [[arg+8]]` |
  | 0x4010 (VT_I1\|byref) | 0x45c7ce | `movsx rax, byte [[arg+8]]` |
  | 0x4011 (VT_UI1\|byref) | 0x45c7e2 | `movzx rax, byte [[arg+8]]` |
  | 0x4012 (VT_UI2\|byref) | 0x45c7f6 | `movzx eax, word [[arg+8]]` |
  | 0x4013 (VT_UI4\|byref) | 0x45c809 | `mov eax, [[arg+8]]`。負なら 0x40f540 |
  | 0x4014 (VT_I8\|byref) | 0x45c824 | `mov rax, [[arg+8]]` → 範囲検査、外れたら 0x40f540 |
  | 0x4015 (VT_UI8\|byref) | 0x45c84c | `mov rax, [[arg+8]]`、`cmp rax, 0x7fffffff`、外れたら 0x40f540 |
  | 0x400c (VT_VARIANT\|byref) | 0x45c869 | 内側 `Variant*` ([arg+8]) を 0x45c290 へ再帰 |

  - 飛び先の集合は 38 個 (0x45c3d8〜0x45c889)。上の全 65536 語の飛び先は、分岐 (`cmp`/`sub`/`test`・`je`/`jne`/`jg`/`jmp`) を追跡して求めた (`pe_py272_probe.py` の `landing`、未決定 0 件)。
  - 0x45c040・0x45c170・0x45c1c0 の式は「その呼び先の戻り値をそのまま eax にする」(確定)。呼び先の中身は未解決 (下の表)。

- **+0 / +8 のフィールド**: `+0` は型ワード (word) として読まれ、`+8` は値部として読まれる (型により整数・double・ポインタ)。読み出し位置から読める事実だけで、Win32 VARIANT の配置との一致は推定。
- **0x40f540 / 0x40f560**: `mov cl, 4 / 5` の後 `0x4096d0` へ入るだけの薄いラッパ。範囲外の結果で呼ばれるので、例外送出 (範囲外エラー) と見られる (推定)。0x4096d0 の中身は未確認。
- **0x45c170 (VT_I4 への強制変換)**: 次の順で呼ぶ。
  1. `VariantInit(&tmp)` (0x457270 → `oleaut32.dll!VariantInit` の thunk、import 表の名前で確定)
  2. 間接 call `[rax]` (IAT に無い関数ポインタ) で `(&tmp, src, 0x400, 0, VT_I4)` 相当の引数を渡す。引数の並びは `VariantChangeTypeEx` の形と一致 (推定。間接先は未確定)
  3. `tmp.lVal` (`[rbp+0x40]`) を返す。
- **0x45c040 (VT_BSTR → int32)**: `0x460e80` を呼んでから `0x414350` を呼び、`call [rax]` (間接) で数値化する。戻り値 eax が `0x80020005` (`0x7ffdfffb` を足すと 0) のときだけ別経路に分岐する。`0x80020005` は `DISP_E_TYPEMISMATCH` と一致する (推定。`0x460e80`・`0x414350`・間接先は未確認)。
- **0x45c1c0**: `VariantInit(&tmp)` → `0x45b480` (VarCopy 形、managed 判定付き) で src を tmp へ複製 → 間接 call → `0x45c290(&tmp)` で int32 化 → `0x45a9b0(&tmp)` で一時値を解放 (型ワード `& 0xbfe8` が 0 なら型ワードを 0 にし、そうでなければ `0x45a8f0`)、の順。役割は「一時コピーを作って int32 化し、解放する」ラッパ (推定。間接 call の先は未確定)。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で `<展開先>/extracted/block00031_PE.bin` に展開 (22 MB)。
- 逆アセは `pe_disasm.py` (capstone)。`call` 先の名前は `pe_iat_name.py` と import 表の照合。
- 検算の対象は 0x45c290 の本体 (0x45c290〜0x45c8d1)、0x40f540・0x40f560、0x45c170、0x457270 (thunk) の各命令。

## 1. 検証

測定 commit: (下の commit 欄を参照。本 round で probe を変えた commit)。

- probe: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py272_probe.py` → 41/41 PASS・終了 0 (前 round は 27 項目)。
  - 追加 14 項目: 型ワード 65536 語の飛び先が全て決まること・飛び先集合 38 個・VT_NULL の大域バイト判定・0x10/0x11/0x13/0x100/0x101/0x102/0x4002/0x400c/0x4000/0x0a の各 case。
- ネガティブ対照: 型 2 の式を型 3 の式と誤認した期待・0x40f540 の cl を 5 と誤認した期待の 2 件は偽として数える (PASS は「誤認が偽」を意味する)。
- 既存 probe は触らない。`pe_py203_probe.py` (27 件) と `pe_py221_chain.py` (17 項目) は PY-272 の変更の影響を受けない (flapi 直下の既存ファイルを変えていない)。

## 2. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x45c170・0x45c040・0x45c1c0 の間接 call 先 (`[rax]`・`[rip+...]` の関数ポインタ) の実体。IAT に無いので、初期化箇所で書かれる値を追う必要がある | 0x45c170 の VariantChangeTypeEx 形の確定、0x45c040 の数値化 API、0x45c1c0 の解放・複製の確定 | [PY-318] (子 issue) |
| 0x40f540・0x40f560 → 0x4096d0 の役割 (例外送出か) と、0x7ffdfffb の意味 | 範囲外時の戻り値 (0x40f540 は戻らない想定) の確定 | [PY-318] (子 issue) |
| 0x45c230 の内部 (フラグ無しの未知の型で最初に呼ぶ判定。型ワードを 0x467910 に渡し、その結果 `dil` で真偽を決める) | 0x45c889 系 (計 32746 語) の戻り値が 0x45c230 の真偽でどちらに分岐するか | [PY-318] (子 issue) |
