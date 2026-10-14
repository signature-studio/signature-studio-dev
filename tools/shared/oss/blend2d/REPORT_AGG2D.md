# Agg2D glue 棚卸し — 実測 (T-SH-02, #146)

> **正本**: 本ファイル (Agg2D glue の実測)。結論と索引は `tools/shared/REPORT.md`。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_inventory.py`
> (依存: `pefile`)。出力は `tools/shared/work/agg2d_inventory.json` (gitignore)。
> 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf fl-win64.tar.zst`、11.9 s)。

## 1. 対象 DLL の同定

- `classify.py` の `win=("Blend2D.dll", 24339)` に従い **`extracted/block24339_PE.bin`** を対象にした。
- `AggCreateInstance` を export する PE は **3 つ** (`block24339` (Blend2D.dll)・`block24355`・`block24356` (dsp_ippv2)) ある。
  名前だけで探すと dsp_ippv2 を拾う (初版スクリプトの誤り)。そのため DLL 番号で固定した。
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
| `block24356_PE.bin` | 446 | `sub rsp,0x28; mov ecx,0x1aec; call ...` | IPP 系 + AGG 同梱 (付録 §12 で比較) |

**判明**:
- `AggCreateInstance` という名前の export は fl-win64 内に **3 本** ある。`block24356` は IPP 系 DLL だが AGG を同梱し `AggCreateInstance` を持つ (付録 §12 で比較)。`block24355` は先頭の形が別で、比較対象外。§1〜§7 の対象は `block24339` だけで、正しい。
- `AggCreateInstance` を import 名で参照する PE は **0 件** (313 PE を走査)。文字列としても 3 PE にしか現れない。`GetProcAddress` は 254 ファイルに現れるが、本 run では解決先を追っていない。
- `Blend2D`・`blend2d` の文字列は DATA を含む複数ファイルに現れる。`block25162_PE.bin` の一致は素材ファイル名 (`Baggy` 等) による偶然の一致で、Blend2D 本体ではない。

**未判明**: FL 本体が `block24339` の `AggCreateInstance` をどこから呼ぶか (呼び出し元の特定)。名前 import が無いため、`GetProcAddress` の引数の文字列を追うか、呼び出し側の関数ポインタ参照を探す必要がある。受入条件 (b) の画素比較の起点はこの未判明の箇所に依存する。

## 9. x64c による lift 可否の実測 (閉包の深さ別)

> 測定 commit: `53b584d8` (`agg2d_vtable.py` の import 用定数を戻した commit)。`git diff 53b584d8 HEAD -- tools/flelift/x64c.py tools/shared/oss/blend2d/*.py` は 0 行 (以後に変えたのは本 REPORT と `docs/DOC_MAP.md` のみ)。前回測定 (`87d5c6ad`) の鮮度主張は、main 取り込みで x64c.py が変わっていたため成り立たなかった。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_lift_probe.py` (依存: `pefile`・`capstone`、測定 4.36 s)。出力は `tools/shared/work/agg2d_lift_probe.json` (gitignore)。
> lifter は `tools/flelift/x64c.py` (FLEngine 向け fork)。`--img 0x180000000 --img-size 0x300000` (block24339 の ImageBase / SizeOfImage)、roots は §5 の unique 79 VA。

| 閉包の深さ (`--closure`) | 関数 | 命令 | 未対応 site | 未対応 mnemonic 種 | 未 lift の直接 call (件) | 使用 import |
|---|---|---|---|---|---|---|
| 0 | 79 | 4,265 | 0 | 0 | 107 | 0 |
| 1 | 110 | 9,007 | 92 | 12 | 36 | 2 |
| 3 | 168 | 22,681 | 220 | 23 | 26 | 7 |
| 50 | **221** | 27,684 | **363** | **33** | **0** | 27 |

**判明**:
- 直接 call の閉包は depth 50 で使い切れる (未 lift の直接 call 0)。vtable 79 関数から到達する内部関数は x64c の閉包で **221** (§6 の `agg2d_callees.py` は **217**。217 は 221 の下限)。
- 差 4 は集合差で特定した (`agg2d_callees` ⊂ x64c)。原因は走査の違い: `agg2d_callees.py` は間接 `jmp reg` で走査を止め、x64c は jump table (switch) の case 先を辿る。4 件の到達経路 (生成 C `fle_lifted.c` depth 50 で確認):
  - `0x1801b4b60`: `f_180070e50` の switch (`0x180070ea7: jmp r9`) の case `0x180070f73` と `0x18007124c` から呼ばれる (呼び出し元ブロックが case 先)。
  - `0x1801b5120`・`0x1801b5a34`: 呼び出し元は `0x1801b4b60` のみ。`0x1801b4b60` と同じ経路。
  - `0x180072e20`: `f_180074590` の 2 ブロック (`0x180074fcf`・`0x180075069`) から呼ばれる。この 2 ブロックは生成 C の制御フロー (goto と switch の辺、近似) で、`0x18007462c: jmp rcx`・`0x180074697: jmp rax` の switch 経由でのみ到達する。binary 上での確認は未実施。
- depth 50 の未対応 site 363 件 (33 mnemonic) の上位: `vfmadd213sd` 53・`vmulsd` 50・`vmovsd` 47・`vaddsd` 40・`vsubsd` 37・`vmovq` 28 (残りは VEX スカラー FMA・整数 SSE/AVX・非テンポラル store `movntps`/`vmovntdq` 23 等)。x64c はこれらを未対応として記録し、C への変換を持たない。
- 未対応 site は `ott_unsup` (実行時 abort) として出力される。到達するかは未検証 (実行トレースが要る)。

## 10. CFG 間接 call の lowering (x64c の不具合候補)

| 項目 | 値 | 根拠 |
|---|---|---|
| x64c の扱い | `call [slot]` / `jmp [slot]` (RIP 相対、IAT 以外) を `ott_dispatch(LD64(slot))` に落とす。`mov reg,[slot]; call reg` は `R[k] = LD64(slot)` の後に `ott_dispatch(R[k])` | `tools/flelift/x64c.py` `i_call` / `i_jmp` (宛先を rax 経由で取らない) |
| 閉包 (depth 50) で slot を読み `ott_dispatch` に流す箇所 | **8** = 直接形 6 (`jmp/call [slot]`) + レジスタ経由形 2 (`mov rdx,[slot]; call rdx`)。slot `0x1801b7308` = GuardCFDispatch | `agg2d_lift_probe.py` の `indirect_dispatch` (`reads=8 sites=8 direct=6 via_reg=2`)。生成 C の `LD64(0x1801b7308ULL)` の出現も 8 (grep) |
| slot の値 | `0x1801b5b90`、bytes `ffe0` (`jmp rax`) | 同上 (PE の `.rdata` から読んだ値) |
| dispatch 表に値があるか | **無い** (`case 0x1801b5b90ULL:` が `ott_dispatch` 本体に無い) | 同上 |
| ネガティブコントロール | 既知値 `0x180009ea0` (表に有り) → `True`、`0x1801b5b90` → `False`。probe が毎回検査し、外れたら非 0 で終了 (WORKFLOW §5) | `agg2d_lift_probe.py` の `control` |
| 到達時の挙動 | `ott_dispatch` の default → `ott_unlifted` (`tools/flelift/rt/fle_cpu.c`)。hook 無しは abort、hook 有りは戻り値 0 扱いで続行 (silent) | `fle_cpu.c` |
| 既知の対応 | `tools/icall/REPORT.md` の D13 (MSVC CFG thunk): `rax-in` を保持し、thunk 経由で実 target に解決する処理が既にある。**x64c 経路には未移植** | `tools/icall/REPORT.md` |

**判明**: x64c の CFG 間接 call は、宛先を rax で渡す thunk (`jmp rax`) の値を dispatch し、実 target を見ていない。閉包内の 8 箇所 (直接形 6 + レジスタ経由形 2) が該当する。
**判明 (dispatch 全体)**: 閉包 50 の `ott_dispatch(t_)` 行は全 85 件。slot 由来の 8 件以外の 77 件 (メモリ間接 `LD64(R[k]+d)` 等 15 件、レジスタ値 62 件) は、本 probe では出所を見ていない。
**未検証**: 到達頻度 (dynamic trace が要る)。`.text` 全体の `call [rip+disp]` (`ff 15`) で CFG スロットを指す 42 件 (§6・§7。母集団は `.text` 全体で、閉包外を含む。閉包内の 8 件とは別) の扱い。閉包 50 の `ott_dispatch` の残り 77 件の出所。

## 11. (a) の判断材料と未解決

- 指示 54 (`docs/pm/DIRECTIVES.md`、2026-10-10): 「upstream からビルドできるものはビルドし、難しいものは lift」。Blend2D 本体は upstream build 済み (`tools/shared/REPORT.md` §3.3)。
- 閉包 221 関数のうち、Blend2D 本体の内部関数と Agg2D glue の帰属は**未判定** (§9 の閉包は両者を含む)。帰属が決まれば、「glue のみ C++ 再実装 + 本体は upstream build」が取れるかが判断できる。
- x64c を使う lift 経路は、閉包 221 関数に対して未対応 33 種と CFG rax-in 欠落がある。lift を採るならこの 2 点の解消が前提。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 221 関数の Blend2D 内部 / Agg2D glue の帰属 (upstream blend2d fc827d5 との照合) | lift か C++ 再実装かの判断の中心 | #146 (次の測定候補) |
| (a) 方針 (lift / C++ 再実装) の決定。指示 54 の当てはめの確認。**PM agent の判断待ち: lift か C++ 再実装か (指示 54 の当てはめ)・既定案: glue のみ C++ 再実装 (Blend2D 本体は upstream build 済みを使う)** | 実装に入れない。既定案の前提 (glue の範囲) は帰属の測定が要り、未検証 | #146 (PM/ユーザ判断) |
| x64c の CFG rax-in 対応 (§10)・未対応 33 種 (§9) | lift 採用時の必須項目。silent 経路の恐れ | #146 (方針決定後に子 issue 化) |
| (b) FL 実描画経路の画素比較 harness | 受入条件 (b) 未達 | #146 |
| (c) symbol 集合比較の手段 | 受入条件 (c) 未達 | #146 |


## 12. vtable の slot 単位比較: Blend2D.dll と dsp_ippv2

結論: 2 DLL の vtable を slot 単位で比較した。差分と未検証事項は `REPORT_APPENDIX_AGG2D.md` §12。

## 13. AggCreateInstance の呼び出し元の手がかり

結論: block18797 に lazy 初期化 loader がある。消費側は未特定。測定値は `REPORT_APPENDIX_AGG2D.md` §13。

## 14. vtable の所属クラス (MSVC RTTI の COL)

> 測定 commit: `bef37ac3` (`agg2d_rtti.py` に vtable 書き込み箇所の走査を追加した commit)。`git diff bef37ac3 HEAD -- tools/shared/oss/blend2d/*.py '*.sh'` の出力は 0 行 (以後の変更は本ファイル・`tools/shared/REPORT.md`・`REPORT_SIMD.md` の文言のみ)。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_rtti.py [出力 JSON]` (依存: `pefile`・`capstone`)。所要はプロセス全体の wall で n=3 の min–max **129–130 ms** (load average 1 分値 0.12、nproc 4、各回の前後で同値)。出力の既定は `tools/shared/work/agg2d_rtti.json` (gitignore)。vtable VA は `agg2d_vtable.py` の検出関数を流用。

| 項目 | 値 | 根拠 |
|---|---|---|
| vtable VA | `0x1801dbec0` (§5 と一致) | `agg2d_vtable.py` の検出 |
| COL VA (`vtable[-1]`) | `0x1801e29b8` | x64 COL (signature = 1) |
| 所属クラス | `.?AVAgg2D@?A0x604ded79@@` (Agg2D、無名名前空間) | COL → TypeDescriptor |
| 基底クラス | `.?AVAgg2DIntf@@` の 1 個 | ClassHierarchyDescriptor |
| 同じ COL を指す vtable | **1 個** (本 vtable 自身のみ。その vtable は 130 slot) | `.rdata` 全 qword 走査 |
| `Agg2DIntf` の COL / 独立 vtable | **0 / 0** | 同上 |
| vtable を書く RIP 相対 `lea` | **2 か所**: `0x1800568b2` (ctor `0x1800568a0` 内、§5 の箇所)・`0x180056add` (関数 `0x180056ad0` 内) | `.text` のバイト走査 (`rip_lea_hits`: REX.W `8d` の disp が vtable を指すもの) を capstone で `lea` と確認 |

**ネガティブコントロール** (WORKFLOW §5): vtable VA を +8 した scratch (`git archive bef37ac3` の複製、出力は `$RUNNER_TEMP`) で `agg2d_rtti.py` を実行すると **rc=1** で `vtable[-1] = 0x180056700 が .rdata 外。COL ではない` と終了し、JSON は出ない。書き込み走査も VA `0x1801dbec8` (+8) で **0 件** (VA は 2 件)。

**判明**:
- 130 slot の vtable は Agg2D 具象クラスの vtable で、DLL 内で COL を指す vtable は 1 個。`AggCreateInstance` が返すオブジェクトの vtable はこれに限られる。vtable を書くのは **2 か所** (ctor `0x1800568b2`、`0x180056ad0` の関数)で、どちらも同じ vtable `0x1801dbec0` を書く (RIP 相対 lea の走査による。絶対アドレスによる書き込みは本測定の対象外で、未検証)。
- `0x180056ad0` (先頭命令 `mov [rsp+8],rbx` から関数の先頭と見なした) は、先頭で `[rcx]` に vtable を書き、続けて `mov rcx,[rcx+0x160]` の後に `lock xadd [rcx-0x10]` を行う。デストラクタ等の可能性があるが、役割は未検証。
- (a) の glue の範囲の上限は、この vtable の **実体 81 slot (unique 78 関数)**。残り 49 slot は同一の `ret 0` (`0x18000c530`、`REPORT_APPENDIX_AGG2D.md` §12)。
- `Agg2DIntf` は独立 vtable を持たない。FL 側がどのインタフェース型で呼ぶかは、Agg2D vtable の slot 順に依る (単一継承の slot 順は未検証)。

**未判明**:
- FL 本体がどの slot を実際に呼ぶか。静的には消費側 (vtable の呼び出し箇所) を特定できていない (§13)。
- 78 関数の役割と、各関数が呼ぶ Blend2D API の名前 (export・シンボル無し)。

**判断への影響**: (a) の既定案 (glue のみ C++ 再実装) の範囲は「FL が呼ぶ slot 集合」と「各 slot の呼び先 Blend2D 内部関数」で決まる。前者は静的測定では決まらず、実行時の vtable 呼び出し記録が要る。その記録は FLEngine の boot が最初のウィンドウに届くことが前提で (`tools/flelift/boot/REPORT.md` §9 は unit 209 で停止)、(b) の画素比較と同じ依存。(a) と (b) は boot の進行に依存し、本 issue 単独では前進しない。
