# PY-118 (#2975): mixer.getTrackColor の既定色 (フラグ無し track) を逆アセンブルで確定し C/mock に反映

親: #2951 (PY-115)。既知類型との関係: 該当なし (lift 作業ではない。PE の静的読みと provider の実装のみ。DEFECTS.md の類型とは無関係)。

## 結論

- 既定色は `.bss` の **VA 0x15f6774 の dword = `0xff636c71`**。書込みは初期化関数 **0x770830** の中の **0x770ba6** (`mov dword ptr [rip+0xe85bc4], 0xff636c71`) だけで、同じ関数が 0x15f6774〜0x15f67b0 の 16 dword を書く。
- `mixer.getTrackColor` (wrapper **0xd5ec60**) のフラグ無し track の戻り値は **`0xff636c71`**。R/B 入替えが 2 回入るため打ち消し、`|0xff000000` だけが残る。
- issue の前提と違い、C (`provider/fl_engine.c`) にも mock (`host/fl_mock.mjs`) にも `mixer.getTrackColor` は main に無かった (`MIX_DEFAULT_COLOR` の名前も無く、旧仮置き `0x5A6B7C` は mixer track の初期化だけ)。本 PY-118 で getter を新設し、既定色を `MIX_DEFAULT_COLOR` に置いた。
- C と mock の差分は 0 (`tests/mixer_diff.mjs` PASS)。

## 1. 逆アセンブル (VA)

- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B。ImageBase `0x400000`)。`.data` = `0x13a5000`、`.bss` = `0x15e6000` (VirtualSize `0x388e9c`、file 実体 0)。
- 走査: `.pdata` の関数範囲 57,816 件・2,566,540 命令を capstone で逆アセ (`.text` 先頭は命令でなく線形走査は使えない)。real 36.7 s (user 36.4 s)、実行直前 load `0.14 0.33 0.23`。
- **ポインタ**: `.data` の `0x15e3858` が dword `0x15f6774` を持つ (`.data` 全走査で唯一の一致)。
- **書込み**: `0x15f6774`〜`0x15f6814` を rip 相対・即値・絶対の各参照で全走査し 21 件。書込み 16 件はすべて関数 **0x770830**–0x770f1a (`.pdata`) の内側で、先頭が 0x770ba6 (`0x15f6774` ← `0xff636c71`)、末尾が 0x770c46 (`0x15f67b0` ← `0xffff5587`)。読み出し 5 件は次の節。
- 初期化関数の呼出し元: `E8`/`E9` の rel32 で 0x770830 を指すのは **2 箇所 (0x111d87a・0x11be297)**。どの起動経路から呼ばれるかは未追跡 (§4)。
- **取得核 0x12c18f0** (45 B): `cmp byte ptr [rcx],0` (フラグ = 要素 +0)。
  - `je 0x12c18fa` (フラグ 0): `rax = [0x15e3858]`、`eax = dword [rax]` (= 0x15f6774)、R/B 入替え (`and 0xff00ff` / `and 0xff00ff00` / `shl 16` / `shr 16`)。
  - フラグ ≠ 0: `eax = dword [rcx+4]` (格納値をそのまま返す)。
- **wrapper 0xd5ec60** (185 B): `PyArg` で index を `[rbp+0x2c]` に受け、`0 ≤ index ≤ [0x8834fa]-1` (`cmp`/`jg`) を確認し、要素 `[0x8819ee] + index*0x28f*8` を `call 0x12c18f0` に渡す。その後 R/B 入替えと `or esi,0xff000000` の後、Python int を返す。
  - 既定経路: core は `swap(D)`、wrapper が再び `swap` して `D`、続けて `|0xff000000`。`D = 0xff636c71` は alpha を持つので `0xff636c71`。
  - 設定済み経路: core は格納値 `raw` を返し、wrapper が `swap(raw) | 0xff000000` を返す。
- **P (0x15e3858) の他の参照 (読みのみ)**: `0x111fb22`・`0x111fb3d` (関数 0x111ed10 内)、`0x12c2f75` (関数 0x12c2b80 内)、`0x12c525a` (同)。いずれも `mov e?x, [rax]` の読み出しで、P 自体・0x15f6774 への書込みは無し。

## 2. 実装 (C / mock / テスト)

- `provider/fl_engine.c`: `#define MIX_DEFAULT_COLOR 0xff636c71`。`Mix` に `color_set` (要素 +0 のフラグに相当) を追加。mixer 初期化は `color = MIX_DEFAULT_COLOR`。`setTrackColor` は `color_set = 1` を立てるだけで格納式は変えない (raw 格納のまま)。`getTrackColor` は `(color_set ? swap_rb(color) : color) | 0xff000000`。
- `host/fl_mock.mjs`: 同じ式。`colorSet` フラグ。`MIX_DEFAULT_COLOR` は mixer track の初期値に使う。channels の `0x5A6B7C` は変えていない (channel 色は本 issue の対象外)。
- `tests/mixer_diff.mjs`: getTrackColor を未設定 track 0・2、設定後 track 1、範囲外 127 で呼ぶ。末尾で未設定 track 2 が `0xff636c71` であることを mock と wasm の両方で pin。
- `tests/provider_check.mjs`: `mixer.getTrackColor` を実装済み扱い (`pe118`) にし、件数検査を 83/352 → 84/351 に更新。

## 3. 測定 (実測)

- 測定 commit (コードを最後に変えた commit): `98109832` (`feat(python): [PY-118] ...`)。検証起点 `origin/main` = `9286a6bb`。
- 素材: `fl-win64` は `block00031_PE.bin` と `block24429/24430/25159/24618_DATA.bin` を展開 (`$RUNNER_TEMP/fl-win64`)。`toolchain-emsdk` は `$RUNNER_TEMP/emsdk` に展開し `EMSDK_ENV` で指定。
- `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh bash tools/python/provider/build.sh`: rc 0、警告 0 (commit `98109832` の HEAD で実測)。warm 再実行は real 0.894 s (user 0.844 s / sys 0.195 s)、load `0.16 0.28 0.23`。初回は system library の生成を含み real 15.176 s (user 30.785 s / sys 15.003 s、実行直前 load `0.14 0.33 0.23`)。
- `node tests/mixer_diff.mjs` (commit `98109832` の HEAD): `{"calls":53,"diffs":0,"PASS":true}`。real 0.045 s (user 0.041 s / sys 0.012 s)、load `0.14 0.27 0.23`。
- `node tests/channels_diff.mjs`: `{"calls":123,"diffs":0,"PASS":true}`。real 0.051 s (user 0.046 s / sys 0.014 s)。
- `node tests/provider_check.mjs`: 件数検査 (`impl 84 / unimpl 351`) まで通過。その後 `dist/flpy.js` が無いため停止 (§4)。
- **ネガティブコントロール** (一時ファイルで実行し、削除済み):
  - (a) 既定色の pin を `0xff5a6b7c` に変える → `AssertionError [ERR_ASSERTION]` (strict deepEqual)。
  - (b) mock の設定済み経路から R/B 入替えを外す → `mixer 差分 1 件` で FAIL。

### 検証範囲 / 範囲外

- 範囲内: 既定色の値・書込み箇所・getTrackColor の既定経路と設定済み経路の読み出し式 (core + wrapper の合成)、C と mock の一致、build。
- 範囲外: `dist/flpy.js` を要する `provider_check.mjs` の後半、`all_tools.mjs` (既定・wasm)。`build_cpython_wasm.sh` が必要で、本 run の時間内に収まらなかった。
- `git diff 98109832 HEAD -- tools/python` の出力: 本 REPORT の追加だけ (§5 の commit 後に確認する)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `setTrackColor` の格納式 (`0x12c17a0`、PY-115 の範囲) が未確定。C/mock は raw を格納する | 設定済み track の `getTrackColor` は `swap(raw)\|0xff000000` の読出しになる。`setTrackColor(1,0x123456)` → `0xff563412`。#2951 の期待 `0xff123456` とは一致しない | #2951 (PY-115) |
| 初期化関数 0x770830 の起動経路 (呼出し元 0x111d87a・0x11be297 の起動順) が未追跡 | 既定色 `0xff636c71` が起動後に必ず有効かは未確認。書込みは 0x770ba6 だけで、起動後の書換えは rip/即値/絶対参照の全走査では見つからなかった | #2951 (PY-115) |
| wrapper の範囲判定 (`[0x8834fa]-1`) と範囲外 error code を未確認 | C/mock は既存の `MX` (0..126) を流用している | #2951 (PY-115) |
| `provider_check.mjs` の flpy 部、`all_tools.mjs` (既定・wasm) を未実行 | `dist/flpy.js` (`build_cpython_wasm.sh`) が無い。本 PR の変更は mixer 経路だけだが、flpy 経路の回帰は未検証 | PM: 次の実測 run で再実行 (子 issue は起票しない) |
| 親 #2951 が参照する `REPORT_PY113.md`・`REPORT_PY115.md` が main に無い | §4・§7 の根拠を追えない。PY-115 の WIP は `origin/2950-flapi-extra-args` (`3e754b8b`) にあり未 merge | #2951 (参照先の補完) |

## 5. 差分と検証の鮮度

- 本 REPORT の commit 後に `git diff 98109832 HEAD -- tools/python` を確認する (期待: `REPORT_PY118.md` の追加のみ)。
