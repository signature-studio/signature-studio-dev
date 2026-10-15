# tools/shared/elastique REPORT — FL 本体からの LoadSharedElastiqueDll の呼出元 (T-SH-123 / #4396)

親: #3386。素材 `fl-win64` (FL 本体 `block00031_PE.bin`)。mac 版は対象外。所有者限定 tier (D20)。

## 0. 結論

| 項目 | 結果 |
|---|---|
| 受入 (FL 本体 PE から élastique export の呼出し形を同定) | **達成**。`block00031_PE.bin` (FL 本体, .text RVA 0x401000) で、`LoadSharedElastiqueDll` を名前で解決するローダ `0x677d10` の直接呼出元 5 箇所を特定し、各 wrap が呼ぶ élastique export (`ElPro_CreateInstance`・`ElProV3_CreateInstance`・`ElResampleSource_CreateInstance`・`Auftakt_CreateInstance`・`SolPitchAn_CreateInstance`) を対応付けた |
| 同定の方式 | 静的。UTF-16LE の名前を指す RIP 相対 `lea` → 関数 → 直接 call/jmp の逆引き。動的実行は行っていない |
| 親 #3386 の受入 2 (同定した引数での実行) | 本 issue の範囲外。親に残す |

## 1. 呼出し形

FL 本体の 2 段構成である。

1. **ローダ** `0x677d10` (`block00031`・.text): `lea rdx,[rip+0x103]` で UTF-16 の `LoadSharedElastiqueDll` (VA `0x677e28`) を取り、`call 0x4235f0` で解決する。解決関数 `0x4235f0` は `shr rax,0x10` の結果が非 0 (引数の上位 16 bit が立つ = 序数でなく名前) のとき、名前として `GetProcAddress` 相当 (`0x4235e0`) を呼ぶ。`LoadSharedElastiqueDll` の export の RVA は `block24350_PE.bin` (QuickFontCache, x64) が `0x186c90`、`block24349` (i386) が `0xf713c`。
   - 解決に成功すると `call rax` (解決した `LoadSharedElastiqueDll`) を呼び、続けて各 élastique export 名を `0x4235f0` で解決して、ローダ内の 8 スロットに格納する。
   - スロット (`fl_loader_callers.py` の出力): `0x15f4860` = ElPro_CreateInstance、`0x15f4868` = ElProDirect_CreateInstance、`0x15f4870` = ElProV3_CreateInstance、`0x15f4878` = ElProV3Direct_CreateInstance、`0x15f4880` = ElResampleSource_CreateInstance、`0x1505be0` = Auftakt_CreateInstance、`0x16b8890`・`0x16b8898` = SolPitchAn_CreateInstance。
   - 失敗時はローダ内のスロット `0x15f4850` を 0 にして 0 を返す (`0x677d2f`・`0x677e0d`)。
2. **wrap** (ローダを呼んだ後に、解決済みスロットを呼ぶ関数):

| 直接呼出元 (call) | wrap 関数 | wrap が呼ぶスロット → export | wrap の呼出元 |
|---|---|---|---|
| `0x677f7c` | `0x677f60` | `call [0x15f4860]` → ElPro_CreateInstance | `0xa977d1` (in `0xa97780`) |
| `0x677fcc` | `0x677fb0` | `call [0x15f4870]` → ElProV3_CreateInstance | `0xa97805` (in `0xa97780`) |
| `0x678030` | `0x678010` | `call [0x15f4880]` → ElResampleSource_CreateInstance | `0x67d60d` (in `0x67d5a0`) |
| `0xc6753f` | `0xc67520` | `call [0x1505be0]` → Auftakt_CreateInstance | `0xc67789` (in `0xc67730`) |
| `0xc69c2a` | `0xc69c10` | 同一関数内で `0x4235f0` が SolPitchAn 名を解決し `call rax` (スロットは `0x16b8890`・`0x16b8898`) | `0xc69d28` (in `0xc69d10`)・`0xc69d67` (in `0xc69d60`) |

`0xc69c10` は `call [slot]` ではなく `call rax` (解決した関数ポインタ) で呼ぶため、スクリプトの自動対応には出ない。手で確認した (§2 の確認 4)。
ローダ内の ElProDirect・ElProV3Direct のスロット (`0x15f4868`・`0x15f4878`) を呼ぶ wrap は、この 5 呼出元の中には無い (§3)。

## 2. 確認

1. **名前参照の数** (`lea` の RIP 相対で UTF-16 名を指す): `LoadSharedElastiqueDll` は 1 箇所 (`0x677d1e`)。`QuickFontCache_x64.dll` は 1 箇所 (`0x653321`・`0x6532f0` 内の QFC ローダ)。
2. **文字列の所在** (素材内の全ファイルの部分一致): ASCII の `LoadSharedElastiqueDll` は `block24349`・`block24350` の 2 件 (QuickFontCache の export 表)。UTF-16LE の `LoadSharedElastiqueDll` は **50 件** の PE にあり、そのうち FL 本体 `block00031` を含む。残り 49 件の PE は本 REPORT では読んでいない (§3)。
3. **export と呼出しの関係**: `block24349` (i386) と `block24350` (x64) の export `LoadSharedElastiqueDll` は QuickFontCache 側の定義。FL 本体 `block00031` は export 表を引かず、UTF-16 名を `0x4235f0` で解決する。
4. **`0xc69c10` の呼出し形**: 手で逆アセンブルし、`0x4235f0` の結果を `call rax` で呼ぶことを確認した。
5. **再現**: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/shared/elastique/fl_loader_callers.py`。測定 commit `fc97566e2` (スクリプト・REPORT の最終変更)。コミット済み HEAD `64792bdca` で再実行: rc 0・経過 38.9 s・load 0.09→0.54 (nproc 4・出力は上の表と一致)。コードの差分は 0 (`fl_loader_callers.py` は測定 commit から変わっていない)。REPORT 本文のみ後続の commit で変えた (`git diff fc97566e2 HEAD -- tools/shared/elastique/fl_loader_callers.py` は 0 行)。

## 3. 限界

- 静的解析である。動的な確認 (ローダの実行・export の呼出し) は行っていない。`0x4235f0` の GetProcAddress 相当の戻り値は、解決した名前が実際に実行時に一致するかを確かめていない。
- UTF-16 名を持つ他の 49 PE (例: `block18797`・`block19220`) は、同じ形のローダを持つかを確かめていない。
- wrap の直接呼出元の検出は rel32 の `call`/`jmp` に限る。関数ポインタ経由の呼出しは数えていない。
- wrap を呼ぶ上位の関数 (`0xa97780`・`0x67d5a0`・`0xc67730`・`0xc69d10`・`0xc69d60`) の機能 (どの FL の機能が élastique を使うか) は未同定。
- ローダの戻り値が 0 のときの経路 (élastique が見つからない場合) の挙動は、呼出元ごとには確かめていない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 上位の関数 (`0xa97780`・`0x67d5a0`・`0xc67730`・`0xc69d10`・`0xc69d60`) が FL のどの機能か | 受入 2 の引数を決める | 親 #3386 (受入 2) |
| ローダの動的実行による確認 | 静的の結論の裏付け | 親 #3386 |
