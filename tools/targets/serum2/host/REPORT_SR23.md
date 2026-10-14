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

## 6. [SR-27 #1836] 書込関数 0xacf70 の上位呼出連鎖と 0x4894c0 の所属

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (実 DLL の静的・動的観測。lift 前)。
素材: `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe` → `7z x`)。`Serum2_win64.vst3` sha256 `501e7bb3…5283` (§0 と一致)。

- 測定 commit (コードを変えた最後の commit): **`5cb1fa6f`** (`feat(serum2-host): unwind watch call chain via .pdata`)。本節の変更は `host/vst3host.cpp` (opt-in の `S2HOST_WATCH` 内のみ) と `host/sr27_dis.py` (静的補助)。既定経路は無変更。
- 結論 (先出し):
  1. **§1-3 の `RVA 0x48954d` を「0xacf70 の呼出元」とした記述は誤り**。`0x48954d` は関数 `0x4894c0` 内の戻り番地ではあるが、呼出連鎖上の frame ではない (下記 6-2)。
  2. **0xacf70 の実行時の直接呼出元は host (`vst3host.exe`) の `ctrl->initialize` 呼出** (IPluginBase slot 3, `call [rax+0x18]`、戻り番地 `0x2bd2a`)。plugin 側の中間 frame は unwind に現れない。連鎖は `host の run 関数 (0x2ae20, ctrl 生成を含む) → ctrl->initialize (slot 3) → (thunk 0xb4ea0 の tail jump 経由と推定) → 0xacf70`。つまり **controller の initialize の内側**で `+0xdc` へ書かれる。
  3. **`0x4894c0` は SerumController ではなく `MenuData` 系の ctor (0x488fc0, vtable `0xa85f28` = `.?AVMenuData@@`) から呼ばれる補助関数**。0x4894c0 自体はどの class の vtable にも現れない (非メンバ)。wrapper / gate の書込とは無関係。

### 6-1. 0xacf70 の実行時呼出連鎖 (unwind, .pdata)

- 方法: 旧版の「RSP から 64 語を戻り番地候補として列挙」は frame pointer 省略で誤読を生んだ。`vst3host.cpp` の watch hit 時に `RtlLookupFunctionEntry` / `RtlVirtualUnwind` で .pdata の unwind 情報から連鎖を辿るよう変更 (`5cb1fa6f`)。
- 実測 (`S2HOST_WATCH=1` 既定 host, 4 blocks, 2 回再現で同一):
  ```
  [watch] armed DR0=…(controller iface+0xdc)
  [watch] hit#1 RIP=00006ffff8af1338 (Serum2_win64.authstub.vst3) value=2
  [unwind] d=0 RIP=…8af1338 mod=Serum2_win64.authstub.vst3 fn=0xacf70 rva=0xb1338
  [unwind] d=1 RIP=000000014002bd2a mod=vst3host.exe fn=0x2ae20 rva=0x2bd2a
  [unwind] d=2 RIP=0000000140001307 mod=vst3host.exe fn=0x1190  rva=0x1307
  [unwind] d=3 RIP=000000014000142a mod=vst3host.exe fn=0x1410  rva=0x142a
  [unwind] d=4 RIP=…kernel32.dll fn=0x293c0
  [unwind] d=5 RIP=…ntdll.dll fn=0x55974
  [gate] 最終 +0xdc=2 (観測ヒストグラム 2:61)
  ```
- 対応: host `0x2bd27` は `call qword ptr [rax+0x18]` (IPluginBase slot 3)、戻り番地 `0x2bd2a`。`vst3host.cpp` の `ctrl->initialize(hostApp)` (`L("controller->initialize(hostApp)…")` の直前) がこの呼出に当たると、逆アセンブルの配置と `[rcx]` vtable 読みから推定 (ソース行との厳密な対応は未照合)。
- 静的側の整合: `sr1c_callers.py 0xacf70` は thunk `0xb4ea4` (`.text`) の 1 件と vtable `0xa2bf00` の 1 件 (§1-2・§4-3 と同一)。thunk は tail jump のため unwind 上に frame を残さない。
- 含意: **+0xdc = 2 は controller initialize 中の 2 件の wrapper QI の失敗 (§3-7 / §4-4) で決まる**。既定 host の値 2 は initialize の内側で確定する。

### 6-2. 0x4894c0 の所属 (静的)

- 呼出元は `0x4890fe` の 1 件 (`sr1c_callers.py 0x4894c0`)。`0x4890fe` は関数 `0x488fc0`-`0x48912a` (size 362) 内。
- `0x488fc0` は ctor 形: 先頭で `[rcx+8]=1`、`[rcx]=vtable`。vtable `0xa85f28` の RTTI は `.?AVMenuData@@`。`0x4894c0` はこの ctor の末尾近く (`0x4890fe`) で呼ばれる。
- `0x4894c0` (size 180) は MSVC の function-local static guard (`0x1809a8ee0` / `0x1809a8f0c`) と、グローバルなポインタ列への push (`mov [rdx], rsi`; 必要時に `0x18048dd90` で拡張) からなる登録補助。どの vtable からも参照されない (非メンバ)。
- `RVA 0x48954d` は `0x4894c0` の `call 0x1809a8f0c` (shared-count 解放相当の thunk) の戻り番地。watch で拾った 1 件は stack 上の残骸であり、writer 連鎖の一部ではない (unwind で否定、6-1)。

### 6-3. 受入 3: e2e

- 実行: `bash tools/targets/serum2/host/e2e.sh`、コード commit `5cb1fa6f`、`work/` を削除してから実行。
- 結果: **62/62 OK, 67.07 s** (`time` real 1m7.070s)、NC1/NC2 とも期待どおり (exit=1, NG=1)、load (1 分値) 0.06 → 0.29、4 core、wine 9.0、逐次。
- 同じ DLL・同じ host の直前ベースライン (コード変更前の `47ee8a17`) は 62/62 OK, 80.8 s (real 1m20.798s)。所要差は同一 runner 上の揺れで、判定には使わない。
- 鮮度 (WORKFLOW §6): `git diff 5cb1fa6f HEAD -- tools/targets/serum2/host ':!tools/targets/serum2/host/REPORT_SR23.md'` は 0 バイト (本節の文書以外に差分が無いこと)。

### 6-4. 受入 4: #255 への判定 (controller 側)

- 書込元 0xacf70 は controller の initialize 内、連鎖 host main → ctrl->initialize → thunk → 0xacf70 で確定。
- gate +0xdc = 2 の由来は initialize 内の wrapper QI 2 件の失敗 (§4-4)。host が 2 IID に応答すると gate は 1 になる (§4-4 の A/B)。
- 未確定: 実 FL Studio が当該 IID に応答するか (§4 の未解決表・#1759 の静的走査は IID 未検出 = 応答の根拠は無いが、実行時の QI 応答は未観測)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FL Studio (fl-win64) の host が `IVst3ToAUWrapper` / `IVst3ToAAXWrapper` に応答するかの実行時観測 | controller gate (+0xdc) が 1 に到達する条件。`S2HOST_WRAPPER_QI` の既定化判断 | #1759 (SR-26、既存の残件) |
| 0x4894c0 (MenuData 系の登録補助) の呼出目的・グローバル配列の用途 | 本 issue の範囲外 (writer 連鎖と無関係と確認済み) | 起票せず (必要なら SR-3 の lift 時に扱う) |
| thunk `0xb4ea0` 経由の連鎖は静的 (tail jump) 確認のみ。実行時の thunk 経由の厳密な確認は unwind の範囲外 | 連鎖の厳密性 (thunk を経由することは `sr1c_callers.py` の静的結果と一致) | #256 (SR-1c) の残件に含める |
