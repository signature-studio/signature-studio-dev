# REPORT 付録 — [SR-23 #1545] gate +0xdc の書込元 0x1800acf70 の所属 class と wrapper IID 応答の根拠

- 日付: 2026-10-14 / 親: #1360 (#256 SR-1c の残り) / 作業ブランチ: `1545-sr23-gate-writer`
- 測定 commit (コードを変えた最後の commit): **`83e6ff76faa17720a7a8891d4ff2d58ec748816e`** (origin/main 時点)。本 run はコードを変更していない (`host/` の変更は本付録のみ)。
- 素材: `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe` → `7z x`)。`Serum2_win64.vst3` sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` (19,236,864 B、`REPORT_SR1c.md` §1-0 と一致)。
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし (実 DLL の静的観測。lift 前)

## 0. 結論 (先出し)

1. **書込元 `0x1800acf70` の所属 class は `SerumController`**。vtable `0x180a2bee8` の slot 3 に登録されている (RTTI で確定)。REPORT_SR1c §4-3 の「IEditController 0xa2bf58」と「RTTI 無し・未確定」は誤記で、本付録で訂正する。
2. **wrapper IID (`IVst3ToAUWrapper` / `IVst3ToAAXWrapper`) に応答する一般 host の根拠は無い**。SDK の参照 host は両 IID を実装せず、`kResultFalse` を返す。既定 host の `kNoInterface` は SDK 参照実装と整合する。`S2HOST_WRAPPER_QI` の既定化は**行わない** (既定は無変更)。
3. e2e: **62/62 OK, 71.9 s** (測定 commit `83e6ff76`)。

## 1. 書込元の所属 class (受入 1)

### 1-1. RTTI による確定

- `.rdata` 上の vtable 候補 `0x180a2bee8` (RVA `0xa2bee8`) の直前 qword (`[-1]`) は COL `0x180a2c7c0` (RVA `0xa2c7c0`) を指す。COL の signature=1、`pSelf` が自身の RVA と一致 (MSVC x64 RTTI として妥当)。
- vtable `0xa2bee8` の `[-1]` が指す COL は `0xa2c7c0`。COL の `offset` = 16、TypeDescriptor 名 = **`.?AVSerumController@@`**。
- Class Hierarchy Descriptor (`0xa2c278`) の base 数 = 33。先頭は `SerumController`、次に `ISerumController`、`Vst::EditControllerEx1`、`Vst::EditController`、`Vst::IEditController`、`Vst::IEditController2`、`Vst::IUnitInfo` など、IEditController 系と IMidiMapping 等を継承する。
- 同一 `.rdata` 上に 2 つ目の vtable `0xa2bf58` (COL `0xa2c800`) があり、こちらも `.?AVSerumController@@` 名。`thunk 0x1800b4ea0` (`add rcx,-0x20; jmp 0x1800acf70`) が `0xa2bf70` (slot 3) に登録されている。

### 1-2. vtable 位置の実測 (`sr1c_callers.py` と `.rdata` 走査)

| 対象 | RVA | VA | 所属 | 位置 |
|---|---|---|---|---|
| `0xacf70` (書込関数) | `0xacf70` | `0x1800acf70` | SerumController | vtable `0xa2bee8` の slot 3 (`0xa2bf00`) |
| thunk `0xb4ea0` | `0xb4ea0` | `0x1800b4ea0` | SerumController | vtable `0xa2bf58` の slot 3 (`0xa2bf70`) |

- `0xacf70` を指す qword は `.rdata` 内に **1 件** (`0xa2bf00`)。直接 `call/jmp` 元は thunk `0xb4ea0` の 1 件のみ (`sr1c_callers.py 0xacf70`)。
- thunk `0xb4ea0` を指す qword は 1 件 (`0xa2bf70`)。直接 `call/jmp` は 0 件。

### 1-3. 呼出元 (実行時スタック)

- 書込関数の呼出は vtable 経由の間接呼出のため、静的には呼出元を一意に決められない (REPORT_SR1c §4-3 と同じ)。
- 実行時 watch の戻り番地候補: `RVA 0x48954d` (関数 `0x4894c0` 内、REPORT_SR1c §4-3)。`sr1c_callers.py 0x4894c0` で、この関数の直接の呼出元は `0x4890fe` の 1 件。
- `RVA 0x1134d60` は `.data` 範囲 (`.data` = RVA `0x1121000`〜) の値で、戻り番地ではない (REPORT_SR1c §4-3 の表記は誤り)。
- 残り: 関数 `0x4894c0` の所属 class と、上位の呼出連鎖 (controller 生成・initialize の内側か) は frame pointer 省略のため未追跡。

## 2. wrapper IID に応答する実 host の根拠 (受入 2)

### 2-1. IID の意味 (SDK, `work/vst3sdk` = `3cdf9ca`)

- `pluginterfaces/vst/ivsthostapplication.h`: `IVst3ToAUWrapper` は `[host imp]`、`[passed as 'context' to IPluginBase::initialize ()]`、`[mandatory]`。説明は「VST 3 to AU Wrapper が plug-in と実 host の間にあることを plug-in に知らせる。Implemented by the AU Wrapper」。`IVst3ToAAXWrapper` も同形 (AAX Wrapper が実装)。
- 両 IID の利用箇所は `public.sdk/source/vst/auwrapper/`・`aaxwrapper/` の wrapper 実装と、サンプル `note_expression_synth_ui.cpp:426`・`hostchecker/hostcheckerprocessor.cpp:77` のみ (`U::cast`)。

### 2-2. 参照 host の挙動

- `public.sdk/source/vst/hosting/hostclasses.cpp:63` `HostApplication::queryInterface`: `FUnknown` / `IHostApplication` の 2 IID のみ自前で返し、それ以外は `mPlugInterfaceSupport` (`IPlugInterfaceSupport`) に委譲する。該当しなければ `*obj = nullptr; return kResultFalse`。
- `IPlugInterfaceSupport` (`PlugInterfaceSupport`) に両 wrapper IID を登録する箇所は、本 run で確認していない (未確認)。

### 2-3. 判断

- 公開 SDK の参照 host は wrapper IID に応答しない。wrapper IID に応答するのは AU/AAX wrapper 自身 (plug-in と実 host の間の中間層) であり、一般 host (FL Studio 等) の応答は SDK からは根拠にならない。
- **実 FL Studio の応答は未観測** (FL 本体の PE 抽出を試みたが、`fl-win64` の展開物 `[0]` が 7z で開けず未確認)。よって「一般 host は応答しない」は**推定**であり、実機根拠ではない。
- 結論: `S2HOST_WRAPPER_QI` の既定化は**しない**。既定 host の `kNoInterface` は SDK 参照実装と整合する。実 host 応答の確認は Windows 実機 (FL Studio 本体の host 実装の観測) が前提で、起票対象とする (§4)。

## 3. e2e (受入 3)

- 実行: `bash tools/targets/serum2/host/e2e.sh` (`PATH` 先頭に pefile/capstone の venv)、実行 commit `83e6ff76`。
- 結果: **62/62 OK, 71.9 s** (`time` の real 1m11.917s、exit 0)。NC1・NC2 は期待どおり (exit=1, NG=1)。
- load: 開始時 (1 分値) 0.73 → 終了時 0.42。4 core、wine 9.0 (`wine64`)、逐次実行。
- 前提の確保: wine64 / g++-mingw-w64-x86-64 は apt で導入 (`apt-get update` 後)。素材は `plugins-serum2` を使用。`fl-win64` は §2-3 の実機観測の試行に展開したのみ (本 e2e では未使用)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FL Studio が `IVst3ToAUWrapper` / `IVst3ToAAXWrapper` に応答するかの実機観測 (§2-3)。`fl-win64` 本体 (`[0]`) は 7z で開けず未確認 | `S2HOST_WRAPPER_QI` の既定化判断 (現状は既定無変更) | #256 (既存の残件。本 issue の受入は SDK 記述で充足) |
| 書込関数 `0xacf70` の上位呼出連鎖と、関数 `0x4894c0` の所属 class | writer の完全な特定 | #256 (`REPORT_SR1c.md` §5 の残件: 全スレッド・wine watchpoint) |

## 5. 再現

```sh
cd tools/targets/serum2 && python3 host/sr1e_qi_map.py work/Serum2_win64.vst3 0x1800acf70
python3 host/sr1c_callers.py work/Serum2_win64.vst3 0xacf70 0xb4ea0
bash host/e2e.sh   # 62/62, 71.9 s (測定 commit 83e6ff76)
```

## 6. [SR-26 #1759] 実 FL Studio (fl-win64) の wrapper IID 観測と e2e 再測定

- 日付: 2026-10-14 / 親: #255 / 作業ブランチ: `1759-sr26-wrapper-iid`
- 測定 commit (コードを変えた最後の commit): **`899e4249`** (origin/main 取得時点)。本 run は `host/` のコードを変更していない。
- 素材: `fl-win64` = `flstudio_win64_26.1.7.5653.exe` (1,106,033,456 B, NSIS 単一 exe)。`plugins-serum2` = `Install_Xfer_Serum2_2.1.5.exe`。`Serum2_win64.vst3` sha256 `501e7bb3…4e5283` (19,236,864 B) は §1-0 と一致。

### 6-1. §2-3 の「未確認」の解消 (受入 1)

- §4 の「`fl-win64` 本体 (`[0]`) は 7z で開けず未確認」は**誤り**だった。exe 自体は `7z l` で開け、`[0]` (1,105,955,048 B) は 7z の 1 段目で展開される。ただし `[0]` は NSIS の圧縮データストリーム (先頭 `DEADBEEF` + `NullsoftInst`) で、7z では再展開できない (`Cannot open the file as archive`)。
- NSIS の LZMA ストリーム (`5d 00 00 80 00` props) を手動で展開した。PE (`MZ`) で始まるストリームは **312 個**、全て完全な PE (x64 `0x8664`) として再構成できた。
- FL 本体の抽出: `FL Studio` / `Image-Line` の UTF-16 文字列を持つ大型 PE (6〜47 MB) を含む。
- **実測**: 312 個の PE 全体を走査し、`IVst3ToAUWrapper` (`C5C6B8A3 95C08846 B0916F0B B697AA44`) と `IVst3ToAAXWrapper` (`C69D316D C5604262 B32C951B 93BEF4C6`) の 16 byte 列は**いずれの PE にも現れない** (0 件)。
- 解釈: FL Studio の PE に wrapper IID の定数が無い。よって FL 本体が `IPlugInterfaceSupport` 経由でこの 2 IID を返す実装を持つ根拠は、静的には見当たらない。これは「応答しない」の**強い示唆**であり、実行時の QI 応答そのものは未観測 (静的のみ)。
- 注意: 検索は INLINE_UID の LE バイト列のみ。IID を別経路 (文字列化・動的生成) で扱う実装は静的検索では拾えない。

### 6-2. 未実施 (受入 2 の残り)

- `0x4894c0` の所属 class と `0xacf70` の上位呼出連鎖は**今 run では未着手** (時間制限)。子 issue で扱う。

### 6-3. e2e 再測定 (受入 3)

- 実行: `bash tools/targets/serum2/host/e2e.sh` (worktree `ws-1759`、commit `899e4249`)。
- 結果: **62/62 OK, 77.3 s** (`time` real 1m17.303s、exit 0)。NC1・NC2 は期待どおり (exit=1, NG=1)。
- 前提: wine64 / mingw-w64 を apt で導入。`Serum2_win64.vst3` は `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` から複製。

### 6-4. 既定の判断 (受入 3 の判定)

- 静的観測 (§6-1) で FL 本体に wrapper IID が無いため、`S2HOST_WRAPPER_QI` の既定化は**行わない** (既定は無変更)。
- #255 受入 #3 (controller 側 A/B) の判定は、§6-2 (writer の上位連鎖) が未特定のため、**未確定**のまま残る。
