# PY-38 (#1525): channels の 4 関数の実機意味論 (rerollLoopStarter{Loop,Sample,Steps} / setSwing)

親: #1515 (PY-37 / #1343 の残り)。既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブル読解のみ)。

## 結論

- 4 関数 (と getSwing) の PE 上の位置・引数書式・index -1 の扱い・値の変換式を、PE 解析箇所つきで確定した。
- 未確定: 汎用 helper `0x1046a30` の中身と、status 値の完全な写像。実装 (`provider/fl_engine.c`・mock・差分検査) は本 run では未実施。残りは子 issue **[PY-41]** に分割する (下記)。
- コード差分 0 (`provider/` `host/` `tests/` は未変更)。よって `provider_check.mjs` と `all_tools.mjs` は再測定していない (PY-32 と同じ扱い)。

## 測定条件

- 素材: `oc_artifacts: fl-win64` の `flstudio_win64_26.1.7.5653.exe` 展開物のうち `extracted/block00031_PE.bin` (`analysis/flapi/raw_win64.json` と同じ PE)。
- 解析: capstone 5.0.7 で逆アセンブル (`analysis/flapi_kwargs.py` の `Image` クラスを流用)。メソッド表 VA `0x15171c8`。

## 関数表

| 関数 | fn VA | flags | 引数書式 (kwlist) |
|---|---|---|---|
| rerollLoopStarterLoop | 0xd5dab0 | 3 | `i\|i` (index, useGlobalIndex) |
| rerollLoopStarterSteps | 0xd5d810 | 3 | `i\|i` (index, useGlobalIndex) |
| rerollLoopStarterSample | 0xd5d490 | 3 | `i\|i` (index, useGlobalIndex) |
| setSwing | 0xd5dcd0 | 1 | `f` (位置引数のみ) |
| getSwing | 0xd5dbf0 | 4 | 引数なし |

## 共通経路 (4 関数とも同じ形)

1. `PyArg_ParseTupleAndKeywords` で引数を解析する。reroll 系は `useGlobalIndex` を `mov dword [rbp+0x98],0` で 0 にしてから解析するため、省略時の既定は 0。
2. 解析に成功したら dispatch `0xd843d0` を呼ぶ。第 3 引数 (r8) は各 callback: loopCb=`0xd5d950`・stepsCb=`0xd5d610`・sampleCb=`0xd5d330`・swingCb=`0xd5dc30`。
3. dispatch は deferred job を作って callback を登録する。callback が返す status (rax) は `finish` (`0xd82c20`) が Python 例外へ写す。
4. 成功時の戻り値は `finish` の結果。エラー文字列は `finish` に 10 件あり、`eax == -4` の分岐 (`0xd82d3c`) が `Index out of range` を出すことを確認した。

## setSwing(value: float) -> None [swingCb 0xd5dc30]

- 入力 `v` を [0.0, 1.0] に clamp する。下限 0.0 (`movss xmm1,[rip+0x4a]` → `ucomiss`)、上限 1.0 (`ucomiss xmm0,[rip+0x38]`)。範囲外はエラーにせず clamp する。
- `mulss` で 128.0 を掛け、`cvtss2sd` の後 `0x40c750` (= `cvttsd2si`) で整数に切り捨てる。
- `0x1046a30(ecx=0x40000001, edx=<値>, r8d=0x3dd)` で書き込む。
- 戻り値: 通常の None 系 (`finish`)。

## getSwing() -> float [0xd5dbf0]

- `0x1046a30(ecx=0x40000001, edx=0, r8d=2)` で読み出し、`cvtsi2sd` して 128.0 で割る (`divsd` の定数 128.0 を確認)。
- 戻りは間接 call `[rax]` で float を返す。

## rerollLoopStarterLoop(index, useGlobalIndex=0) -> None [loopCb 0xd5d950]

- `index == -1`: 全チャンネルを走査する (件数 = グローバル配列の `[+0x10]`)。`chan[+0x79c] != 0` の要素について、対応する別 object の `[+0x739] = 1` をセットする。走査後 `0xdbde10` を呼ぶ。
- `index != -1`: `0x1005730` で index を解決する (`useGlobalIndex` で global / local の配列を切り替え)。
  - 解決失敗 → status `-4` (`Index out of range`)。
  - `chan[+0x79c] == 0` → status `-4`。
  - 成功 → `chan[+0x739] = 1`、`0xdbdd50(edx = chan[+0x794])` で反映。plugin `[+0x7d4]` の `[+0xa9]` が立っていれば `0x73cf60`。

## rerollLoopStarterSteps(index, useGlobalIndex=0) -> None [stepsCb 0xd5d610]

- `index == -1`: 全件走査し、`0xffa6d0` の戻り値が 2 の chan を配列 (スタック上の動的配列) に積む。走査後 `0xdbe1f0` に渡す。
- `index != -1`: `0x1005730` で解決。失敗 → `-4`。

## rerollLoopStarterSample(index, useGlobalIndex=0) -> None [sampleCb 0xd5d330]

- `index == -1`: 全件走査し、`0xffa6d0 == 2` の chan に `[+0x739] = 1` をセット。走査後 `0xdbde10`。
- `index != -1`: 解決失敗 → `-4`。成功 → `[+0x739] = 1`、`0xdbdd50(edx = chan[+0x794])`、plugin `[+0x7d4]` の `[+0xa9]` 判定で `0x73cf60`。

## 未確定 (実装前に要確認)

- `0x1046a30` の中身 (汎用の get/set helper。`0x40000001`・`0x3dd`・`2` が何を指すか)。
- `chan[+0x79c]`・`chan[+0x739]`・`chan[+0x794]` と `0xffa6d0` の戻り値 2 の意味 (名前と役割は未確定)。
- status 値の完全な写像。`finish` の文字列 (`OK`・`Unspecified error`・`Operation unsafe at current time`・`Range error`・`Index out of range`・`Wrong number of function parameters or wrong parameter type`・`Linked device not assigned`・`Device not assigned`・`Plugin not valid`・`Unknown error`) のどれが -1〜-10 のどれに対応するかは未対応付け。
- reroll 系の成功時戻り値 (None 系 = `finish` の `OK` 経路かどうか)。

## 受入条件の判定 (#1525)

- [ ] 4 関数の引数・戻り値・範囲外 code を PE 解析箇所つきで REPORT に残す — **部分達成**。引数書式・index -1 の扱い・setSwing/getSwing の変換式・範囲外 (-4) は確定。`0x1046a30` と status 完全写像は未確定。
- [ ] `provider/fl_engine.c` に実装し `provider_check.mjs` の実装数を更新 — 未達 → **[PY-41]**。
- [ ] mock と C の差分検査で diffs 0 — 未達 → **[PY-41]**。
- [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok — 未再測定 (コード差分 0)。

## 分割先

- 残り (実装・mock・差分検査・`0x1046a30` と status 写像の確定) → [PY-41] (親: #1525)。
