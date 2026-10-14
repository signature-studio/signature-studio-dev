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

## 6. vtable 各関数の依存 (呼び出し先の推移閉包)

> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_callees.py`
> (依存: `pefile`・`capstone`)。出力は `tools/shared/work/agg2d_callees.json` (gitignore)。
> 各 root から直接 call/jmp で到達する内部関数を再帰で辿り、IAT (`call [rip+disp]`) の import を集計する。

| 項目 | 値 | 根拠 |
|---|---|---|
| unique root (vtable 関数) | **79** | §5 と同じ |
| 内部関数の到達数 (全 root の和集合) | **217** | `agg2d_callees.py` |
| 2 root 以上から到達する内部関数 | **97** | 同上 |
| 到達数 (root 別) | 1〜83 (中央値 32) | 同上 |
| import に到達する root | **42 / 79** | 同上 |
| 到達する import の種類 | **28** (KERNEL32 の名前付き 27 件 + CFG dispatch スロット 1 件) | 同上 |

- 42 root が共通に到達する import: `EnterCriticalSection`・`LeaveCriticalSection`・`HeapAlloc`・`HeapFree`・`GetLastError`・`SetLastError`・`TlsGetValue`・`TlsSetValue`・`LoadLibraryExW`・`GetProcAddress`・`FreeLibrary` と、CFG dispatch スロット 1 件 (下記)。
- 16 root が共通に到達する import: `RaiseException`・`RtlCaptureContext`・`RtlLookupFunctionEntry`・`RtlVirtualUnwind`・`UnhandledExceptionFilter`・`SetUnhandledExceptionFilter`・`IsProcessorFeaturePresent`・`GetCurrentProcess`・`TerminateProcess`。例外処理・フェイルファスト系の共通経路と読める (**未検証**)。
- 「exclusive」 (その root だけが到達する内部関数) は大半が **1 (root 自身)**。Agg2D 固有の実装量は小さく、大部分は共有の Blend2D 内部関数に依存している可能性が高い (**未検証**)。

**判明**: 79 root のうち内部呼び出し先を持たない (`reachable_funcs` = 1) のは **34 / 79**、到達数 5 以下は **37 / 79**。到達数の中央値は 32 で、root により差が大きい。2 root 以上から到達する内部関数は 217 中 **97**。
**未判明 / 制約**:
- 間接 call (`call reg`・`jmp reg`) は辿れない。推移閉包は**下限**。
- `unresolved@1801b7308` の正体を特定 (実測): VA `0x1801b7308` は PE load config の **`GuardCFDispatchFunctionPointer`** (Control Flow Guard の間接 call ディスパッチ用スロット)。中身は `jmp rax` の thunk (VA `0x1801b5b90`)。IAT ではない。`call [rip+disp]` で同スロットを呼ぶ箇所は **42 件** (`ff 15` の全走査で確認)。つまり 42 root が到達するのは「関数ポインタ経由の間接 call」で、その先の実体は本スクリプトでは辿っていない。`agg2d_callees.py` は当該スロットを `CFG!GuardCFDispatch` とラベルし直した (旧 `unresolved@` 表記は廃止)。
- 本スクリプトは線形スイープを行わず、vtable の root から call/jmp で到達する関数だけを集計する。到達しない `.text` 領域は集計外で、全体の網羅は未実施。
- 「Blend2D API の名前」は特定できていない (export 無し・シンボル無し)。関数の役割 (描画 / パス / 画素処理) は未判定。

**結論**: vtable の規模は確定 (§5)。依存は「共有ヘルパ + KERNEL32 の少数 import」に寄るが、lift 対象の実質規模 (間接 call 込み、関数の役割) は未確定のため、lift か再実装かの決定は本 run ではしない。

## 7. CFG 間接 call の宛先の静的解決 (試行と結果)

> 目的: §6 で未確定の `GuardCFDispatchFunctionPointer` 経由 call の宛先を、直前の定数ロードから解決する。
> 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (5.4 s)。解析は capstone の逆アセンブルのみ。

| 項目 | 値 | 根拠 |
|---|---|---|
| CFG スロット (VA) | `0x1801b7308` | load config |
| `ff 15` (call [rip+disp]) で CFG スロットを指す箇所 | **42 件** | `.text` のバイト走査 (§6 の 42 と一致) |
| 直前 8 命令の窓に `lea rax,[rip+X]` (定数) がある箇所 | **0 件** | 直前 8 命令の窓を実測 |
| 確認した直前の rax 設定 (例) | `mov rax, r14`・`mov rax, rdi` 等 | 同上 |

**判明**: `lea` 定数追跡の 8 命令窓では、42 件とも宛先を解決できなかった (窓内に `lea rax,[rip+X]` が 0 件)。
**未検証**: 以下は今回の測定の対象外で、解決できるかどうかは分かっていない。
- `mov rax,[rip+X]` (データ領域のポインタ読み出し) や、別レジスタに `lea` してから rax へ `mov` する形
- 8 命令より前で rax が決まるケース
- 他の命令形 (例: `mov eax, esi`・`mov eax, [rax+0x10]`) の扱い
**未判明**: 宛先の候補集合。解決にはデータフロー解析 (レジスタ・スタックの値の伝播) か、実行トレースが要る。定数 lea 追跡は閉じない (他の経路は未検証)。
**未検証**: 線形スイープは `0x180001b82` 付近で止まるため、`.text` 全体の命令列からの集計は未完 (§6 の制約と同じ)。
**扱い**: 解析スクリプトは作業ツリーに残していない (定数追跡で有用な出力が出ないため)。再開するなら、データフロー解析か動的トレース (fl-win64 の実行) の方式を先に決める。

## 8. AggCreateInstance の export 元 (3 DLL 比較)

> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_exports.py` (依存: `pefile`・`capstone`、約 0.5 s)。

| PE (extracted 配下) | export 数 | AggCreateInstance の先頭命令 | 判定 |
|---|---|---|---|
| `block24339_PE.bin` | 1 | `sub rsp,0x28; mov ecx,0x1170; call ...` (§5 と同じ) | Blend2D 本体 (本 REPORT の対象) |
| `block24355_PE.bin` | 446 | `push 0x19f8; call ...` | Intel IPP 系 (`ipps*`・`ippi*` の export が大半、`IPPCODE` section) |
| `block24356_PE.bin` | 446 | `sub rsp,0x28; mov ecx,0x1aec; call ...` | IPP 系 (同上) |

**判明**:
- `AggCreateInstance` という名前の export は fl-win64 内に **3 本** ある。ただし `block24355`・`block24356` は IPP の DLL で、Agg2D とは無関係。§1〜§7 の対象は `block24339` だけで、正しい。
- `AggCreateInstance` を import 名で参照する PE は **0 件** (313 PE を走査)。文字列としても 3 PE にしか現れない。`GetProcAddress` は 254 ファイルに現れるが、本 run では解決先を追っていない。
- `Blend2D`・`blend2d` の文字列は DATA を含む複数ファイルに現れる。`block25162_PE.bin` の一致は素材ファイル名 (`Baggy` 等) による偶然の一致で、Blend2D 本体ではない。

**未判明**: FL 本体が `block24339` の `AggCreateInstance` をどこから呼ぶか (呼び出し元の特定)。名前 import が無いため、`GetProcAddress` の引数の文字列を追うか、呼び出し側の関数ポインタ参照を探す必要がある。受入条件 (b) の画素比較の起点はこの未判明の箇所に依存する。
