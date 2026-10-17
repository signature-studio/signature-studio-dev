# PY-5418 (#6207) 付録: グローバル `0x16bd1d8`・`0x16bd1e0`・`0x16bd1a8` の読み手の列挙

> 親: #5801 (PY-5390)。前段: `tools/python/REPORT_APPENDIX_5801.md` §3 の未解決表 (#6106)。
> 本付録は #5801 の付録 (生成物) を手で編集せず、読み手の列挙だけをここに置く。判定 (立ち/落ち) の作用の確定は #5801 側。
> 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B・`tar --zstd -xf` で展開)。

## 1. 読み手・書き手 (`.text` 全体の rip 相対参照)

列挙: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py193_refs.py <開始VA> <終了VA>` (範囲は各グローバルの 1 バイト)。
3 グローバルとも `rip` 参照だけが 1 件以上あり、`abs`・`imm`・`dsp` (基底レジスタ付き) の候補は 0 件。
全命令数 5,022,467 (3 回とも同数)。

| VA (命令) | 種別 | グローバル | 命令 | 所属関数 (線形デコード一致) |
|---|---|---|---|---|
| 0x11f1801 | 書 | `0x16bd1d8` | `mov qword ptr [rip+0x4cb9cc], 0` | 0x11f16b0 |
| 0x11f1822 | 書 | `0x16bd1e0` | `mov dword ptr [rip+0x4cb9b4], 0x5dc` | 0x11f16b0 |
| 0x11f182e | 書 | `0x16bd1e0` | `mov dword ptr [rip+0x4cb9a8], 0` | 0x11f16b0 |
| 0x11fd6b9 | 読 | `0x16bd1e0` | `cmp dword ptr [rip+0x4bfb20], 0` | 0x11fc770 |
| 0x11fd710 | 読 | `0x16bd1d8` | `cmp qword ptr [rip+0x4bfac0], 0` | 0x11fc770 |
| 0x11fd721 | 書 | `0x16bd1d8` | `mov qword ptr [rip+0x4bfab0], rax` | 0x11fc770 |
| 0x11fd731 | 読 | `0x16bd1d8` | `sub rax, qword ptr [rip+0x4bfaa0]` | 0x11fc770 |
| 0x11fd738 | 読 | `0x16bd1e0` | `movsxd rcx, dword ptr [rip+0x4bfaa1]` | 0x11fc770 |
| 0x11f1a47 | 書 | `0x16bd1a8` | `mov byte ptr [rip+0x4cb75a], sil` | 0x11f1a20 |
| 0x119350b | 読 | `0x16bd1a8` | `movzx rbx, byte ptr [rip+0x529c95]` | 0x1192f80 |

- `0x16bd1d8`: 書 3 箇所 (0x11f1801・0x11fd721)・読 2 箇所 (0x11fd710・0x11fd731)。読みは全て `0x11fc770` 内。
- `0x16bd1e0`: 書 2 箇所 (0x11f1822・0x11f182e)・読 2 箇所 (0x11fd6b9・0x11fd738)。読みは全て `0x11fc770` 内。
- `0x16bd1a8`: 書 1 箇所 (0x11f1a47)・読 1 箇所 (0x119350b)。

## 2. 所属関数の確かめ方と限界

- 関数先頭は、命令の直前が `ret` (0xc3) か `int3` (0xcc) で、そこから 2 命令が `push`/`sub` で始まる候補のうち、線形デコードで対象命令の先頭に**一致したもの**を採った (`analysis/flapi/pe_py6207_readers.py`)。
- 照合: 10 件中 10 件で、採った候補先頭から線形デコードした命令境界が対象命令の先頭に一致 (mismatch 0)。
  照合の負の対照は行っていない。途中の検証で終了条件を 1 命令ずらした版では全件が不一致になったが、これは検証コードの誤りを直した過程の出来事で、負の対照として数えない。
- 限界: 線形デコードの一致は**境界の整合**だけを見る。候補先頭が関数の唯一の先頭であること・呼出し元 (呼ばれ方) は**未確認**。
  `0x11fc770` と `0x1192f80` は、本付録の範囲では呼出し元を列挙していない。
- 途中で誤った候補を 2 件除いた: `0x11fcc52` (先頭 `push rbp` の直後が不整合) と `0x11f1805` (`0x11f1801` の命令の途中)。どちらも採らない。

## 3. 読み手の結論 (本付録の範囲)

- `0x16bd1d8`・`0x16bd1e0` の読み手は `0x11fc770` のみ (`0x16bd1d8` の読み 2・`0x16bd1e0` の読み 2)。書き手は `0x11f16b0` (#5801 の 1 段目に名指しの関数。`0x16bd1d8`・`0x16bd1e0` の両方へ書く) と、`0x11fc770` (`0x16bd1d8` へ 0x11fd721 で書く)。
- `0x16bd1a8` の読み手は `0x1192f80` (1 命令)。書き手は `0x11f1a20` (#5801 の 2 段目に名指しの関数 0x11f22f0 の直接の呼出し先)。
- #5801 の判定の立ち/落ちへの作用は本付録では確定しない。`0x11fc770`・`0x1192f80` が判定 (0x1047857 等) の経路に入るかは、#5801 で行う。

## 4. 再現

```
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py193_refs.py 0x16bd1d8 0x16bd1d9
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py193_refs.py 0x16bd1e0 0x16bd1e1
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py193_refs.py 0x16bd1a8 0x16bd1a9
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py6207_readers.py 0x11f1801 0x11fd710 0x11fd721 0x11fd731 0x11f1822 0x11f182e 0x11fd6b9 0x11fd738 0x11f1a47 0x119350b
```

`<展開先>` は `extracted/block00031_PE.bin` を含むディレクトリ (本 run では `tools/python/work/py5801/extracted`)。
