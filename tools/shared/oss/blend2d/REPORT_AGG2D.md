# Agg2D glue 棚卸し — 実測 (T-SH-02, #146)

> **正本**: 本ファイル (Agg2D glue の実測)。結論と索引は `tools/shared/REPORT.md`。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_inventory.py`
> (依存: `pefile`)。出力は `tools/shared/work/agg2d_inventory.json` (gitignore)。
> 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf fl-win64.tar.zst`、11.9 s)。

## 1. 対象 DLL の同定

- `classify.py` の `win=("Blend2D.dll", 24339)` に従い **`extracted/block24339_PE.bin`** を対象にした。
- `AggCreateInstance` を export する PE は **`dsp_ippv2` (block24356) と block24339 の 2 つ**ある。名前だけで
  探すと dsp_ippv2 を拾う (初版スクリプトの誤り)。そのため DLL 番号で固定した。
- PE32+ DLL x86-64, 2,065,920 B, sha256 先頭 16 桁 `66634d24412084b7`。

## 2. 実測

| 項目 | 値 | 根拠 |
|---|---|---|
| section | `.text` 1,790,469 B / `.rdata` 232,660 / `.data` 1,067,956 | pefile |
| export | **1 本** (`AggCreateInstance`) | pefile `DIRECTORY_ENTRY_EXPORT` |
| import | **KERNEL32.dll 94 本のみ** | pefile (Blend2D 本体・asmjit は静的リンク) |
| RTTI クラス名 (`.?AV`) | **44 個** (Fe 10 / Ba 6 / Fi 5 / Co 3 / ba 3 / Ag 2 / 他) | 文字列走査 |
| うち Agg2D | `.?AVAgg2D@?A0x604ded79@@`・`.?AVAgg2DIntf@@` の **2 個** | 同上 |
| `bl[A-Z]` で始まる文字列 | **0 個** | 文字列走査 |

## 3. 判明したこと / 判明しなかったこと

- **判明**: Blend2D 本体は DLL 内に静的に入り、公開シンボル (export) は `AggCreateInstance` の 1 本だけ。
  Agg2D の外部 API は 1 本に絞られている。
- **判明**: issue の「~140 symbol」は **export でも RTTI でも再現できない**。140 という数は、
  `AggCreateInstance` が返す Agg2D インタフェースの vtable のメソッド数、または内部関数数の推定と思われる
  (**未検証**)。数え方を決めるには vtable の実体を逆アセンブルする必要がある。
- **未判明**: Agg2D が公開するメソッドの一覧、vtable の位置と長さ、各メソッドが内部で呼ぶ Blend2D API。
  これは逆アセンブル (Ghidra / capstone 等) なしには確定できない。本 run では未実施。
- 以上より「lift か C++ 再実装か」を決める材料は、現時点で **export 1 本 + Agg2D RTTI 2 個 + 静的リンクされた Blend2D** まで。
  glue の規模 (symbol 数・依存) はまだ確定していない。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~Agg2D の vtable / メソッド数の確定 (逆アセンブル)~~ | 解決: §5 で 130 slot / 79 unique を実測 | 完了 (§5) |
| lift か C++ 再実装かの方針決定 | 本採用の実装に入れない (REPORT_SIMD.md §4 と同じく人判断) | #146 (PM/ユーザ判断) |
| FL 実描画経路の画素比較 | 本 run では未実施 (fl-win64 は展開済みだが描画経路の harness が無い) | #146 (継続) |
| FL が使う Blend2D commit の symbol 集合比較 | pre-v0.20 の近似のまま。export が 1 本のため symbol 比較の手段が要再設計 | #146 (継続) |

## 5. vtable の実測 (逆アセンブル)

> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_vtable.py`
> (依存: `pefile`・`capstone`)。出力は `tools/shared/work/agg2d_vtable.json` (gitignore)。

- `AggCreateInstance` (`0x180059a60`) は `0x1170` B を確保し、`0x1800568a0` のコンストラクタに tail-jump する。
- コンストラクタは `lea rax,[rip+0x185607]` で vtable (VA `0x1801DBEC0`) を先頭に書く。
- vtable は `.text` 内を指す qword が **130 slot** 連続し、終端値 `0x504d42` (コード外) で止まる。

| 項目 | 値 | 根拠 |
|---|---|---|
| vtable slot 数 | **130** | `agg2d_vtable.py` |
| 相異なる関数 (unique target) | **79** | 同上 |
| 種別 (unique) | code 76 / trivial_ret 3 | 先頭命令の判定 (capstone) |
| 種別 (slot 単位) | code 76 / trivial_ret 54 | 同上 |

**判明**: 「~140 symbol」の出所は、vtable slot 130 に近いが一致しない。slot 数は 130、関数は 79。
140 という数は再現できないので、本文の「~140」は **旧推定値** として扱う。

**未判明**: 各関数が呼ぶ Blend2D API、引数の型、Agg2D のどのメソッドが FL から実際に呼ばれるか。
lift か C++ 再実装かの判断には、この依存の確定が要る。`trivial_ret` 54 slot は共通スタブの可能性がある (未検証)。
