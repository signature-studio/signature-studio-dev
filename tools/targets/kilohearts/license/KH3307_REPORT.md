# KH-52 (#3307) — gen_simd の SSE 整数語彙 6 件の追加と module F 2 関数の lift 試行

- 親: #709 (KH-14)。前提 #3306 (KH-51, PR #3347 MERGED) と #709 の ymm 語彙 (PR #3315 MERGED) は main に入っている。
- 素材: `fl-win64` (`HeartCore.core_64` の sha256 一致を確認)・`toolchain-retdec`・`toolchain-emsdk`・`plugins-kilohearts` が `$HOME/artifacts` に実在。
- 測定 commit: `a441a3654` (コードを変えた最後の commit)。

## 1. 結論

| 受入条件 (#3307 本文) | 結果 |
|---|---|
| (1) 6 語彙を gen_simd.py に実装 | **達成**。`pcmpeqd`・`pcmpeqw`・`pmovmskb`・`pshufd`・`vpxor`・`tzcnt` を追加。宣言 6 件の abort スタブ 0 件 (§3-a) |
| (2) 2 関数を module F に加え emcc が通る | **部分**。試行ビルドは emcc 通過・`undefined_imports []` (§3-b)。ただし product 設定 `lic_config.json` には**入れていない** (§3-c) |
| (3) 2 関数の bit-exact を実機 (native_ref) と突合・ネガコン | **未達**。2 関数の ctx-fuzz シナリオは未作成。語彙単位の突合は達成 (§3-a) |
| (4) 既存 KH snap-in の 200/200 × 12 系が維持 | **達成**。6 種 × base/lic の 12 系すべて `trialsOk == trials` (§3-d) |

受入 (1)・(4) は達成、(2) は部分、(3) は未達。未達分は子 issue に移す (§5)。

## 2. 変更

- `license/lift/gen_simd.py`:
  - `base_of` 後の VEX 接頭除去の対象に `pxor`・`pshufd`・`pcmpeqd`・`pcmpeqw`・`pmovmskb` を追加 (SSE 名で既存分岐に流す)。
  - C 本体を追加: `pcmpeqd` (i128,i128→i128)・`pcmpeqw` (同)・`pmovmskb` (i128→i32)・`tzcnt` (i32→i32)。`pxor`・`pshufd` は既存分岐を使う。
- `license/scripts/kh52_sse_check.py`: 6 語彙の host SSE2 突合とネガコン (比較反転) を 1 コマンドで実行する検証。

## 3. 検証 (実測)

host: nproc=4, Linux, host の clang/gcc (`cc` -O1 -msse2)。

**(a) 語彙の bit-exact (`kh52_sse_check.py 200000 12345`、測定 commit `a441a3654`)**

| 検査 | 結果 | 所要 |
|---|---|---|
| positive: pcmpeqd/w・pmovmskb・pshufd (imm 全 256)・vpxor・tzcnt | cases 200000, **mismatch 0** | 0.57 秒 (real) |
| ネガコン: pcmpeqd の比較を反転 | mismatch 200000 → **FAIL を検出** | 同上 |
| RESULT | **PASS** (positive=True, negctrl_detected=True) | — |

**(b) module F の試行 (2 関数を `modules.F.lift` に追加、測定後に config は戻した)**

| 項目 | 値 |
|---|---|
| gen_simd | helpers 18・undefined(abort stub) 1 (`void __asm_int3()` のみ・既存) |
| wasm | 72,254 B・undefined imports 0・emcc 1.1 秒 |
| 変更前 (HEAD) | 54,394 B・sha `7ba79e65…8c7707` |

**(c) product 設定 (HEAD の `lic_config.json`) の module F 回帰 (測定 commit `a441a3654` の worktree で実測)**

| 項目 | 変更前 | 変更後 |
|---|---|---|
| module F wasm | 54,394 B・sha `7ba79e65…8c7707` | 54,394 B・sha `7ba79e65…8c7707` (不変) |

2 関数は product 設定に入れていない。理由: 実機 bit 突合 (受入 3) が未了のまま lift すると、対応の無い命令を含む関数が無言で誤る恐れがあるため (`KH709_REPORT.md` §3 の方針を維持)。

**(d) 既存 snap-in 回帰 (`lic_build.py --dsp <n> --tag {base,lic} --trials 200 --seed 1`、測定 commit `a441a3654` の worktree で実測)**

| dsp | base trialsOk/trials | lic trialsOk/trials | calls (lic) |
|---|---|---|---|
| matrix | 200/200 | 200/200 | 1149/1149 |
| gain | 200/200 | 200/200 | 999/999 |
| haas | 200/200 | 200/200 | 1100/1100 |
| clipper | 200/200 | 200/200 | 1100/1100 |
| gate | 200/200 | 200/200 | 999/999 |
| quickeq | 200/200 | 200/200 | 999/999 |

## 4. 測定 commit と差分

- 測定 commit: `a441a3654`。
- コード差分 (測定 commit → HEAD): 0 行 (REPORT 追記のみの commit は含めない)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 2 関数 (`0x180f89cf0`・`0x180fb6124`) の ctx-fuzz シナリオ作成と native_ref 突合・ネガコン | 受入 (3)。未検証の関数を product に入れられない | 子 issue (起票予定, 親 #3307) |
| 2 関数を `modules.F.lift` (product) へ入れ、`excluded_i256` を外す | 受入 (2) の product 部分。突合後に行う | 上記子 issue に含める |
