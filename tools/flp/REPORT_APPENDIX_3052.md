# FLP (#3052) WFBox / DitherBox の読取り関数の静的調査 (REPORT §18 の全文)

`REPORT.md` の索引から参照する付録。`REPORT_APPENDIX.md` が 250 行上限を超えるため、§18 を分割移動した (内容の削除はない)。

## 18. #3052 WFBox / DitherBox の読取り関数の静的調査 (受入 1 の VA)

測定 commit: **`b2c1d611`** (`tools/flp/s3_regread_xref.py` の最後のコード変更。追加は `f2fd830f`、ヒットごとの VA 出力と陰性対照 (`S3_DROP_CALL`) の追加は `b2c1d611`)。対象: 素材 `block00031_PE.bin` (FLEngine_x64.dll, 22,227,016 B)。再現: `uv run --with pefile --with capstone python3 tools/flp/s3_regread_xref.py $RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`。

**所要 (n=3、単一プロセス、4 コア、`uv run` 含む wall 時間)**: 1 回目 18.72 s・2 回目 18.58 s・3 回目 18.46 s (min 18.46・max 18.72 s)。各回の開始時 load average は 1 回目 0.50 (5 分値 0.46)・2 回目 0.64 (0.49)・3 回目 0.74 (0.53)。出力は 3 回とも同一。前版の 13.5 s は 1 回値で load を記録していなかったため置換した。

**結論: 受入 1 の「読取り関数の VA」は未特定 (未達のまま)。** 静的に言えるのは次の 3 点。
1. `WFBox`・`DitherBox`・`WAVRenderForm` の **UTF-16 リテラルは FLEngine に無い** (ASCII の出現だけ)。よって、この値名を文字列リテラルで読む関数は無い。読取りは部品名を実行時に得る汎用経路と見られる (推定)。
2. レジストリ読取りは `RegQueryValueExW`・`RegOpenKeyExW` の thunk (`jmp [IAT]`) を経由する。直接呼出し 60 箇所・33 関数。
3. 汎用経路の候補は絞れたが、確定していない (下記 18.4)。

**18.1 文字列の出現** (script §1。対照: 既知の UTF-16 リテラル `Software\Image-Line\FL Studio 26\General` は script §6 で 2 関数の参照を検出 → 検出方法は UTF-16 リテラルを拾える)

| 文字列 | ASCII 出現 | UTF-16 出現 |
|---|--:|--:|
| `WFBox` | 14 | 0 |
| `DitherBox` | 6 | 0 |
| `QualityBox` | 4 | 0 |
| `FormatBox` | 10 | 0 |
| `WAVRenderForm` | 6 | 0 |

`WFBox`・`DitherBox`・`WAVRenderForm` の全ヒットの VA と前後のバイト (script §1 の `hit` 行をそのまま載せた。`va` = `ImageBase 0x400000 + セクション VA + (file offset − PointerToRawData)`、`off` = ファイルオフセット、`pre` = 直前 4 バイト、`post` = 直後 24 バイト):

```text
string WFBox          ascii_hits=14 utf16_hits=0
  hit WFBox         va=0xc4c5ae sec=.text off=0x84b9ae pre=b'\x00\x07DW' post=b'8\t\x00\x00\x03\x00\rDWChannelsBox@\t\x00\x00'
  hit WFBox         va=0xd1339d sec=.text off=0x91279d pre=b'\x00\x04\x00\x05' post=b'\xe8\x07\x00\x00\x05\x00\x10MP3BitrateSlider\xf0'
  hit WFBox         va=0xd1391c sec=.text off=0x912d1c pre=b'\x00\x00\x00\x0b' post=b'Change\x16\x00\x10\xf5\xd1\x00\x00\x00\x00\x00\x0bIPBoxCh'
  hit WFBox         va=0xed9d82 sec=.text off=0xad9182 pre=b'rmat' post=b'\xf0\n\x00\x00\n\x00\x1cOutputFormatMP3Bi'
  hit WFBox         va=0xeda90d sec=.text off=0xad9d0d pre=b'rmat' post=b'Change\x1d\x00\xf04\xef\x00\x00\x00\x00\x00\x12TuningS'
  hit WFBox         va=0x1b32417 sec=.rsrc off=0x13a3017 pre=b'o\x07DW' post=b'\x04Left\x03\xfc\x00\x03Top\x02\x1c\x05Width\x02M\x06H'
  hit WFBox         va=0x1c66e12 sec=.rsrc off=0x14d7a12 pre=b'rmat' post=b'\x04Left\x02\n\x03Top\x02\x1e\x05Width\x02O\x06He'
  hit WFBox         va=0x1c67135 sec=.rsrc off=0x14d7d35 pre=b'rmat' post=b'Change\x0cDefaultValue\x02\x00\nPo'
  hit WFBox         va=0x1c68949 sec=.rsrc off=0x14d9549 pre=b'rmat' post=b'Change\x0cDefaultValue\x02\x00\nPo'
  hit WFBox         va=0x1c68c5e sec=.rsrc off=0x14d985e pre=b'rmat' post=b'Change\x0cDefaultValue\x02\x00\nPo'
  hit WFBox         va=0x1cb5db5 sec=.rsrc off=0x15269b5 pre=b'mbo\x05' post=b'\x04Left\x02Z\x03Top\x02\x1e\x05Width\x02O\x06He'
  hit WFBox         va=0x1cb60cc sec=.rsrc off=0x1526ccc pre=b'ge\x07\x0b' post=b'Change\x0cDefaultValue\x02\x00\nPo'
  hit WFBox         va=0x1cb7854 sec=.rsrc off=0x1528454 pre=b'ge\x07\x0b' post=b'Change\x0cDefaultValue\x02\x00\nPo'
  hit WFBox         va=0x1cb7b52 sec=.rsrc off=0x1528752 pre=b'ge\x07\x0b' post=b'Change\x0cDefaultValue\x02\x00\nPo'
string DitherBox      ascii_hits=6 utf16_hits=0
  hit DitherBox     va=0xc4c23d sec=.text off=0x84b63d pre=b'\x00\x04\x00\t' post=b'\xb8\x07\x00\x00\x04\x00\tPlugHQBox\xc0\x07\x00\x00\x04\x00\tN'
  hit DitherBox     va=0xd133ed sec=.text off=0x9127ed pre=b'\x00\x02\x00\t' post=b'\x10\x08\x00\x00\x02\x00\tPlugHQBox\x18\x08\x00\x00\x02\x00\tN'
  hit DitherBox     va=0xed99c1 sec=.text off=0xad8dc1 pre=b'lity' post=b'\xc0\t\x00\x00\x08\x00\x0cQualityHQBox\xc8\t\x00\x00\x08'
  hit DitherBox     va=0x1b31e9f sec=.rsrc off=0x13a2a9f pre=b'Box\t' post=b'\x04Left\x02\x03\x03Top\x02P\x05Width\x02{\x06He'
  hit DitherBox     va=0x1c65695 sec=.rsrc off=0x14d6295 pre=b'lity' post=b'\x04Left\x02\x0c\x03Top\x02U\x05Width\x03\xc4\x00\x06H'
  hit DitherBox     va=0x1cb4e28 sec=.rsrc off=0x1525a28 pre=b'Box\t' post=b'\x04Left\x02\x03\x03Top\x02P\x05Width\x02{\x06He'
string WAVRenderForm  ascii_hits=6 utf16_hits=0
  hit WAVRenderForm va=0xd12d64 sec=.text off=0x912164 pre=b'\x11\x12:T' post=b'.:1\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xa8\x04+\x01\x00'
  hit WAVRenderForm va=0xd12dac sec=.text off=0x9121ac pre=b'\x11\x12:T' post=b'.:2\x18\x00\x00\x00 -\xd1\x00\x00\x00\x00\x00\xff\xff\xff\xff -\xd1\x00\x00'
  hit WAVRenderForm va=0xd13aff sec=.text off=0x912eff pre=b'n\x00\x0eT' post=b'\t\x00\x98m|\x00\x00\x00\x00\x00H\x93y\x00\x00\x00\x00\x00@Xs\x00\x00\x00'
  hit WAVRenderForm va=0xd13b63 sec=.text off=0x912f63 pre=b'\x00\x07\x0eT' post=b'\xb0.\xd1\x00\x00\x00\x00\x00\xc0\x1dt\x00\x00\x00\x00\x00\x81\x00\tRende'
  hit WAVRenderForm va=0x1cb1727 sec=.rsrc off=0x1522327 pre=b'0\xf1\x0eT' post=b'\rWAVRenderForm\x04Left\x03v\x01\x03T'
  hit WAVRenderForm va=0x1cb1735 sec=.rsrc off=0x1522335 pre=b'orm\r' post=b'\x04Left\x03v\x01\x03Top\x03\xe7\x00\x0bHelpCont'
```

- `WFBox` の VA `0xd1339d` は、直前が `\x00\x04\x00\x05` (`\x05` は WFBox の長さ接頭)。直後は `\xe8\x07\x00\x00\x05\x00` の 6 バイトを挟んで、部品名 `\x10MP3BitrateSlider` (長さ接頭 16) が続く。
- `WAVRenderForm` の `.text` ヒットは 4 件 (`0xd12d64`・`0xd12dac`・`0xd13aff`・`0xd13b63`) で、範囲は `0xd12d64`〜`0xd13b63`。`DitherBox` の `.text` ヒットは `0xd133ed` を含む。これらは同じ領域のため、TWAVRenderForm のフォーム定義 (DFM) と推定する。
- 旧版 (`f2fd830f`) は file offset 順の先頭 1 件 (VA `0xc4c5ae`、file offset `0x84b9ae`) の前後だけを出していた。本節の `0xd1339d` とは別のヒットで、読み手が食い違って見えた原因。`b2c1d611` で全ヒットを出すように直した。

**18.2 レジストリ API の thunk** (script §2。`jmp [IAT]` のバイト列 `ff 25` を IAT スロットで照合)

| thunk VA | API |
|---|---|
| `0x407200` | RegOpenKeyExW |
| `0x407210` | RegQueryValueExW |
| `0x4230d0` | RegOpenKeyExW |
| `0x423100` | RegQueryValueExW |

**18.3 直接呼出し** (script §4・§5。call/jmp rel32 の先が thunk のもの。間接呼出し `call [reg]`・vtable は数えていない)
- `Reg{Query,Open}` thunk への直接呼出し: **60 箇所・33 関数** (`functions=57816`、`insns=2566540` を関数単位で逆アセンブル)。各関数の呼出し箇所 VA は script §4 の `at=` に出る。
- うち `RegQueryValueExW` を直接呼ぶ関数は **30 件**。呼出し元が 1 件以上ある主な関数: `0x5b0bd0` (size 0xb0・呼出し元 8)、`0x5b02a0` (0x72・7)、`0x11d9340` (0x1d85・10)、`0xf40840` (0x401d・3・プロジェクト保存)、`0x121d7e0` (0x17c1・3・`General` / `Last SER`)、`0x117f850` (0xd0a・2・`Shared\General`)。
- `0x11a57c0` (size 0x81e8・`ReadIniFile`・`General\` 系) は主要オプションを**リテラル名**で読む (`SmootherUpdateBox`・`SyncType` 等が UTF-16 リテラル)。`WFBox` はリテラルに無いので、この関数の直接の文字列参照では読まれない (推定)。ただし §19 で `0xba5d10` が WFBox の読取り経路上にあることを置換で確認した (推定。`0x11a57c0` の 2 箇所の呼出しがその経路に入るかは未確認。§19 の連鎖を参照)。
- **陰性対照 (1 件を壊す。WORKFLOW §5)**: `S3_DROP_CALL=0x5b0d53` で `0x5b0cd0` の唯一の呼出し (`0x5b0d53`、`RegOpenKeyExW` 側) を数えないと、直接呼出しは **59 箇所・32 関数** (正: 60・33) になり、`fn 0x5b0cd0` の行が消える。RegQueryValueExW を直接呼ぶ関数は 30 件のまま (Query 側は不変)。計数が 1 件ごとに効くことを確認した (実測 18.63 s、load 0.80)。

**18.4 キー組立ての候補 (未検証)**
- `Software\Image-Line\FL Studio 26\General` (UTF-16 リテラル) は `0x111bce0` (TRegistry を生成し `OpenKey` (`0x5af5e0`) を呼び、リテラル名 1 件を処理) と `0x1175480` から参照される。
- `Software\Image-Line\FL Studio 26\General\` (末尾 `\` 付き) は `0xfe0710` (コンストラクタ) だけが参照する。`0xfe0750` の `lea rdx` でリテラルを第 2 引数に渡し、`0xfe0749` の `lea rcx, [rsi+0x1654]` でサブオブジェクト `+0x1654` のアドレスを第 1 引数に渡して `0x414c70` を呼ぶ (逆アセンブルで確認。`+0x1654` への代入ではない)。
- 仮説 (推定、未確認): フォームの設定キーは「基底キー `General\` + フォーム名」で、`WAVRenderForm` は `General\WAVRenderForm`。その汎用ローダが部品名 (`WFBox`) を値名に使う。

**18.5 読取りラッパ層 (RTL 相当、名称は未確認)**
- `0x5b02a0`・`0x5b0bd0`: `RegQueryValueExW` を直接呼ぶ読取り層 (呼出し元 7 / 8)。`0x5af7c0`: `RegOpenKeyExW` を呼ぶ `OpenKey` 相当 (呼出し元は一意の関数で 26)。
- 上記の呼出し元の中に、部品名を実行時に受け取って読む関数があるはず (推定)。その特定が次の一手。

**未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `WFBox` を読む汎用ローダ (部品名を実行時に値名にする関数) の VA と、読んだ値の書式引数 (`0x670fd0` の第 6 引数) への渡し先 | 受入 1 未達 (VA 未特定) | #3052 |
| 18.4・18.5 の候補の真偽 (静的のみ)。動的確認 (S1 で install 木を作り、候補の戻り値を `S2_PATCH` で変える) は未実施 | 候補が経路上かは未確認 | #3052 |
| 間接呼出し (`call [reg]`・vtable) 経由の読取りは未計数 | 静的な網羅性は直接呼出しの範囲まで | #3052 |
| 別 wineprefix・別 run での SHA 一致、Render tests 全数の書き出し | 本節の対象外 | #3053 (依存 #3052) |

**差分の証跡**: `git diff b2c1d611 HEAD -- tools/flp/s3_regread_xref.py` の出力は 0 行 (以後は文書の変更のみ)。製品 KPI (flelift の起動 dispatch 数・通過 unit 数): 動かしていない (静的解析のみ、起動なし)。

## 19. #3052 WFBox の読取り経路 (関数先頭の置換による二分探索)

測定 commit: **`3c98162a3`** (`tools/flp/s4_bisect.sh`・`tools/flp/s4_xref.py` の追加)。再現: `bash tools/flp/s4_bisect.sh <VA hex or none> 1` (1 run)。**前提は手動補完が必要**: `s1_wine_probe.sh` は 280 s で 20,572 ファイルで止まるため、残りを手動 copy し、`Shared/QuickFontCache*.dll` を手動で配置してから実行した (下の環境段落)。手動補完をしないと同じ表は再現されない。静的呼出し元: `uv run --with pefile --with capstone python3 tools/flp/s4_xref.py $RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin ba5d10 2`。関数本文: 同じ引数で末尾に `5 fn` を付ける (`ba5d10 5 fn`)。
差分の証跡: `git diff 3c98162a3 HEAD -- tools/flp/s2_render_probe.sh tools/flp/s4_bisect.sh` の出力は 0 行。`tools/flp/s4_xref.py` は `d6f33a0ed` で `fn` 引数 (関数本文の出力) を足した。既定モード (`ba5d10 2`) の出力は `3c98162a3` 版と `d6f33a0ed` 版で `cmp` が一致 (direct callers=4・関数 3)。

**結論 (受入 1 の一部達成)**: WFBox の RegQueryValueExW が通る汎用ループは **`0xba5d10`** (項目リスト `[rbp+0x40]` を回し、各項目の名前 `[item+0x10]` で値を読む。WFBox の値を読む関数とは断定しない)。0 を返す版にすると WFBox の RegQueryValueExW が 4 件 → 0 件になり、書出しは既定の 16-bit (385,000 B) になる。値の格納先と、WAV 書式引数 (`0x670fd0` の第 6 引数) への渡し先は未特定。

**環境 (この run の組立て)**: wine-9.0 (`/usr/lib/wine/wine64`)・xvfb-run。`WINEDLLOVERRIDES="mscoree,mshtml="` (Mono/Gecko の導入待ちを避ける)。`s1_wine_probe.sh` は 280 s の上限で止まり、インストール木が 20,572 ファイルで途切れた (copy 部の `os.listdir` を block ごとに呼ぶ O(N²) が原因)。残りを同じ規則 (`paths[0]` が `$INSTDIR`) で copy して 25,131 ファイル。`Shared/QuickFontCache*.dll` が無いと `/R` が `Runtime error 216` の MessageBox で止まる (`WINEDEBUG=+msgbox`)。copy 後は止まらず完走。

**実測 (1 run ずつ、`s4_bisect.sh` の出力。WFBox の値は 1 (24-bit) を既定に使う)**

| 条件 | fmt / bit | data B | data SHA-256 (先頭 12 桁) | WFBox の RegQueryValueExW 件数 |
|---|---|--:|---|--:|
| 基準 (置換なし、WFBox=1) | 1 / 24 | 577,500 | fc353b289269 | 4 |
| `0xba5d10` を `xor eax,eax; ret` | 1 / 16 | 385,000 | fe7a061441ea | **0** |
| `0x9073c0` を同上 | 1 / 24 | 577,500 | fc353b289269 | 4 |
| 基準 (置換なし、WFBox=2、既定) | 3 / 32 float | 770,000 | 9e0251ebf3ab | 未計測 |

同じ方法で `+reg` 件数だけを比べた結果 (WFBox=1、基準 4 件):

| 置換した関数 | 件数 | 置換した関数 | 件数 |
|---|--:|---|--:|
| `0x5b0810` (4 バイト読取り) | 4 | `0x9088f0` (項目の種別ループ) | 4 |
| `0x5b25d0` | 4 | `0x5b1c10` (ラッパ) | 4 |
| `0x5b1820` | 4 | `0x963ed0` / `0xeec5d0` / `0xdf60e0` / `0x963b50` / `0xba6340` | 各 4 |
| `0x664fd0` | 4 | `0x5b03a0` | 0 (ただし他の設定も変わり 44,100 Hz / 16-bit) |
| `0x5b19f0` | 0 (同上、44,100 Hz / 16-bit) | `0xba5d10` | **0** (16-bit) |

**`0xba5d10` の中身 (`s4_xref.py` の `fn` 出力。再現は上の `ba5d10 5 fn`)**: `r13 = [rbp+0x40]` (項目の配列)、`rsi = [r13]` (項目)・`0x40fe90(rsi, …)` で項目の種別を判定・名前 `r8 = [rsi+0x10]`・区間 `rdx = [rbp+0x38]`・既定値 `r9d = 0x7fffffff` (未取得の番兵) で `0x5b19f0` を呼ぶ。ループは `add r13,8; jne` で回る。直接の呼出し箇所は **4 箇所** (`0xba6162`・`0xcef026`・`0x11a7467`・`0x11a75b1`)、呼出し元の関数は **3 つ** (`0xba6150`・`0xceee30`・`0x11a57c0`)。`0x11a57c0` に 2 箇所 (`0x11a7467`・`0x11a75b1`)。`0x11a57c0` は §18 の ReadIniFile 相当。

**呼出しの連鎖**:
- **静的な呼出し辺 (確認済み)**: `0x11a57c0` → `0xba5d10` → `0x5b19f0` (呼出し元 99) → `0x5b03a0` → `0x5b0bd0` → `RegQueryValueExW` thunk (`0x423100`、§18 の thunk 表)。
- **WFBox の読取りがこの連鎖を通るか (未確認・推定)**: 置換で `0xba5d10` を消すと WFBox の RegQueryValueExW が 4 → 0 件になったので、`0xba5d10` が WFBox の読取り経路上にあることは示された。ただし `0x11a57c0` の 2 箇所の呼出し (`0x11a7467`・`0x11a75b1`) を塞いだ試験は未実施。確定させるなら、この 2 つの 5 バイトの call (期待値 `e8a4e89fff`・`e85ae79fff`) を `9090909090` に置換する 1 run を `S2_PATCH` (形式は `VA|期待バイト|置換バイト`) で測り、WFBox の RegQueryValueExW が 0 件になるかを見る (未解決表に記載)。

**否定された候補**: `0x9073c0` (§18 の整数読取り候補。置換しても出力・件数とも変わらない)、`0x9088f0` (置換しても WFBox の読取りは残る)、`0x5b0810`・`0x5b25d0`・`0x5b1820`・`0x664fd0`。

**受入の状況**: 受入 1 の「読取り経路の VA」は、WFBox の RegQuery が通る汎用ループ `0xba5d10` まで (置換で経路上を確認。WFBox の値を読む関数とは未確定)。書式を決める値の格納先と、`0x670fd0` の第 6 引数への渡し先は未特定のため、受入 1 は未達。受入 2 は PR #3084 で達成済み (本 run では変えていない)。

**未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xba5d10` が書き込む項目フィールドと、`0x670fd0` の書式引数 (第 6 引数) への渡し先 | 受入 1 の後半未達 | #3052 |
| `0x11a57c0` の 2 箇所の呼出し (`0x11a7467`・`0x11a75b1`) を `9090909090` に置換して、WFBox の RegQuery が 0 件になるかの確認 (未試験) | §19 の呼出し連鎖の確定 | #3052 |
| 今回の SHA (WFBox=2 で `9e0251eb…`) が §17 の `aa3253b9…` と一致しない。インストール木の組立て差の可能性 | SHA の比較は同一環境内のみ有効 | #3052 |
| `s1_wine_probe.sh` の copy 部が `os.listdir` を block ごとに呼ぶ O(N²) (280 s で 20,572 ファイルで途切れた)。§19 の再現に手動補完が要る原因 | 再現の前提が手動 | #3052 |
| 全数 (82 + Demo 3) の書出し | 本 issue の対象外 | #3053 |

製品 KPI (flelift の起動 dispatch 数・通過 unit 数): 動かしていない (FLEngine の /R 書出しのみ。flelift は触っていない)。
