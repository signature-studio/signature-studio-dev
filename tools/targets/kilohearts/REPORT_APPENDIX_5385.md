# REPORT 付録 (#5385 KH-159): Delay の stereo ABI 族後半 callee の呼出し 4 件を機械語で確定し規則化

親 #4880 (KH-126) の分割 2。本 issue は後半 3 callee (呼出し 6 件) を扱う。前半 3 callee は #5384 (`REPORT_APPENDIX_5384.md` §10-7z)。

#### 10-7aa. #5385 (KH-159): `FUN_180fdc700`・`FUN_180fdc6d8` の呼出し 4 件を規則化 (`FUN_180fcd400` の 2 件は未確定)

- **結論**: 呼出し 6 件のうち **4 件を規則化** (`FUN_180fdc700` 2 件・`FUN_180fdc6d8` 2 件)。残り 2 件 (`FUN_180fcd400` ← `FUN_180fcce40`) は機械語の源が未確定のため規則にしない。受入 1 (6 件の源の確定) と受入 2 (規則 1 件 = 呼出し 1 件) は **部分達成**。
- **再測定 (本 fix run・同一条件・n=1)**: 測定 commit は 2 点。`origin/main` `a0b804faf` (規則なし) と head (`ghidra_route` は `e0aff674f` と同一・`git diff e0aff674f HEAD -- tools/targets/kilohearts/ghidra_route` は 0 行)。両方とも素材 `plugins-kilohearts` の `HeartCore.core_64` (sha256 先頭 `d55ce8b4`)・Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致)・emcc 6.0.12 (emsdk 上流 `6.0.12`)・FX `bitcast,intload,stackpair,assoc,concat`・閉包 `closure.py delay` (139 関数・反復 1・FAIL 0 を両方で確認)。
  - 判定: `ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat` は両方とも rc 0 で通過 (head で `ABI rule hit 1` の 4 規則の assert が通ったことを示す)。

| 測定 commit | emcc `-c -ferror-limit=0` error 総数 | 引数数不一致 | 128bit レーン型 | 演算・代入・ポインタ型不一致 |
|---|---|---|---|---|
| `origin/main` `a0b804faf` (規則なし) | 399 | 69 | 166 | 164 |
| head (`e0aff674f` と同一の `ghidra_route`) | 395 | 65 | 166 | 164 |
| 差 (head − main) | **−4** | **−4** | 0 | 0 |

  - 差は引数数不一致の −4 のみ。生成 C の差分は 4 行 (4232・4295・4512・4545 の `FUN_180fdc700()`・`FUN_180fdc6d8()` に `d2u(param_1)` を追加)。`diff` で確認した。
  - `git diff a0b804faf HEAD -- tools/targets/kilohearts/ghidra_route` は `patches.py` の 9 行追加 (規則 4 件と、そのコメント)。
  - 件数 assert: 規則 4 件はいずれも `ABI rule hit 1` を満たした (head の `ghidra_to_c.py` が rc 0)。
  - 前 run の 343 / 69 (採用しない値) は今回の測定対象外で、撤回のまま。
  - 素材の注記: 素材は `plugins-kilohearts` (`HeartCore.core_64`) と `toolchain-emsdk` (`[EMSDK]`) を使った。emsdk の版 6.0.12 の emcc で測定した。Ghidra 12.1.4 は公式 zip を取得し sha256 を検査して使った。
- **機械語の源 (capstone 逆アセンブル)**:

| 呼出元 (C 行 → 機械語の call) | 呼出先 | 引数の源 (呼出し直前の xmm0) | 根拠 |
|---|---|---|---|
| 4232 → `180fcd9e5` (`FUN_180fcd690` 内) | `FUN_180fdc700` | 入口 `param_1` | `180fcd9e5 call` の直前は `movq xmm0,rdx` (`rdx` = 入口 xmm0 の bit、`180fcd6a1` で保持) |
| 4295 → `180fcdbf0` (`FUN_180fcd690` 内) | `FUN_180fdc700` | 入口 `param_1` | `180fcdab7 jae 180fcdbf0` は `180fcdabd vmovq xmm0,r9` より前に分岐。`180fcd9f0` (flag≠0) 経路で xmm0 は入口のまま |
| 4512 → `180fce455` (`FUN_180fce0d0` 内) | `FUN_180fdc6d8` | 入口 `param_1` | `180fce450 movq xmm0,rdx` (`rdx` = 入口 xmm0、`180fce0e1` で保持) |
| 4545 → `180fce640` (`FUN_180fce0d0` 内・flag≠0) | `FUN_180fdc6d8` | 入口 `param_1` | `180fce460 vmovq r9,xmm0` (読むだけ)・`180fce515`〜 で xmm0 を書かない経路 |

- **未規則化 2 件 (`FUN_180fcd400` ← `FUN_180fcce40`)**:
  - 4048 (`180fccee6`): 直前の xmm0 は入口 `param_1` (`movq rdx,xmm0`・`movaps xmm6,xmm0` で保持)。ただし `FUN_180fcd400` は `double` 2 個 + `int` 1 個を取り、`180fccee0` で xmm1 = 0.0・r8 = 0 を設定する。C 側の 2 個目・3 個目の引数の書き方 (4048 では未指定) を機械語と合わせる作業が残るため、本件では規則にしない。
  - 4060 (`180fcd074`): 直前の xmm0 は reduction 後の値 (`180fcd042`〜`180fcd069` の `subsd` 群の結果。`movaps xmm1,xmm6` で xmm1 も設定)。C 4060 の `param_1 = FUN_180fcd400()` に対応する式が未確定。`FUN_180fcd040` 相当の C 本体は生成 C に無く、同じ経路の対応を確定できなかった。
- **規則の正規表現**: 生成 C は `func_0x000180fdc700()` の形と `FUN_180fdc700()` の形の両方を出すため、既存規則と同じく `(?:func_0x000|FUN_)` で受けた。
- **数値の扱い**: emcc 通過は値の正しさを示さない。delay の wasm は全体で未成立 (引数数不一致 65・型不一致 115 が残る) のため、1000 trial 突合は未実施 (#3073 [KH-41] が担当)。

#### 10-7ab. #5385 (KH-159 残件): `FUN_180fcd400` ← `FUN_180fcce40` の 4048 を規則化 (4060 は未確定)

- **結論**: 残り 2 件のうち **4048 (`180fccee6`) を規則化** (件数 1 の assert 通過)。emcc error は **339 → 338** (−1 = 4048 の引数数不一致)。4060 (`180fcd074`) は未規則化 (下記)。
- **測定 commit**: `c1576d604` (コードを変えた commit: `ghidra_route/patches.py` +3 行)。基準は `e5261de58` (規則なし・origin/main)。
- **素材**: `plugins-kilohearts` → `HeartCore.core_64` (76,642,304 B、sha256 先頭 `d55ce8b4`)。Ghidra 12.1.4 (公式 zip sha256 先頭 `ddac49f9` 一致)・JDK 21・emsdk 6.0.12。
- **閉包**: `closure.py delay` = 139 関数・反復 1・FAIL 0 (wall 22.0 s)。
- **生成 C**: `ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat` (rc 0)。規則 1 件の件数 assert 通過。生成 C の差分は 1 行 (4048 の `FUN_180fcd400()` → `FUN_180fcd400(param_1,0.0,0)`)。
- **emcc**: `emcc -c -w -O1 -ferror-limit=0 -Wno-error=int-conversion` → 基準 339・規則後 338。`grep -c error:` で計数。4048 の該当 error (`too few arguments ... expected 3, have 0`) は消え、新規 error は無い (差分 1 件のみ)。
- **4048 の機械語 (capstone)**: `180fcce60 movq rdx,xmm0`・`movaps xmm6,xmm0` で入口値を保持。`180fccee0 xorps xmm1,xmm1` (+0.0)・`180fccee3 xor r8d,r8d` (0) の後、`180fccee6 call FUN_180fcd400`。この経路で xmm0 は書かれない (xmm0 = 入口 param_1)。xmm1 は call 直前に明示的に設定されるため、D5 の入口 live-in の置換には当たらない。
- **4060 が未確定の理由**: `180fcd074 call` の直前の xmm0 は `180fcd042`〜`180fcd069` の `subsd` 群の結果 (縮約の余り)。`movaps xmm1,xmm6` で xmm1 も設定される。C 側 4060 (`param_1 = FUN_180fcd400()`) は縮約の途中値の式が生成 C に無く、対応式を機械語から確定できなかった。`FUN_180fccf30` 以降 (`180fccf51` 比較・`180fcd0a0` の `FUN_180fdfdb0` 経路) を含めて未読。次 run で確定する。
- **stereo への影響**: 規則は `ABI['delay']` のみ。`ABI['stereo']` の抽出条件 (`'FUN_180fd4f30(' in r[2]`) に当たらず、stereo の生成 C は変わらない。
- **回帰 (gain / haas / gate)**: 規則なし (`e5261de58` の `patches.py`) と規則あり (`c1576d604`) で `ghidra_to_c.py <name> --fix bitcast,intload,stackpair,assoc,concat` を同じ閉包 (`closure.py`) から生成し `diff -r` → **3 本とも 0 行**。`ABI.get(name)` が name ごとに引くため、delay の規則は他の name に効かない。
- **未測定**: delay の数値突合 (wasm 未成立・#3073 [KH-41] の範囲)。

**測定 commit** (コードを変えた最後の commit): 規則追加の commit は `e0aff674f`。再測定の 2 点は `origin/main` `a0b804faf` (規則なし) と head (`ghidra_route` は `e0aff674f` と同一)。`git diff a0b804faf HEAD -- tools/targets/kilohearts/ghidra_route` は `patches.py` の 9 行追加 (上の表の差の由来)。

**残件の起票先** (本 issue の受入 1・2 の残り):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FUN_180fcd400` ← `FUN_180fcce40` の 2 件 (4048・4060) | stereo 族の残件 (引数数不一致 65 の内 2) | 本 issue #5385 に残りとして記載 (親 #4880) |
| 引数数不一致の残り 65 件 | Delay の emcc 不通過 (wasm 不成立) | #3844 [KH-79]・#3847 [KH-73]・#4917 [KH-135] (既存・open) |
| Delay の数値未検証 | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] (既存・open) |
