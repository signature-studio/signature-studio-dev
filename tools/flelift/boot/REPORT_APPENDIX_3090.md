# tools/flelift/boot — REPORT 付録 (FLE-12 (#3090): 0x6a7b70 の呼出元と幅の源)

> `REPORT.md` §0 の 1 行から参照する付録。親は #3060 → #2702。本節の数値は HEAD `a409cd6f` で採取した
> (診断 probe を入れた最後のコード commit `0307d592` と測定対象コードは差分 0。`0307d592` の run のログは保存されていないため再採取した)。

## 結論 (先出し)

- **呼出元 (実測)**: `0x6a7b70` (fill コールバック) への dispatch は boot 1 回で **6 回**。全て戻りアドレス `0x6c7923` (`f_6c7610` 内)。
  その直前 `0x6c791f` が `call qword ptr [0x15f4b80]` (`r13` = `0x15f4b80`・slot の値 `0x6a7b70`)。
  `f_6c7610` の上位呼出元は **`0x815920` (`f_815050` の `call f_6c7610` 直後)**。shim 有・ネガコンとも同一。
- **幅 r8 の源 (実測 + lift の逆引き)**: `f_6c7610` は `r8 = [rbp+0x48] − [rbp+0x40]` (矩形の右端 − 左端、`0x6c7652`〜`0x6c765e`)。
  呼出し時の矩形は `(0,0,1048576,1048576)` (実測)。`f_815050` の `[rbp+0x214]` (= W) が 1048576 (実測)。
  **W の源は命令の即値 (推定・静的な逆引き)**: `0x81571b` と `0x81572c` の `movabs rax, 0x4130000000000000` (= 1048576.0 = 2^20) が
  `[rbp+0x184]`・`[rbp+0x18c]` に入り、`f_40c660` (double→int) を経て W になる。
  即値は PE のバイト列と一致 (`VA 0x81571b`・`VA 0x81572c` が `48 b8 00 00 00 00 00 00 30 41`。imm64 は 8 バイト)。**lift の変換誤りではない**。
- **修復はしない**。理由: 即値 2^20 の幅で作った面 (`f_6cefb0(w,h,1)` の戻り `this=0x12d6a090`) は `[this+0x50]` (buf) = 0 のまま
  で、fill がそこへ 4 MiB ずつ書く (dst = 0x0, 0x400000, …, 0x1400000)。native で同じ経路が通るか (面の生成・clip・alloc
  失敗の扱い) は未確認のため、どこを直すかを決められない。推定: native では面の生成が失敗して別経路に入る (未検証)。
- **0x15F34A0 の書込み元 (受入 3)**: 未了。lift C の `0x15f34a0` の参照は `s2:94092` (`0x6542eb` の `lea rdx,[0x15f34a0]`、
  `f_653f40` の登録ループで `f_653dd0` に渡す引数) の 1 箇所。直接の store は無く、終了前に 0 へ戻す箇所は特定していない。

## 1. 計測 (HEAD `a409cd6f` で再採取、`bash tools/flelift/boot/fle6_measure.sh`、素材 `fl-win64` + `toolchain-emsdk`)

- 再採取の理由: `0307d592` の run のログは保存されていない。`0307d592` → HEAD で測定対象コード (`x64c.py` / `build.sh` / `fle6_measure.sh` / `fle_boot.c` / `rt` / `gen_boot.py`) の差分は空 (`git diff --stat 0307d592 HEAD -- ...` が空)。よって HEAD の値を `0307d592` の run の再現値とする。前版の秒数・RSS 表は出典を確認できないため、本再採取の値に置き換えた。

| 工程 | 結果 | 秒 | ピーク RSS | load (開始 → 終了) |
|---|---|---|---|---|
| gen-A | rc 0 | 7 | - | 0.40 → 0.45 |
| lift (x64c closure 2・`FLE_EXTRA_ROOTS=0x6a7b70`・cap 13800MB) | rc 0・29,908 関数・1,557,903 insn | 81 | 609MB | 0.45 → 1.20 |
| clang shard ×8 (-O0・P3・cap 5000MB) | 8/8 OK・cap 超過 0 件 | 103 | 2,182〜2,668MB | 1.20 → 2.04 |
| boot shim (`FLE_IPP=1`) | units 209・stopped 209・IPP 判定 NG (`ptr_15F34A0=0x0`) | 25 | - | 2.04 → 1.87 |
| boot ネガコン (`FLE_IPP=0`) | units 209・stopped 209・IPP 判定 OK | 23 | - | 1.87 → 1.69 |

- 全体 3 分 59 秒 (`real 3m59.268s`)。`nproc` 4・MemAvailable 14,783,096 kB。
- link: mismatch 0 / undefined 0 / duplicate 0 (`fleboot_plain.cjs` 127,079,654 B)。
- 計数 (units・GetMem / FreeMem)。修正前 (`a5fb0d2d`・診断なし) も本 PR で再測定した:

| 測定 | commit | units | GetMem | FreeMem | IPP 判定 |
|---|---|---|---|---|---|
| shim 有 (`FLE_IPP=1`) | `a409cd6f` (HEAD・診断あり) | 209 | 2,314 | 1,199 | NG (`ptr_15F34A0=0x0`) |
| ネガコン (`FLE_IPP=0`) | `a409cd6f` (HEAD・診断あり) | 209 | 1,891 | 776 | OK |
| shim 有 | `a5fb0d2d` (修正前・診断なし) | 209 | 2,314 | 1,199 | NG (`ptr_15F34A0=0x0`) |
| ネガコン | `a5fb0d2d` (修正前・診断なし) | 209 | 1,891 | 776 | OK |

- 基準 (`REPORT.md` §9-2 の shim 有 2,314 / 1,199、ネガコン 1,891 / 776) は測定 commit `a741a0ca` (FLE-9) の値。上表の `a5fb0d2d` 行で同値を再確認した。`a741a0ca` → `a5fb0d2d` で測定対象ファイル (上記 6 件) の差は `fle_boot.mjs` の undo probe 出力の追加 (読み取りのみ) だけ。
- 診断 probe (`fle_boot.c`・`fle_boot.mjs` の出力) は出力のみで、実行経路と計数を変えない (上表で `a409cd6f` と `a5fb0d2d` が同値)。
- **KPI (前後)**: FLEngine 起動の unit 通過 209 → **209 (変化なし)**。最初のウィンドウ: 未到達 (unit 209 の後の `MessageBoxA` → `exit(0)` のまま)。

### 1-1. 0x6a7b70 への dispatch の実測 (`fle_boot.c` の `[fill6a7b70]` 行、shim 有・ネガコンで同一)

| # | ret (呼出元) | dst (rcx) | val (edx) | cnt (r8, DWORD) | this (R[3]) | 矩形 (f_6c7610 の rect) |
|---|---|---|---|---|---|---|
| 0 | 0x6c7923 | 0x0 | 0x0 | 0x100000 | 0x12d6a090 | (0,0,1048576,1048576) |
| 1〜5 | 0x6c7923 | 0x400000 〜 0x1400000 (+0x400000 ずつ) | 0x0 | 0x100000 | 同上 | 同上 |

- `caller=0x815920` (6 件とも)。初回の呼出元フレーム: `callerRbp=0x1158b318`、`w=1048576`、`h=1048576`、
  `spi_left=0` (`[rbp+0x1c8]`・`SystemParametersInfoW` の soft stub は out を書かない)、`sm13=0`、`sm14=0` (`GetSystemMetrics` の soft stub)。
- 6 回で止まる理由は未特定 (`f_6c7610` の行ループの上限の源は未確認)。

### 1-2. 読み取り (lift C の逆引き・`f_6c7610` / `f_815050`)

- `f_6c7610(rcx=this, rdx=RECT*, r8=値, r9=flag)`: `rect` を `[rbp+0x40..0x50)` にコピー → `f_6ce3f0(this, rect)` の真偽で続行
  (`0x6c7643`) → `r8 = right − left` (`0x6c7652`〜`0x6c765e`、`[rbp+0x38]`) → 面の先頭 `dst = [this+0x50] + top·[this+0x78] + left·[this+0x74]`
  (`0x6c7675`〜`0x6c768d`) → 行ループ内で `call [0x15f4b80]` (`0x6c791f`)。
- `f_815050` は `this = f_6cefb0(w = [rbp+0x214], h = [rbp+0x218], r8b = 1)` (`0x8158f8`)、`rect = [rbp+0x20c..0x21c) = (0,0,w,h)` (`0x8154d7`・`0x815904`〜`0x81590b`)。
  `r9 = 0x100` (`0x815915`)。`0x815920` は `f_6c7610` の戻りアドレス。
- `W = [rbp+0x214]` の計算: `0x8154f2` で `*(0x15f6f60)` (`GetSystemMetrics` の結果、boot では 0) を入れた後、
  `0x815854` で `[rbp+0x228] + f_40c660(·) + [rbp+0x22c]` に置き換えられる。`[rbp+0x228]` (`0x8157f3`) は `f_40c660(0x174 の符号反転 + c)` と `[rbp+0x1c8]`
  (SPI の out = 0) から、`0x815831` の `f_40c660([rbp+0x184] + c)` は即値 2^20 由来。
  `0x8158d2`〜`0x8158e5` で max を 16 の倍数に切り上げた値を [0x214] と [0x218] の両方に入れる (w = h)。
  よって **W は SPI / GetSystemMetrics の stub 出力に依存しうる**。stub 値 (現在 0) を変えた実測は未取得のため、依存の有無は未確定 (推定)。

## 2. 検証 (同一性・負例)

- lift の即値: PE の `VA 0x81571b`・`VA 0x81572c` のバイト列 (pefile で読み出し・`48 b8 00 00 00 00 00 00 30 41`) は `movabs rax, 0x4130000000000000` で、lift C と一致。
- 診断の追加だけで、既存の計測値 (units 209・GetMem/FreeMem) は不変 (§1)。
- 負例: 未実施 (本件は再現と特定のみ。修復を入れていない)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 面 `f_6cefb0(2^20, 2^20, 1)` が native で作られるか・alloc 失敗時の扱い (buf=0) と、fill の 6 行で止まる源 | unit 209 の MessageBoxA 直前の 0 埋め。修復の方向が決まらない | 子 issue (`[FLE-13]`、`親: #3090`) |
| 0x15F34A0 を終了前に 0 へ戻す書込み元 (受入 3 の残り) | #3060 受入 4 の残り | 本 issue #3090 (Refs のため open のまま) |
| `[rbp+0x184]` の即値 2^20 が native の意図どおりか (clip・面の寸法の正規化の有無) | W の正しい値が決まらない | 子 issue `[FLE-13]` |
| SPI / GetSystemMetrics の stub 出力 (現在 0) が W に入るか。native 相当の値で W が変わるか | W = 2^20 の依存先が未確定 (stub 値を変えた実測は未取得) | 子 issue `[FLE-13]` |

既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 と照合。命令の即値・変換は PE と一致し、lift 欠陥の根拠は確認できない)。
