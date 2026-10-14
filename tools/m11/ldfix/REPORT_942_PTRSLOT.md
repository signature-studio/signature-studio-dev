# REPORT_942_PTRSLOT — trap 上流の旧値は「上位 4 byte の残骸」 (#942 受入 1・2)

既知類型との関係: DEFECTS の D4 (引数・slot の幅や deref の誤り) と同じ方向。ただし `ptr` 幅 (wasm32 4 byte) と C override の 8 byte 読みの食い違いで、既存の類型名には割り当てていない。類型名の割当てと `docs/DEFECTS.md` の変更は PM 判断。

## 0. 結論

- unit 53 の trap は、IR の `alloca ptr` (wasm32 で 4 byte) に `store ptr null` (4 byte) で入れた値を、C 版 `function_418190` が `Q(dest)` (8 byte) で読むことで起きる。上位 4 byte は前の呼出しの残骸 (`1`) なので、旧値が `0x100000000` になり、`D(old-0xc)` が範囲外を読んで trap する。
- `function_418190` の旧値読みだけを 4 byte (`D(dest)`) に変えると、unit 53 の trap は消える (survey ok 136→137・trap 9→8)。測定 commit は `5fe8dbe0`。
- 同じ読み方の `function_4133f0`・`function_412d60` も 4 byte にすると boot の `threw` は消えるが、boot 中に 887,685,120 byte (`0x34e90000`) の VirtualAlloc 要求が 2 回出て OOM (NULL) になり、後段へ進むだけ。**修正として採用しない** (§4)。
- 受入 1 は**部分** (unit 53 の発生源まで確定・修正)。受入 2 は**部分** (boot threw は不変。次の入口は 887MB 要求の発生元)。

## 1. 症状 (unit 53・base = 修復前 IR, HEAD 26f90ada)

`probe_942_obj.py` (変種) で unit 53 の trap 直前の値を読んだ (`trap_obj_942.mjs`・記録は各記録点の最後の hit)。

| 記録点 | 値 | 読み |
|---|---|---|
| `8cbb00` entry (`arg1`=0x10bd3440・`arg2`=4) | `[arg1+8]` = 0 | object の field は entry 時点では nil |
| `8cbb00` で `418210(&stack_var_-48, 0, ti)` を呼ぶ直前 | `[stack_var_-48]` = **0x100000000** | 直前に `store ptr null` した slot が 8 byte で 1<<32 |
| `418210` の `418190` 呼出し直前 (`*arg1`) | **0x100000000** | 同じ値。この間に書込みは無い |

IR の該当行 (`tools/m11/work/boot_final3.ll` の `function_8cbb00`): `%stack_var_-48 = alloca ptr, align 8` と `store ptr null, ptr %stack_var_-48, align 8`。datalayout は `p:32:32` で、`ptr` は 4 byte。`alloca ptr` は IR 全体で 514 箇所、`store ptr null` は 218 箇所ある。

## 2. 切り分けの実験

| 実験 | 変更 | survey (ok / trap) | unit 53 | 判定 |
|---|---|---|---|---|
| E0 base | なし (HEAD 26f90ada) | 136 / 9 (OOB 8・halt 1) | trap | — |
| E1 IR 1 箇所 | `8cbb00` の `stack_var_-48` を `alloca i64`・`store i64 0` (IR 手修正・work 内のみ) | 137 / 8 (OOB 7・halt 1) | 解消 | 同じ slot の幅が原因 |
| E2 C 1 行 (採用) | `function_418190` の旧値 `Q(dest)` → `D(dest)` (commit `5fe8dbe0`) | 137 / 8 (OOB 6・halt 2) | 解消 | 採用 |
| E3 C 3 箇所 | E2 + `4133f0`・`412d60` の旧値も `D` | 137 / 8 (OOB 5・halt 3) | 解消 | boot 結果が変わる (§4) |

E1 では unit 53 の trap だけが消え、他の unit は変わらない。E2 では unit 53 が消え、unit 144 は OOB から Halt に変わる (他は変わらない)。E1 は IR の slot 幅だけを変えた対照で、E2 の unit 53 の効果が同じ原因によることを支持する。

## 3. 採用する修正 (commit `5fe8dbe0`)

- `tools/m11/m11_ov.c` の `function_418190`: `u64 old = Q(dest);` → `u64 old = D(dest);` (1 行。コメントに理由)。
- 追加: `tools/m11/ldfix/probe_942_obj.py` (記録点の変種生成) と `trap_obj_942.mjs` (読み手)。probe は `PROBE2_BASE` = 0x11FFE000 (SLOT2 = 128 byte) を使う。

なぜ 4 byte 読みで安全か: wasm32 の pointer 値は 4 GB 未満。IR の `ptr` 格納 (4 byte) は下位 4 byte だけを残すので、4 byte 読みは格納幅によらず正しい。8 byte 読みは IR の 4 byte 格納の後に残った上位 4 byte を拾う。C 側の `Q(dest) = 0` (8 byte) の書込みは残した。

## 4. 採用しなかった変更 (E3)

E3 (`4133f0`・`412d60` も 4 byte 読み) では、stage4 の boot が `threw: null`・`dllmain_done: true` になり、一見成功する。しかし:

- `va_calls` 1→3・`va_used` 1,310,720→888,995,840。VA #1・#2 は `size=887685120 (0x34e90000)` で、2 回目は OOM (`[m11][VA] OOM want=887.7MB ... (NULL を返す)`)。
- 巨大な要求は、旧値を誤って解放・確保しない経路に入ったことを示す。boot が成功したとは言えない。
- `getmem` 16→31・`freemem` 6→14 の増加は、誤った経路に入った結果の可能性がある。

よって E3 の `4133f0`・`412d60` は採用しない。次の入口は「887MB 要求の size の計算元」。

## 5. 測定 (測定 commit `5fe8dbe0`)

- `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` (HEAD `5fe8dbe0`): **53.1 秒・rc 0・judge PASS**。load 0.19 / 0.40 / 0.35 (実行前)。
- base 比較 (HEAD `26f90ada`・同じ手順): **62.5 秒・rc 0・judge PASS**。
- stage4 (base = fix・両方同じ): units_run 17/942・icall_ok 24・threw `memory access out of bounds`・getmem 16・freemem 6 (`26f90ada` と不変)。
- survey (base = fix): ok 137 / trap 8 (OOB 6・halt 2)。`26f90ada` は 136 / 9 (OOB 8・halt 1)。
- trap の VA (OOB): 0x55790 (17)・0x16fde0 (56)・0x19f9a0 (87)・0x243270 (138)・0x264260 (149)・0x0 (158)。halt: 0x223840 (114)・0x25c540 (144・OOB から変化)。
- 修復件数 (不変): F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。

差分の確認: `git diff 5fe8dbe0 HEAD -- tools/m11 tools/m11/ldfix` は本 REPORT と DOC_MAP の追記だけで、コードの差分は 0 (§7 の確認を参照)。

## 6. 受入への反映・未解決

- 受入 1 (trap 9 件の原因): **部分**。unit 53 は発生源 (`alloca ptr` の 4 byte 格納と C の 8 byte 読みの幅不一致) を確定し、修正で trap が消えた。unit 138 は同じ残骸 (`0x1ce900000000`) を持つが、修正後も OOB が残るため、別の trap 位置がある。17・56・87・144・149・158 は未確定。
- 受入 2 (boot threw): **部分**。boot threw は不変 (`5fe8dbe0`)。E3 の boot の `threw` 消失は 887MB OOM に進むだけで、原因の確定ではない。
- 受入 3 (件数反映): **変更なし**。`#1469` で判定済み。本修正の件数反映は survey ok 136→137。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| E3 の 887MB VirtualAlloc 要求 (2 回・OOM) の size の計算元 | 受入 2 (boot threw の後段) | #942 (次 run) |
| unit 138 (同じ残骸を持つ) の修正後の OOB の位置 | 受入 1 | #942 (次 run) |
| unit 17・56・87・149・158 の trap 位置 (今回は未確認) | 受入 1 | #942 (次 run) |
| `alloca ptr` 514 箇所のうち、C 側が 8 byte で読む slot の洗い出し | 同種の残骸が他の unit にもある可能性 | #942 (次 run) |
| work-m11 の IR と現 main の不一致 | 測定の母体が現 main と違う | 既存 #680 |

## 7. 再現

```sh
bash tools/m11/ldfix/ldfix_e2e.sh                       # 5fe8dbe0 の e2e (要 fl-win64・work-m11・work-liftdiff 素材)
python3 tools/m11/ldfix/probe_942_obj.py tools/m11/work/boot_final3.ll tools/m11/ldfix/work/probe_942_obj.ll
(cd tools/m11/ldfix && bash stage4.sh work/probe_942_obj.ll probe_obj)
S4_NAME=probe_obj S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_obj_942.mjs
git diff 26f90ada 5fe8dbe0 -- tools/m11/m11_ov.c         # 採用した 1 行
```
