# PY-272 (#3926): 0x45c290 の戻り値 eax (= [rbp+0x3c]) の意味

親: #3617 (PY-221)。前段: `tools/python/REPORT_PY203.md` §3 (書込み 36 件の内訳)・`tools/python/REPORT_PY269.md` (第 1 引数 [rbp+0x30] の所属)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- **0x45c290 は `Variant*` を受けて int32 に変換する関数**。戻り値 eax は、型ワード (`word [arg+0]`) で分岐した先の変換結果。値の写像は次の表。
  - 第 1 引数 rcx は `[rbp+0x50]` に保存され、型ワードは `movzx rax, word [rax]` で読む。ペイロードは `[arg+8]` (VARIANT の値部)。
  - 戻り値は全経路で `[rbp+0x3c]` 経由 (ret は 0x45c8d0 と 0x45c8ed の 2 箇所、0x45c8c8 で `mov eax, [rbp+0x3c]`)。
- **型ごとの写像** (0x45c290 内の確定した命令):

  | 型 (word) | 戻り値の式 | 備考 |
  |---|---|---|
  | 0 (VT_EMPTY) | 0 | 0x45c3d8 |
  | 2 (VT_I2) | `movsx rax, word [arg+8]` | 0x45c406 |
  | 3 (VT_I4) | `mov eax, [arg+8]` | 0x45c417 |
  | 1 (VT_NULL) | 0 を返す。フラグ付きなら 0x459f60 (エラー経路、推定) を呼んでから 0 | 0x45c3e4 |
  | 4 (R4) | `cvtss2sd` → 0x40c660 (`cvtsd2si`) → 32bit 符号つき範囲を検査、外れたら 0x40f540 | 0x45c426 |
  | 5 (R8) | 同上 (`movsd` → 0x40c660) | 0x45c455 |
  | 6 (CY) | `[arg+8]` を整数として 0x40c670 (10000 で割る形、推定) → 範囲検査 | 0x45c483 |
  | 7 (DATE) | `movsd` → 0x40c660 → 範囲検査 | 0x45c4b0 |
  | 0xb (VT_BOOL) | `movsx rax, word [arg+8]` | 0x45c4ef |
  | 0xc (VT_VARIANT) | 内側の `Variant*` ([arg+8]) を再帰的に 0x45c290 へ | 0x45c58f |
  | 8 (VT_BSTR) | 0x45c040 | 0x45c4e2 |
  | 9・0xd | 0x45c170 | 0x45c5a8 |
  | 0x11 (VT_UI1) | `movzx rax, byte [arg+8]` | 0x45c511 |
  | 0x12 (VT_UI2) | `movzx eax, word [arg+8]` | 0x45c522 |
  | 0x14 (VT_I8) | 範囲検査、外れたら 0x40f540 | 0x45c54a |
  | 0x15 (VT_UI8) | `cmp rax, 0x7fffffff`、外れたら 0x40f540 | 0x45c572 |
  | 未知の型 | 0x45c230 で判定、だめなら 0x45c170 | 0x45c889 |

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

測定 commit: 本 PR の最後のコード commit (`git log -1 -- tools/python/analysis/flapi/pe_py272_probe.py` の hash)。

- probe: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py272_probe.py` → 27/27 PASS・終了 0。
- ネガティブ対照: 型 2 の式を型 3 の式と誤認した期待・0x40f540 の cl を 5 と誤認した期待の 2 件は偽として数える (PASS は「誤認が偽」を意味する)。
- 既存 probe は触らない。`pe_py203_probe.py` (27 件) と `pe_py221_chain.py` (17 項目) は PY-272 の変更の影響を受けない (flapi 直下の既存ファイルを変えていない)。

## 2. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x45c170・0x45c040・0x45c1c0 の間接 call 先 (`[rax]`・`[rip+...]` の関数ポインタ) の実体。IAT に無いので、初期化箇所で書かれる値を追う必要がある | 0x45c170 の VariantChangeTypeEx 形の確定、0x45c040 の数値化 API、0x45c1c0 の解放・複製の確定 | [PY-318] (子 issue) |
| 0x40f540・0x40f560 → 0x4096d0 の役割 (例外送出か) と、0x7ffdfffb の意味 | 範囲外時の戻り値 (0x40f540 は戻らない想定) の確定 | [PY-318] (子 issue) |
