# REPORT_942_PTRSLOT — unit 53 の trap の上流は qstore 対象の 4B 初期化 slot (#942 受入 1・2)

既知類型との関係: **D17** (`docs/DEFECTS.md`)。64bit ポインタ局所の 0 初期化が 4B store に縮み、8B で読む C 転記 (`function_418190` = `_LStrArrayClr`) が上位 4B のゴミを読む、という同じ症状。修復は IR 側の qstore (`tools/m11/qstore/m11_qstore.py`・`tools/m11/m11_build.sh` で既定 ON)。C 転記側を 4B 読みにする案は D17 で不採用と明記されている。既存の類型に該当するので、DEFECTS の新規行案は出さない。

## 0. 結論

- unit 53 の trap の上流は `function_8cbb00` の `%stack_var_-48` (`alloca ptr`・4 byte)。`store ptr null` は下位 4 byte だけを消し、上位 4 byte には前の呼出しの残骸 (`1`) が残る。C 版 `function_418190` が `Q(dest)` (8 byte) で旧値を読むと `0x100000000` になり、`D(old-0xc)` が範囲外を読んで trap する。
- この slot は qstore の確定 site である (`tools/m11/qstore/results/qstore_sites.tsv` の `function_8cbb00 -48`・verdict `fix`・`store ptr null, ptr %stack_var_-48`。`tools/m11/qstore/REPORT.md` §4.2)。qstore 適用 IR では `alloca i64`・`store i64 0` になり、§2 の E1 と同じ IR になる。したがって本番経路では unit 53 は解消される**と推定**する。適用後 IR での実測は未実施 (§5)。
- 初版 (commit `5fe8dbe0`) の C 側 1 行変更 (`function_418190` の `Q(dest)`→`D(dest)`) は**撤回**した。qstore と二重になり、D17 が不採用とした「C 転記側だけを 4B にする」方式にあたる。`tools/m11/m11_ov.c` は main と同一。
- 初版の測定は base が qstore 前の IR だったため無効 (§5)。
- E3 (`4133f0`・`412d60` も 4B 読み) は採らない (§4)。

## 1. 症状 (qstore 前 IR での観測・base = HEAD `26f90ada`)

`probe_942_obj.py` (変種) で unit 53 の trap 直前の値を読んだ (`trap_obj_942.mjs`・記録は各記録点の最後の hit)。

| 記録点 | 値 | 読み |
|---|---|---|
| `8cbb00` entry (`arg1`=0x10bd3440・`arg2`=4) | `[arg1+8]` = 0 | object の field は entry 時点では nil |
| `8cbb00` で `418210(&stack_var_-48, 0, ti)` を呼ぶ直前 | `[stack_var_-48]` = **0x100000000** | 直前に `store ptr null` した slot が 8 byte で 1<<32 |
| `418210` の `418190` 呼出し直前 (`*arg1`) | **0x100000000** | 同じ値。この間に書込みは無い |

qstore 前の IR (`tools/m11/work/boot_final3.ll` の `function_8cbb00`): `%stack_var_-48 = alloca ptr, align 8` と `store ptr null, ptr %stack_var_-48, align 8`。datalayout は `p:32:32` で、`ptr` は 4 byte。

## 2. 切り分けの実験 (すべて qstore 前 IR)

| 実験 | 変更 | survey (ok / trap) | unit 53 | 判定 |
|---|---|---|---|---|
| E0 base | なし (HEAD 26f90ada) | 136 / 9 (OOB 8・halt 1) | trap | — |
| E1 IR 1 箇所 | `8cbb00` の `stack_var_-48` を `alloca i64`・`store i64 0` (IR 手修正・work 内のみ) | 137 / 8 (OOB 7・halt 1) | 解消 | 同じ slot の幅が原因。qstore の確定 site と同じ変換 |
| E2 C 1 行 (撤回) | `function_418190` の `Q(dest)`→`D(dest)` (commit `5fe8dbe0`) | 137 / 8 (OOB 6・halt 2) | 解消 | qstore と二重。D17 が不採用とした方式 |
| E3 C 3 箇所 (採らない) | E2 + `4133f0`・`412d60` も `D` | 137 / 8 (OOB 5・halt 3) | 解消 | boot 結果が変わる (§4) |

E1 は IR の slot 幅だけを変えた対照で、unit 53 の原因が `8cbb00` の 4B 初期化 slot であることを支持する。E2 は同じ現象を C 側で隠しただけで、修復としては採らない。

## 3. 残す成果物 (診断のみ・本番経路は変更しない)

- `tools/m11/ldfix/probe_942_obj.py` (記録点の変種生成。`PROBE2_BASE` = 0x11FFE000・SLOT2 = 128 byte) と `tools/m11/ldfix/trap_obj_942.mjs` (読み手)。
- 本番の修復 (`m11_ov.c`・`ldfix.py`・`fix_450560.py`・`m11_qstore.py`) は変更しない。

## 4. 採らなかった変更 (E3)

E3 では stage4 の boot が `threw: null`・`dllmain_done: true` になり、一見成功する。しかし (qstore 前 IR での観測):

- `va_calls` 1→3・`va_used` 1,310,720→888,995,840。VA #1・#2 は `size=887685120 (0x34e90000)` で、2 回目は OOM (NULL)。
- 巨大な要求は、旧値を誤って解放・確保しない経路に入ったことを示す。boot が成功したとは言えない。
- `getmem` 16→31・`freemem` 6→14 の増加も、誤った経路に入った結果の可能性がある。

よって E3 は採用しない。次の入口は「887MB 要求の size の計算元」。qstore 適用 IR で同じ現象が出るかは未確認。

## 5. 測定と再現の状態

- **初版の測定 (commit `5fe8dbe0`) は無効**。base は qstore 前の IR で、所要秒 (n=1) は比較の根拠にしない。
- **再測定は未実施**。必要なこと: (a) 素材 `work-m11` (`tools/m11/work/boot_final3.ll`・`m11_image.bin`)・work-liftdiff・emsdk `[EMSDK]`・RetDec `[RETDEC]` を揃える、(b) `python3 tools/m11/m11_cond.py --get qstore` が `applied` の IR で base (`m11_ov.c` = main) を測る、(c) pe の指紋 (`sha256sum block00031_PE.bin`) と qstore 状態を REPORT に書く。この run では `$ARTIFACTS_DIR` に `fl-win64.tar.zst` だけがあり、`tools/m11/work`・`[EMSDK]`・`[RETDEC]` が無いため、(a)〜(c) は実行できなかった。
- コード差分 (WORKFLOW §6): e2e の経路 (`m11_ov.c`・`ldfix_e2e.sh`・`stage4.sh`・`survey_stage4.mjs`・`ldfix.py`・`fix_450560.py`) は main (`bbb07d80`) に対して差分 0。

```sh
git diff bbb07d80 HEAD -- tools/m11/m11_ov.c tools/m11/ldfix/ldfix_e2e.sh tools/m11/ldfix/stage4.sh tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/ldfix.py tools/m11/ldfix/fix_450560.py | wc -l   # → 0
```

## 6. 受入への反映・未解決

- 受入 1 (trap 9 件の原因): **部分**。unit 53 の上流は D17 の 4B 初期化 slot と確定 (静的照合・§0)。修復は既存の qstore。適用 IR での消失は未実測。unit 87・138・17・56・144・149・158 は未確定。
- 受入 2 (boot threw): **部分**。boot threw は不変 (修復を入れていない)。次の入口は 887MB 要求の size の計算元。
- 受入 3 (件数反映): 変更なし。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| qstore 適用 IR での base 再測定 (unit 53 の消失の実測・qstore=applied・pe 指紋) | 受入 1 | #942 (次 run・素材が必要) |
| E3 の 887MB VirtualAlloc 要求 (2 回・OOM) の size の計算元 | 受入 2 | #942 (次 run) |
| unit 87・138 の上流 (`function_59f9a0`・`function_418210`)。qstore の確定 site かどうか | 受入 1 | #942 (次 run) |
| unit 17・56・144・149・158 の trap 位置の確定 | 受入 1 | #942 (次 run) |
| `alloca ptr` のうち C 側が 8 byte で読む slot の洗い出し (qstore の未検出分を含む) | 同種の残骸が他の unit にもある可能性 | #942 (次 run) |

## 7. 再現

```sh
grep -n "8cbb00" tools/m11/qstore/results/qstore_sites.tsv        # qstore の確定 site (-48 / -56)
python3 tools/m11/ldfix/probe_942_obj.py tools/m11/work/boot_final3.ll tools/m11/ldfix/work/probe_942_obj.ll
(cd tools/m11/ldfix && bash stage4.sh work/probe_942_obj.ll probe_obj)
S4_NAME=probe_obj S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_obj_942.mjs
git diff bbb07d80 HEAD -- tools/m11/m11_ov.c                    # 空 (初版の 1 行は撤回)
```
