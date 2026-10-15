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
- **wrapper 0xd5ec60** (185 B): `PyArg` で index を受け、`0 ≤ index ≤ [0x8834fa]-1` (`cmp`/`jg`) を確認し、要素 `[0x8819ee] + index*0x28f*8` を `call 0x12c18f0` に渡す。戻り値に R/B 入替えと `or esi,0xff000000` をかけて Python int を返す。範囲判定の境界と範囲外の応答は §8 (#3059) で確認 (下限のみ。上限は #3553)。
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
| ~~`provider_check.mjs` の flpy 部と `all_tools.mjs` (既定・wasm) が未実行~~ | §10 で実行済み (#3804 / PY-255)。PASS | #3804 (PY-255) で解消 |

## 7. 差分と検証の鮮度

- 測定 commit `dbfc2a4f` 以降に `tools/python` で変えるのは REPORT のみ (`REPORT_PY118.md`・`REPORT_PY115.md` の文言)。`git diff dbfc2a4f HEAD -- tools/python` は REPORT の 2 ファイルだけで、コードの差分は 0。再測定は不要。

## 8. #3059 (PY-202): 実行時の既定色と wrapper 範囲判定の PE 静的解析 (追記)

受入条件 1 と 3 の下限 (idx < 0) を本節で確定した。上限 (N−1 の実行時値と 127〜501 の区間) は #3553 へ移した (§9)。受入条件 2 と 4 は子 issue に移した (§9)。
測定 commit (コードを変えた最後の commit): `32662af4d` (`test(python): mixer_diff の範囲外コメントを idx ≥ 127 の RANGE に合わせる [PY-202]`)。直前のコード変更は `359ba1159` (`fix(python): getTrackColor の idx < 0 を PE 0xd5ec60 に合わせ int 0 にし、idx ≥ 127 は RANGE のまま [PY-202]`)。

### 8.1 結論

- **wrapper 0xd5ec60 の範囲判定**: `idx < 0` (`jl`) と `idx > N-1` (`jg`) の両方が、int 0 を返す経路 `0xd5ecea` へ入る。N は qword 大域 `0x15e2198` (.data) の指す先の dword。PE 初期値は `0x14188a8` → dword `0x1f6` = **502**。N の実行時値は未確定。
- **範囲外の応答 (PE)**: `0xd5ecea`〜`0xd5ecfd` で int 0 を返す (戻り経路は確認済み)。経路の途中で警告 `call 0xd84510` を通る (初回のみ)。**PyErr を立てるかは未確認** (`0xd84510` の間接呼出し先を未読)。
- **C/mock の応答**: `idx < 0` は int 0 (PE に合わせた)。`idx ≥ 127` (NMIX) は RANGE (code 4) のまま。**PE は 127〜501 を範囲内とみるため、この区間は PE と食い違う** (未解決・§9)。上限を N−1 へ広げるのは N の実行時値が確定してから行う。N が未確定の段階で RANGE を int 0 に変えると、実在する track の色が 0 として返るおそれがあるため、上限は据え置く。
- **既定色の初期値**: 0x770830 が書く `0xff636c71` (§1)。設定ストアの root (qword `0x13fc3e8`) が PE 初期値 0 で、0x783810 の変換ゲートも 0 のため、**設定 XML が無い状態では 0x78b8e0 は既定値をそのまま返す**。よって未設定時の getTrackColor は `0xff636c71` (C/mock と一致)。ただし 0x111d7e0 の起動経路が未確定のため、起動時に有効かは未確定 (#3805)。

### 8.2 PE の根拠 (VA)

範囲判定と範囲外の行は、round 1 のレビューで `block00031_PE.bin` を再照合した。他の行は前回の記録のままで、再照合していない。

| 項目 | VA | 根拠 |
|---|---|---|
| 範囲判定 | `0xd5ec97`〜`0xd5eca9` | `mov rcx,[rip+0x8834fa]` (実効 `0x15e2198`) → `mov ecx,[rcx]` → `sub ecx,1` → `cmp rax,rcx` → `jg`。`jl` (idx<0) も同じ `0xd5ecea` へ入る |
| 範囲外 | `0xd5ecea`〜`0xd5ecfd` | `call 0xd64ca0` → `call 0xd84510` (警告・初回のみ・間接先は未確認) → esi = 0 → 変換 `call [0x88557a]` → 戻る |
| 引数解析 | `0xd5ec82` / 失敗 `0xd5ed0a` | `call [0x16b82f0]` (PyArg 相当)。失敗時のみ `0xd82c20` |
| 未発見判定 | `0x7878c0` | 戻り値 al = 発見フラグ `[rbp+0x57]` (初期 0)。`[rbp+0x88]==0` で 0 のまま返り、`*r8` は書かない |
| 設定ストア | `0x13fc3e8` (.data) | PE 上 0。書込みは `0x789530` のみ (`0x78954a`・`0x7895f6`・`0x789751`) |
| ゲート書込み | `0x788150` | 先頭ガード `0x7881cb`: `cmp [0x13fc3e8],0` で root 0 なら何も書かず戻る。呼出し元は `0x789764` (`0x789530` 内) のみ |
| ゲートの対応 | `0x78865f`・`0x788677`・`0x78868f`・`0x7886a7` | `0x15f69e0` ← "fl.tweaks.hue"、`0x15f69e4` ← "fl.tweaks.saturation"、`0x15f69ec` ← "fl.tweaks.lightness"、`0x15f69e8` ← "fl.tweaks.contrast"。値は設定の整数 (不可なら旧値) |
| 変換 | `0x783810` (`0x783820`・`0x78383f`) | root 0 のときゲートが全て 0 で恒等 |
| 0x789530 の呼出し元 | `0x111d882` (`0x111d7e0` 内) | `0x111d7e0` は PE 内に直接参照が無い (間接呼出し)。設定 XML の読込み `0x111b930` は推定 (拡張子 ".xml" の比較は UTF-16 からの推定) |
| 0x770830 の呼出し元 | `0x111d87a` (`0x111d7e0` 内)・`0x11be297` (`0x11be0a0` 内) | `0x11be0a0` ← `0x1375220` ← `0x1376545` ← export `CreateFruityInstance` (`0x1375990`) |

### 8.3 実測 (コミット済み HEAD `32662af4d`・測定 commit)

- 環境: runner。build 直前の `uptime` は `load average: 0.43, 0.49, 0.23` (04:40:25)。emsdk は素材 `toolchain-emsdk` を `tar --zstd -xf` で `$RUNNER_TEMP/emsdk-art` に展開。`fl-win64` は使わない (provider の build と mock・wasm の比較だけ)。
- 初回 build (`32662af4d`): real 10.089 s、警告 0。下表は同じ HEAD での再実行。

| コマンド | 結果 | wall |
|---|---|---|
| `EMSDK_ENV=$RUNNER_TEMP/emsdk-art/emsdk/emsdk_env.sh bash provider/build.sh` | rc 0、警告 0 (grep 0 件)。`dist/flprov.wasm` を更新 | 0.702 s (emcc のキャッシュ有り) |
| `node tests/mixer_diff.mjs` | `{"calls":69,"diffs":0,"PASS":true}` | 0.042 s |
| `node tests/channels_diff.mjs` | `{"calls":238,"diffs":0,"grid_calls":1200,"grid_true":30,"grid_diffs":0,"PASS":true}` | 0.052 s |
| `node tests/provider_check.mjs` | rc 1。`tests/provider_check.mjs:134` (flpy 部の入力 `work/midi.py`) で ENOENT。それ以前の assert は通過。前回と同じ未解決 (#3804) | — |

- **ネガティブコントロール** (HEAD で実行): mock の `getTrackColor` から `if (i < 0) return 0;` を外すと `mixer_diff` は `AssertionError` (actual `{ code: 4 }`、expected `{ ok: 0 }`)、rc 1。`git show HEAD:` で元に戻し、`cmp` で一致を確認してから `{"calls":69,"diffs":0,"PASS":true}` を再確認。
- **範囲の照合** (mock と wasm、idx −1〜502。一時 script を `$RUNNER_TEMP` に置き、リポジトリには残さない): `{"range":[-1,502],"diffs":0,"segments":{"int0":[[-1,-1]],"color":[[0,126]],"code4":[[127,502]]}}`。mock と wasm は一致。idx 127〜501 は両方 code 4 で、PE は 127〜501 を範囲内とみる (§8.1)。502 は PE では N=502 のとき範囲外 (`jg`) となり int 0 を返すが、C/mock は code 4 のまま。この食い違いは上限の未解決として §9 (#3553) に含む。
- **差分**: `git diff 32662af4d HEAD -- tools/python ':(exclude)*.md'` の出力は 0 行 (本 REPORT の commit 前の HEAD で確認)。本 REPORT の commit 後は `REPORT_PY118.md` だけになる。直前のコード変更 (`359ba1159`) からの `tools/python` の差分は `tests/mixer_diff.mjs` の注記コメント 1 行 (`32662af4d`)。挙動は変えていない。

### 8.4 変更の範囲

- `getTrackColor` の **idx < 0 のみ** RANGE → int 0 に変わる (C・mock とも)。idx 0〜126 の戻り値は変わらない。
- idx ≥ 127 (NMIX) は RANGE (code 4) のまま。前版 (`f4f3375bc`) の 127 → int 0 は撤回した (PE の 127〜501 と一致しないため)。
- 他の mixer 関数 (`MX` マクロ) は変えない。上限 127 は据え置き。

## 9. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x111d7e0 の上位呼出し元 (起動時か遅延か) | 未設定時の既定色 `0xff636c71` が実行時に有効かは未確定 | #3805 (PY-256) |
| 0x11be297 経路 (`CreateFruityInstance`) の起動時性 | 0x770830 の初期化タイミング | #3805 (PY-256) |
| ~~provider_check の flpy 部・all_tools (既定・wasm) の実行~~ | §10 で実行済み (#3804 / PY-255)。PASS | #3804 (PY-255) で解消 |
| N = 502 の実行時値 (上限 N−1)、PE の 127〜501 の区間、範囲外の PyErr 有無 (`0xd84510` の間接先) | C/mock は 127 以上を RANGE、PE は 127〜501 を範囲内とみる。実行時 N が 502 なら食い違いが残る | #3553 (PY-212) |

## 10. #3804 (PY-255): flpy 部 (provider_check.mjs) と all_tools.mjs (既定・wasm) の実行 (実測)

§5・§6 で未実行だった 2 本を実行した。コードは変えていない (測定 commit `425347571` = `origin/main`)。

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)、`toolchain-emsdk` を `$RUNNER_TEMP/emsdk-art` に `tar --zstd -xf` で展開。入力は `bash tools/python/fetch_inputs.sh` で配置 (win64 の DATA block から `midi.py`・`utils.py`・`MCPTools.pyc`・device script・fl-stubs)。
- 手順 (順に実行、いずれも foreground、rc は実測):
  1. `bash tools/python/build_cpython_wasm.sh`: rc 0。real 4 分 9.9 秒 (user 7 分 51 秒)。`libpython3.12.a`・`python.js`・`python.wasm`・`python.data` を生成。
  2. `EMSDK_ENV=<emsdk>/emsdk_env.sh FL_WIN_PE=<fl-win64>/extracted/block00031_PE.bin bash tools/python/build_flpy.sh`: rc 0。real 24.6 秒 (user 53.3 秒)。`dist/flpy.{js,wasm,data}` を生成。
  3. `node tests/all_tools.mjs` (既定・wasm): **PASS**。出力 `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}`。real 2.081 秒 (user 2.720 秒)、load `2.78 1.85 0.88` (17:43:25)。
  4. `EMSDK_ENV=<emsdk>/emsdk_env.sh bash tools/python/provider/build.sh` (`dist/flprov.{js,wasm}` を作る): rc 0。real 1.537 秒。`fl_table.c`: 435 関数、ハンドラ 228。
  5. `node tests/provider_check.mjs`: **PASS**。出力 `{"functions":435,"implemented":228,"unimplemented":207,"mcp_static":60,"PASS":true}`。real 0.373 秒 (user 0.755 秒)、load `2.43 1.80 0.88` (17:43:35)。flpy 部 (`work/midi.py` を使う CPython 側の検査) まで通過。
- 件数について: §4・§8.3 の `impl 84 / unimpl 351` は過去の木の値。現行の `provider_check.mjs` は件数を期待集合 (`provider_expect/*.json`) から導出するため、現行値 `228 / 207` が正。件数の assert はスクリプト内で PASS。
- 失敗: 0 件。手順 4 の前に `provider_check.mjs` を実行した際は `dist/flprov.js` が無く ERR_MODULE_NOT_FOUND で止まった (前提の不足。手順 4 の後で PASS)。C/mock の差分ではない。
- 素材: `toolchain-emsdk` は本 run の `$ARTIFACTS_DIR` にあった (§4 の記述は過去 run のもの)。

結論: §5 の未実行は解消。flpy 経路 (`dist/flpy.js`) の回帰は、本測定の範囲では無し。
