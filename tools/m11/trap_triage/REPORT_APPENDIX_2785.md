> **正本**: `tools/m11/trap_triage/REPORT_714.md`。本付録は #2785 (#1426 の受入 3・obj の生成元) の詳細。

# #2785: obj の生成元 (IR 静的追跡と inspector 実測, 2026-10-14, n=1)

測定 commit `bbb07d80` (origin/main)。素材 `fl-win64` (`extracted/block00031_PE.bin` のみ) と `work-m11` を展開。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。build は `work/obj`・`boot.o` を消してから行った clean build。

## 1. 工程と既定 survey (HEAD)

| 工程 | 結果 |
|---|---|
| `m11_gen_ir2.sh` | rc=0 / `boot_final.ll` 490735 行 / 42.3 秒 |
| `m11_build.sh` (clean) | rc=0 |
| `m11_survey.mjs` (既定) | ok 872 / trap 22 / noproc 1 / miss 47 / units 942 |
| `check_682.py` | 4/5 (304=ok 555=ok 923=trap 291=ok 296=ok) rc=1 |

REPORT の既定 (870 / 24、304・555 が trap) とは一致しない。`bbb07d80` の既定挙動であり、本 PR はコードを変えない (`git diff bbb07d80 HEAD -- tools/m11 ':!*.md'` は 0 件)。差の原因は未特定。

## 2. obj の生成元 (IR 静的, `boot_final.ll`)

### 2-1. 304・555 (`function_535bf2` の obj)

- `function_4fb910(arg1, arg2)`: `G = load [0x11f26a0]` (`18818720`) を取り、`410730(G, -1)`・`4fad10(G, arg1, arg2)`・`410a50(G)` を呼ぶ。
- `function_4fad10` の `%43 = call 535240(%42, %36)` が obj の作成。`535c11(%43)` は同関数内の 2 か所 (`%44` と `%56`) で呼ばれる。
- `function_535240(a1, a2) = 535b30(const 1003752, a2, a1)`。`function_535b30` は `a2 != 0` のとき `410320` で確保し、`40f9e0` で初期化して `[node+8] = a3`・`[node+16] = -1` を書く。つまり 535c11 に渡る obj は 4fad10 内で新規に確保された node。
- **引数の取りこぼし**: `function_535c11(arg1)` は `arg1` を読むが、境界外時の分岐先を `call i64 @function_535bf2()` (引数なし、`boot_final.ll` 189403 行) と書く。`boot_final3.ll` (build の入力) では `call i64 @function_535bf2(i64 0)` (192097 行) になっている。どちらも 535bf2 の obj は 0 になる。
- 旧 HEAD (`e07712a4`、REPORT_APPENDIX_1602 §16) では obj=0 で OOB。`bbb07d80` の既定 survey では 304・555 とも trap しない (`returned 1`)。ただし、obj が 0 のまま通る理由は、この run では確定していない。

### 2-2. 923 (`function_410b10` の obj)

- inspector (`M11_INSPECT_FRAMES=9`, `bbb07d80` 既定 build): trap 時の `410b10` local0 = `0x10bd3960` (obj)。呼出し鎖は `410730 (local0=0x10bd3960, -1)` ← `4fb910 (local0=0xf6b900, local1=0x1faa18)` ← `136c660` ← `m11_tr_function_136c660` ← `m11_icall` ← `m11_call_unit` (unit 923)。
- `4fb910` の 2 引数は `136c660` の IR 定数 (`102127` 行: `16169216` = `0xf6b900`, `2074840` = `0x1faa18`)。obj ではない。obj は `410730` の第 1 引数 = `G`。
- `G` への書込みは 2 箇所だけ。`function_52f1f0` (`187880` 行) が `G = function_4fa990(995616, %20)` で設定し、`function_52f090` (`187795` 行) が 0 にする。`function_4fa990` (`178676` 行) は `410320` で確保し、`40f9e0` で初期化する。
- 実測: obj `0x10bd3960` は線形メモリ内。`[obj+8]` (peek) = 0。
- REPORT_714 §9・§12 の `4fb910 local1 = 0x1fa8d8` は、この HEAD の実測 (`0x1faa18`、IR 定数と一致) と違う。旧 build の値として扱う。

## 3. 判定

- 受入 3 (`obj` を作る関数の特定): **達成** (IR 上の生成関数を特定。304・555 側は `535240` → `535b30` → `410320` (4fad10 内で確保)。923 側は `4fa990` (`52f1f0` で G に設定))。
- 受入 4 (回帰 0, 既定 OFF の survey が 870 / 24): **未達**。HEAD の既定は 872 / 22。本 PR はコード変更なしで、この差は本 PR 由来ではない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `535c11` → `535bf2` の obj 引数の取りこぼし (IR に残る。`boot_final3.ll` では `i64 0`) | 304・555 の obj が 0 のまま | #1426 (継続) |
| HEAD の既定 survey 872/22 と REPORT の 870/24 の差。304・555 が HEAD で ok になる理由も未確認 | 受入 4 | #1426 (継続) |
| 923: `G` = `0x10bd3960` の `[obj+8]` = 0 の由来 (`52f090` の 0 化との順序) | 923 が trap | #1426 (継続) |
