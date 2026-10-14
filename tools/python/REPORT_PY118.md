# PY-118 (#2975): mixer.getTrackColor の既定色 (フラグ無し track) を逆アセンブルで確定し C/mock に反映

親: #2951 (PY-115)。既知類型との関係: 該当なし (lift 作業ではない。PE の静的読みと provider の実装のみ。DEFECTS.md の類型とは無関係)。

## 結論

- 既定色は `.bss` の **VA 0x15f6774 の dword = `0xff636c71`**。書込みは初期化関数 **0x770830** の中の **0x770ba6** (`mov dword ptr [rip+0xe85bc4], 0xff636c71`) だけで、同じ関数が 0x15f6774〜0x15f67b0 の 16 dword を書く。
- `mixer.getTrackColor` (wrapper **0xd5ec60**) のフラグ無し track の戻り値は **`0xff636c71`**。R/B 入替えが 2 回入るため打ち消し、`|0xff000000` だけが残る。
- main (PY-115 #2951) が getter と byte-order 版の格納式を実装済み。本 PR は既定色の定数だけを確定値に置き換える (main の仮置き `0x5A6B7C` → `0xff636c71`)。main の `REPORT_PY115.md` §2・§4・§7 の「仮置き」の記述は、この確定で古くなった。既定色の正は本 REPORT。
- C と mock の差分は 0 (`tests/mixer_diff.mjs` PASS、59 呼出し)。

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
  - 設定済み経路: core は格納値 `stored` を返し、wrapper が `swap(stored) | 0xff000000` を返す。格納値は PY-115 の式 `swap(raw) | 0xff000000` (`REPORT_PY115.md` §2)。
- **P (0x15e3858) の他の参照 (読みのみ)**: `0x111fb22`・`0x111fb3d` (関数 0x111ed10 内)、`0x12c2f75` (関数 0x12c2b80 内)、`0x12c525a` (同)。いずれも `mov e?x, [rax]` の読み出しで、P 自体・0x15f6774 への書込みは無し。

## 2. 実装 (C / mock / テスト)

- `provider/fl_engine.c`: `#define MIX_DEFAULT_COLOR 0xff636c71u` (main の `0x5A6B7Cu` を置換)。格納・取得式は main (PY-115) のまま。`setTrackColor` は `fl_swap_rb(raw) | 0xff000000` を格納して `color_set = 1`、`getTrackColor` は `color_set` が立てば格納値、立たなければ `MIX_DEFAULT_COLOR` を入替えて返す。
- `host/fl_mock.mjs`: `MIX_DEFAULT_COLOR = 0xff636c71` (定義は 1 箇所)。格納・取得式は main と同じ (`swapRb`)。
- `tests/mixer_diff.mjs`: 既定経路 (未設定 track 2) の pin を、seq の set 呼出しより前に置く (mock と wasm の両方で `0xff636c71`)。set 後に pin すると track 2 が設定済みになり既定経路を検証できないため。seq と往復 pin (`setTrackColor(1,0x123456)` → `0xff123456`) は main の版を保つ。
- `tests/provider_check.mjs`: main の版を採る。`mixer.getTrackColor` は main の `pe115` で実装済み扱いになっており、件数検査 84/351 は main と同じ。

### 解消 (main 取り込み, merge `dbfc2a4f`)

- 衝突: `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/mixer_diff.mjs`・`tests/provider_check.mjs` の 4 件。本 PR の PY-118 と main の PY-115 (#2951) が同じ色の関数を触っていた。
- 格納・取得式: main (PY-115 の byte-order 版) を採る。本 PR の raw 格納 (`setTrackColor(1,0x123456)` → `0xff563412`) は取り込みで捨てた。これで PY-115 の期待値 `0xff123456` と一致する。
- 既定色: 本 PR の `0xff636c71` を採る。main の仮置き `0x5A6B7C` (旧 mock の初期値を流用) は置き換えた。
- `provider_check.mjs`: 本 PR の `pe118` は main の `pe115` と同じ関数の重複のため外した。
- `mixer_diff.mjs`: 本 PR の末尾の重複呼出し `getTrackColor [127]` を外した (main の同じ呼出しと重複)。

## 3. 測定 (実測)

- 測定 commit (コードを最後に変えた commit): `dbfc2a4f` (`Merge remote-tracking branch 'origin/main' into 2975-mixer-default-color`)。検証起点 `origin/main` = `e87eb52a`。逆アセ (§1) の入力は `98109832` の測定から変えていない。
- 素材: `toolchain-emsdk` は本 run の `$ARTIFACTS_DIR` に無い (取得済みは `fl-win64` のみ)。上流の emsdk 6.0.12 を `$RUNNER_TEMP/emsdk` に `emsdk install 6.0.12` + `activate` で導入し、`EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh` で指定した。
- `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh bash tools/python/provider/build.sh`: rc 0、警告 0 (grep 0 件)。real 1.391 s (user 1.316 s / sys 0.244 s)、実行直前 load `0.54 0.34 0.18`。
- `node tests/mixer_diff.mjs` (commit `dbfc2a4f`): `{"calls":59,"diffs":0,"PASS":true}`。real 0.124 s (user 0.041 s / sys 0.013 s)、load `0.45 0.33 0.18`。
- `node tests/channels_diff.mjs`: `{"calls":123,"diffs":0,"PASS":true}`。real 0.052 s (user 0.049 s / sys 0.012 s)。
- `node tests/provider_check.mjs`: 件数検査 (`impl 84 / unimpl 351`) まで通過 (42 行目の top-level assert)。その後、flpy 部で `work/midi.py` が無く ENOENT で停止 (§4)。
- **ネガティブコントロール** (一時ファイルで実行し、削除済み):
  - (a) 既定色の pin を `0xff5a6b7c` に変える → `AssertionError [ERR_ASSERTION]`、rc 1。
  - (b) mock の `setTrackColor` の格納から R/B 入替えを外す → `mixer 差分 3 件`、rc 1。

### 検証範囲 / 範囲外

- 範囲内: 既定色の値・書込み箇所 (§1)、getTrackColor の既定経路と設定済み経路の読み出し式 (C と mock)、C と mock の一致 (mixer 59 呼出し・channels 123 呼出し)、build、件数検査 84/351。
- 範囲外: `provider_check.mjs` の flpy 部、`all_tools.mjs` (既定・wasm)。`dist/flpy.js` (`build_flpy.sh`) と `work/midi.py` (利用者の FL から供給・git 非管理) が本 run に無い。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 初期化関数 0x770830 の起動経路 (呼出し元 0x111d87a・0x11be297 の起動順) が未追跡 | 既定色 `0xff636c71` が起動後に必ず有効かは未確認。書込みは 0x770ba6 だけで、起動後の書換えは rip/即値/絶対参照の全走査では見つからなかった | #2951 (PY-115) |
| wrapper の範囲判定 (`[0x8834fa]-1`) と範囲外 error code を未確認 | C/mock は既存の `MX` (0..126) を流用している | #2951 (PY-115) |
| `provider_check.mjs` の flpy 部と `all_tools.mjs` (既定・wasm) が未実行 | `dist/flpy.js` と `work/midi.py` が本 run に無い。本 PR の変更は mixer 経路だけだが、flpy 経路の回帰は未検証 | PM: 素材の揃う実測 run で再実行 (子 issue は起票しない) |

## 5. 差分と検証の鮮度

- 測定 commit `dbfc2a4f` 以降に変えるのは本 REPORT だけ。`git diff dbfc2a4f HEAD -- tools/python` の期待値は `tools/python/REPORT_PY118.md` のみ (コードの差分 0)。PR 本文に実出力を添える。
