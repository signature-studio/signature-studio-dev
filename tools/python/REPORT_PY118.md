# PY-118 (#2975): mixer.getTrackColor の既定色 (フラグ無し track) の初期値を逆アセンブルで確定し C/mock に反映

親: #2951 (PY-115)。実行時値の残り: #3059 (PY-157)。既知類型との関係: 該当なし (lift 作業ではない。PE の静的読みと provider の実装のみ。DEFECTS.md の類型とは無関係)。

## 結論

- 既定色の **初期値** は `.bss` の **VA 0x15f6774 の dword = `0xff636c71`**。書込みは初期化関数 **0x770830** の **0x770ba6** (`mov dword ptr [rip+0xe85bc4], 0xff636c71`)。
- **実行時の既定色は初期値のままとは限らない。** 0x770830 の直後 (0x111d88e) に呼ばれる **0x111ed10** が **0x111fb44** で同じセルを、設定読込 (0x78b8e0) の戻り値で書き換える。これは rip 相対・即値・絶対の走査では見えない間接書込みである。設定ストアの未発見判定と変換ゲートは未確定 (#3059)。
- `mixer.getTrackColor` (wrapper **0xd5ec60**) のフラグ無し track は、セルの値をそのまま返す (R/B 入替えが 2 回入って打ち消し、`|0xff000000` だけが残る)。セルが初期値 `0xff636c71` のとき戻り値は `0xff636c71`。
- C と mock の `MIX_DEFAULT_COLOR` は初期値 `0xff636c71` に置き換えた (main の仮置き `0x5A6B7C` を置換)。C と mock の差分は 0 (`tests/mixer_diff.mjs` PASS、59 呼出し)。

## 1. 逆アセンブル (VA)

- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B。ImageBase `0x400000`)。`.data` = `0x13a5000`、`.bss` = `0x15e6000` (VirtualSize `0x388e9c`、file 実体 0)。
- 走査: `.pdata` の関数 57,816 件を capstone で逆アセ。窓の全走査は real 9.0 s (user 9.0 s)。
- **ポインタ**: `.data` の `0x15e3858` が dword `0x15f6774` を持つ (`.data` 全走査で唯一の一致)。`0x15e3858` の参照は 5 件で、全て読み出し (`0x111fb22`・`0x111fb3d`・`0x12c18fa`・`0x12c2f75`・`0x12c525a`)。P への書込みは無い。
- **初期化の書込み (0x770830)**: 窓 `[0x15f6774, 0x15f6814]` を rip 相対・即値・絶対の各参照で全走査 → 42 件。書込み 41 件・読み出し 1 件 (`0x770ac1`)。全件が関数 0x770830–0x770f1a の内側。内訳は `[0x15f6774, 0x15f67b0]` に書込み 16 件 (先頭 0x770ba6 ← `0xff636c71`)、`[0x15f67b4, 0x15f67fc]` に 19 件、`[0x15f6800, 0x15f6814]` に 6 件 (末尾 0x770d5f ← `0xffbaf453`)。
- 初期化関数の呼出し元: E8/E9 で 0x770830 を指すのは **2 箇所 (0x111d87a・0x11be297)**。どの起動経路から呼ばれるかは未追跡 (#3059)。

### 1b. 実行時の書込み (0x111ed10 経由・間接書込み)

- `0x111d7e0` は `0x111d87a` で `0x770830` を呼んだ直後、`0x111d88e` で `0x111ed10` を呼ぶ。
- `0x111ed10` 内 (`0x111fb19`〜`0x111fb44`):
  - `0x111fb22`: `rax = [0x15e3858]` (= `0x15f6774`)、`0x111fb29`: `ecx = dword [rax]` (セルの現在値 = 初期値)。
  - `0x111fb2b`: `rdx` = UTF-16 キー `0x1122a34` (`forms.mixer.track.header.background`)、`r8d = 0xf`、`0x111fb38`: `call 0x78b8e0`。
  - `0x111fb3d`: `rcx = [0x15e3858]` (= `0x15f6774`)、`0x111fb44`: **`mov dword ptr [rcx], eax`** (戻り値を書く)。
- `0x78b8e0` (約 50 命令): `v = ecx` (既定値)。`0x7878c0` で設定ストアを引く。未発見なら `v` は既定値のまま、発見なら格納値。次に `0x783810(v, r8d)` で変換する (flags `0xf` は `0x20` を含まないため、発見・未発見のどちらでも変換まで進む)。戻り値は `(変換後 & 0xffffff) | (既定値 & 0xff000000)`。alpha は既定値から保つ。
- `0x783810(c, 0xf)`: 変換は次のゲートで決まる。`0x13fc3f0` (byte) が非 0 なら恒等。0 なら `0xf` の各ビットに対応するゲートを見る (bit 8 → `0x15f69e0`、bit 2 → `0x15f69e4`、bit 1 → `0x15f69e8`、bit 4 → `0x15f69ec`)。ゲートが全て 0 なら `c` をそのまま返す。PE の初期値は全て 0 (`0x13fc3f0` は `.data`、`0x15f69e0`〜`0x15f69ec` は `.bss`)。
- `0x788150` が `0x15f69e0`・`0x15f69e4`・`0x15f69e8`・`0x15f69ec` を書く (`.text` 全走査で 4 箇所。`0x78865f`・`0x788677`・`0x78868f`・`0x7886a7`)。呼出し元と起動時の値は未追跡 (#3059)。
- **確定できた範囲**: PE の初期状態で、設定ストアがキーを持たず、ゲートが 0 のままなら `0x78b8e0` は既定値 `0xff636c71` を返す。
- **確定できていない範囲**: (a) `0x7878c0` の未発見判定と設定ストアの中身、(b) `0x788150` によるゲート値。どちらかが違えば、実行時のセルは `0xff636c71` と異なる (#3059)。

## 2. 取得核と wrapper

- **取得核 0x12c18f0** (45 B): `cmp byte ptr [rcx],0` (フラグ = 要素 +0)。
  - `je 0x12c18fa` (フラグ 0): `rax = [0x15e3858]`、`eax = dword [rax]` (= 0x15f6774 のセル値)、R/B 入替え (`and 0xff00ff` / `and 0xff00ff00` / `shl 16` / `shr 16`)。
  - フラグ ≠ 0: `eax = dword [rcx+4]` (格納値をそのまま返す)。
- **wrapper 0xd5ec60** (185 B): `PyArg` で index を受け、`0 ≤ index ≤ [0x8834fa]-1` (`cmp`/`jg`) を確認し、要素 `[0x8819ee] + index*0x28f*8` を `call 0x12c18f0` に渡す。戻り値に R/B 入替えと `or esi,0xff000000` をかけて Python int を返す。範囲判定の境界と範囲外 error code は未確認 (#3059)。
  - 既定経路: 核は `swap(D)`、wrapper が再び `swap` して `D`、続けて `|0xff000000`。`D = 0xff636c71` なら戻り値 `0xff636c71`。
  - 設定済み経路: 核は格納値 `stored` を返し、wrapper が `swap(stored) | 0xff000000` を返す。格納値は PY-115 の式 `swap(raw) | 0xff000000` (`REPORT_PY115.md` §2)。

## 3. 実装 (C / mock / テスト)

- `provider/fl_engine.c`: `#define MIX_DEFAULT_COLOR 0xff636c71u` (main の `0x5A6B7Cu` を置換)。格納・取得式は main (PY-115) のまま。`setTrackColor` は `fl_swap_rb(raw) | 0xff000000` を格納して `color_set = 1`、`getTrackColor` は `color_set` が立てば格納値、立たなければ `MIX_DEFAULT_COLOR` を入替えて返す。
- `host/fl_mock.mjs`: `MIX_DEFAULT_COLOR = 0xff636c71` (定義は 1 箇所)。格納・取得式は main と同じ (`swapRb`)。
- `tests/mixer_diff.mjs`: 既定経路 (未設定 track 2) の pin を、seq の set 呼出しより前に置く (mock と wasm の両方で `0xff636c71`)。set 後に pin すると track 2 が設定済みになり既定経路を検証できないため。seq と往復 pin (`setTrackColor(1,0x123456)` → `0xff123456`) は main の版を保つ。
- `tests/provider_check.mjs`: main の版を採る。`mixer.getTrackColor` は main の `pe115` で実装済み扱いになっており、件数検査 84/351 は main と同じ。

### 解消 (main 取り込み, merge `dbfc2a4f`)

- 衝突: `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/mixer_diff.mjs`・`tests/provider_check.mjs` の 4 件。本 PR の PY-118 と main の PY-115 (#2951) が同じ色の関数を触っていた。
- 格納・取得式: main (PY-115 の byte-order 版) を採る。本 PR の raw 格納は取り込みで捨てた。これで PY-115 の期待値 `0xff123456` と一致する。
- 既定色: 本 PR の `0xff636c71` を採る。main の仮置き `0x5A6B7C` (旧 mock の初期値を流用) は置き換えた。
- `provider_check.mjs`: 本 PR の `pe118` は main の `pe115` と同じ関数の重複のため外した。
- `mixer_diff.mjs`: 本 PR の末尾の重複呼出し `getTrackColor [127]` を外した (main の同じ呼出しと重複)。

## 4. 測定 (実測)

- 測定 commit (コードを最後に変えた commit): `dbfc2a4f` (`Merge remote-tracking branch 'origin/main' into 2975-mixer-default-color`)。検証起点 `origin/main` = `e87eb52a`。コードは測定後に変えていない (以後の変更は本 REPORT と `REPORT_PY115.md` の文言のみ)。
- 素材: `toolchain-emsdk` は本 run の `$ARTIFACTS_DIR` に無い (取得済みは `fl-win64` のみ)。上流の emsdk 6.0.12 を `$RUNNER_TEMP/emsdk` に入れて `EMSDK_ENV` で指定した。
- `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh bash tools/python/provider/build.sh`: rc 0、警告 0 (grep 0 件)。real 1.391 s (user 1.316 s / sys 0.244 s)、実行直前 load `0.54 0.34 0.18`。
- `node tests/mixer_diff.mjs` (commit `dbfc2a4f`): `{"calls":59,"diffs":0,"PASS":true}`。real 0.124 s (user 0.041 s / sys 0.013 s)、load `0.45 0.33 0.18`。
- `node tests/channels_diff.mjs`: `{"calls":123,"diffs":0,"PASS":true}`。real 0.052 s (user 0.049 s / sys 0.012 s)。
- `node tests/provider_check.mjs`: 件数検査 (`impl 84 / unimpl 351`) まで通過 (42 行目の top-level assert)。その後、flpy 部で `work/midi.py` が無く ENOENT で停止 (§6)。
- **ネガティブコントロール** (一時ファイルで実行し、削除済み):
  - (a) 既定色の pin を `0xff5a6b7c` に変える → `AssertionError [ERR_ASSERTION]`、rc 1。
  - (b) mock の `setTrackColor` の格納から R/B 入替えを外す → `mixer 差分 3 件`、rc 1。

## 5. 検証範囲 / 範囲外

- 範囲内: 初期値の位置と値 (§1)、間接書込みの経路 (§1b、0x111ed10 → 0x78b8e0 → 0x783810)、getTrackColor の既定経路と設定済み経路の読み出し式 (C と mock)、C と mock の一致 (mixer 59 呼出し・channels 123 呼出し)、build、件数検査 84/351。
- 範囲外: 実行時のセル値 (§1b の未確定 (a)(b))、起動経路 (0x770830 の呼出し元)、wrapper の範囲判定、`provider_check.mjs` の flpy 部、`all_tools.mjs` (既定・wasm)。`dist/flpy.js` (`build_flpy.sh`) と `work/midi.py` (利用者の FL から供給・git 非管理) が本 run に無い。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x111ed10 の設定読込: 0x7878c0 の未発見判定と設定ストアの中身 (§1b) | 実行時の既定色が初期値 `0xff636c71` のままかは未確定 | #3059 (PY-157) |
| 0x788150 の呼出し元と起動時のゲート値 `0x15f69e0`〜`0x15f69ec` (§1b) | `0x783810` の変換が恒等かは未確定 | #3059 (PY-157) |
| 初期化 0x770830 の起動経路 (呼出し元 0x111d87a・0x11be297) | 初期値が起動時に有効かは未確定 | #3059 (PY-157) |
| wrapper の範囲判定 `[0x8834fa]-1` と範囲外 error code | C/mock は既存の `MX` (0..126) を流用している | #3059 (PY-157) |
| `provider_check.mjs` の flpy 部と `all_tools.mjs` (既定・wasm) が未実行 | `dist/flpy.js` と `work/midi.py` が本 run に無い。本 PR の変更は mixer 経路だけだが、flpy 経路の回帰は未検証 | #3059 (PY-157) |

## 7. 差分と検証の鮮度

- 測定 commit `dbfc2a4f` 以降に `tools/python` で変えるのは REPORT のみ (`REPORT_PY118.md`・`REPORT_PY115.md` の文言)。`git diff dbfc2a4f HEAD -- tools/python` は REPORT の 2 ファイルだけで、コードの差分は 0。再測定は不要。
