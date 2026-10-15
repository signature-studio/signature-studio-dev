# p0c 付録 L (#3951: 0x5e1280 の buf_diff≠0 の原因特定)

REPORT.md 索引の §25。付録 K (§24, #3281) が出した未解決 (0x5e1280 buf_diff=3996) の切り分け。

## 25. #3951 [P0c-24]: 0x5e1280 の buf_diff≠0 は k80_diff の入力モデルの不一致だった

- 測定 commit: `73409179c` (コードを変えた最後の commit。`tools/plugins/p0c/k80_diff.py` の 4 行)。
- 基準: origin/main `26d6d4a03` (clean worktree `ws-3951`)。

### 25.1 原因 (機械語と IR の突合)

- 機械語 (VA 0x5e1280): `cvtss2sd xmm1, [0x6fff50]` → `mulsd xmm0, xmm1` → `call 0x409df0` (= `cvttsd2si rax, xmm0`) → rax を 2 本の dword に分けて store。
- `k80abi.json` の 0x5e1280: `xmm_slots=[xmm0]`、`xmm_width.xmm0=64` (#3641 `fd03fb1b0` で `mulsd` の `*sd` が 64 bit になった)。
- IR (`k80.hb.ll`): `%in.xmm0.bits` を `zext i64` して `__asm_mulsd__12` に渡す。IR は double として読む。IR は正しい。
- 食い違いは driver (`k80_diff.py` の `ir_expr`) にあった。native へは `vA[4].f` (double) を渡すが、IR へは `(u64)fbits((float)vI[4].f)` (float の bit 表現) を渡していた。同じ入力を両側に渡していないため、`ret`・`buf` が毎ケース食い違った (2000 case で ret 2000 / buf 3996)。
- 修復前の `ir_expr` は 32 bit の xmm 引数を前提にしていた。#3641 で幅が 64 になっても driver の分岐が追随していなかった。

### 25.2 修復 (測定 commit `73409179c`)

- `k80_diff.py` の `ir_expr`: 64 bit の xmm 引数 (`kind2=='xmm' and d2[1]==64`) は `(u64)vI[%d].u` (double の bit 表現) をそのまま渡す。他の分岐は変えない。
- 生成側 (`k80abi.py`・lift pass・IR) は変えていない。IR と ABI の 0x5e1280 はどちらも #3641 の後の値で正しい。受入条件 1 の「生成側で修復」は文字どおりには行っていない (§25.5)。

### 25.3 実測 (全て 4 vCPU・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`PATH=/usr/lib/llvm-18/bin:$PATH`)

| 測定 | commit | rc | 所要 (wall) | load 1 分 (開始 → 終了) | 結果 |
|---|---|---:|---:|---|---|
| `p0c_e2e.sh` (再生成) | `26d6d4a03` | 0 | 9 分 16 秒 | 未記録 | `== e2e OK ==` |
| `p0c4_abi_e2e.py 2000` (修復前) | `26d6d4a03` | 1 | 34 秒 | 6.05 → 3.81 | `run=68 ok=68 sig11=0`・[7] FAIL: `0x5e1280 buf_diff=3996` |
| `k80_diff.py --only 0x5e1280` (修復前, 2000) | `26d6d4a03` | 0 | 1 秒 | — | `ret_diff=2000 buf_diff=3996` |
| `k80_diff.py --only 0x5e1280` (修復後, 2000) | `73409179c` | 0 | 1 秒 | — | `ret_diff=0 buf_diff=0` |
| `k80_diff.py --only 0x5e1280` (修復後, 10000) | `73409179c` | 0 | 未計時 | — | `ret_diff=0 buf_diff=0` |
| `p0c4_abi_e2e.py 2000` (修復後) | `73409179c` | 0 | 29 秒 | 0.20 → 0.52 | `run=68 ok=68 sig11=0`・[7] PASS・`0x5e1280 buf_diff=0`・全 68 kernel buf_diff=0 |
| `p0c3_e2e.sh 2000` (回帰) | `73409179c` | 0 | 52 秒 | 0.29 → 0.69 | `== p0c3 e2e OK (構造修復 3 kernel bit-exact + 回帰 0) ==` |

- 修復前の 10000 case の 0x5e1280 (`buf_diff=19986`) は付録 K §24.1 の値。今回は再測定していない。

### 25.4 負論対照

- 同じ IR (`work/diff3/k80.hb.ll`) に対し、修復前の `k80_diff.py` (`git show 26d6d4a03:...`) と修復後を並べた。結果は 3996 (修復前) と 0 (修復後)。
- 修復後の 0x5e1280 の出力は、修復前と同じ IR・同じ入力の seed で、driver の引数だけが違う。
- 別 kernel への効き: 修復後 `p0c4 2000` の CSV で 68 kernel 全件 buf_diff=0 (`p0c4_head.log`)。修復前は 0x5e1280 の 1 件だけが非 0。

### 25.5 受入条件との対応

| 受入条件 | 状態 |
|---|---|
| 1. 0x5e1280 の buf_diff を 2000 / 10000 で 0 | 2000・10000 とも 0 (§25.3)。ただし修復箇所は driver (`k80_diff.py`)。生成側は変えていない |
| 2. `p0c4_abi_e2e.py 2000` の [7] PASS | PASS (`run=68 ok=68 sig11=0`、全 kernel buf_diff=0) |
| 3. 負論対照を数値で | 3996 (修復前) / 0 (修復後) (§25.4) |
| 4. #3641 のどの節が ABI・IR を変えたか | `fd03fb1b0` の `xmm_read_width` が `k80abi.py` の xmm0 幅を 32 → 64 にした (ABI)。IR は `%in.xmm0.bits` が `zext i64` になった (argfix が ABI から生成)。driver の `ir_expr` は 32 bit 前提のまま残っていた |

### 25.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入条件 1 の「生成側で修復」は driver の修復で置き換えた。IR・ABI は正しい (mulsd が double を読む) ため、生成側に修復すべき欠陥は見つからなかった | 修復の場所の判断が必要 | 本 PR の判断 (PM) |
| `k80_diff.py` の `ir_expr` は 32 bit の fp 引数の分岐を他 kernel にも持つ。他 kernel の幅 64 の xmm 引数は本修復で同じ経路に入る | 他 kernel の結果は 68 件全件 0 で変化なし。`p0c4 2000` で確認済み | 対応不要 (確認済み) |
| 修復前の 10000 case (19986) の再測定 | 数値の裏取りのみ | 測定のみのため子は起票しない |

## 25.7 差分 (WORKFLOW §6)

- 測定 commit: `73409179c`。`git diff 73409179c HEAD -- tools/plugins/p0c ':!*REPORT*'` の出力は空 (本 PR の REPORT 追加は REPORT のみ)。
- 測定後の差分は REPORT のみ。コードの再測定は要らない。

## 25.8 再現

```
export FL_WIN64_DIR=<fl-win64 展開先> RETDEC_ROOT=<retdec 展開先> PATH=/usr/lib/llvm-18/bin:$PATH
bash tools/plugins/p0c/p0c_e2e.sh
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000
python3 tools/plugins/p0c/k80_diff.py --ir tools/plugins/p0c/work/diff3/k80.hb.ll --cases 10000 --only 0x5e1280
```
