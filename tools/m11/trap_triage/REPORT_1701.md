# REPORT_1701 — 計測 build の getmem −4 の帰属 (C 側の計測 flag: rt.o / ov.o / リンク時 EXPORTS) (#1701 = [M11-N116], 親 #1542)

## 0. 結論

- 測定 commit: **`fb3c40c3`** (測定時にコードを変えた最後の commit)。以降は main 取り込み (`00083cdb`) で #1894 の entry probe が `m11_ov.c`・`m11_build.sh` に入ったが、既定 OFF (§5)。
- −4 は **rt.o の計測 flag** に帰属した。`rt.o` だけ計測 OFF (既定) に戻すと getmem は 2008 → **2012 (既定と一致)**。`rt.o` だけ計測 ON にすると既定 IR のままでも 2008。
- `ov.o` の計測 flag (O0) は本切り分けでは検証対象外。`m11_ov.c` の計測本体は `M11_OV_413060=0`・`M11_OV_CLASSCREATE=0` の条件で未コンパイルのため、`M11_OV_INSTR` を変えても ov.o の object は C と同一で、O0 の 2008 は構造上の必然 (寄与の有無は判定していない)。ov.o の寄与を測るには `M11_OV_413060=1` 側の比較が必要 (IR 挙動を変えるため別 issue)。リンク時 EXPORTS (`_m11_dest_obs_*`) を外しても 2008 のまま (寄与なし)。
- survey 判定 (ok/trap/clobber) は全構成で 870/24/0。既定の基準 (870/24/0) は変えていない。
- 未解決: rt.o のどの部分が −4 を生むか (機序) は未特定。n=1 のみ (決定性は未確認)。→ §3 の子 issue。

## 1. 測定 (測定 commit `fb3c40c3`・直列・単発・n=1・foreground)

**実行環境**: 4 vCPU・load 0.4〜1.2。素材 `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-m11` → `tools/m11/work/` (展開後 `m11_gen_ir2.sh` で作り直し)、`toolchain-emsdk` → [EMSDK]。`toolchain-retdec` は展開せず、[RETDEC] の既存を使用 (本測定は lift を走らせない)。
IR 生成: `ldfix=applied`・F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 errors=0 (REPORT_1542 と一致)。

**切り分けの定義** (`tools/m11/trap_triage/repro_1701_rt_ov.sh`。基準は REPORT_1542 の C = `M11_PROBE_VARIANT=noren`・計測 ON で IR を既定と同一に戻した build):

| 構成 | 内容 | boot_final3.ll md5 | undefined symbol | ok | trap | clobber | getmem | fastmm_getmem_impl |
|---|---|---|--:|--:|--:|--:|--:|--:|
| A_default | 計測 OFF (既定) | `baa100ff` | 0 | 870 | 24 | 0 | **2012** | 2096 |
| C_noren | 計測 ON・IR 既定同一 (基準) | `baa100ff` | 0 | 870 | 24 | 0 | **2008** | 2091 |
| R0_rtOFF | C + rt.o のみ計測 OFF (EXPORTS も外す) | `baa100ff` | 0 | 870 | 24 | 0 | **2012** | 2096 |
| O0_ovOFF | C + ov.o のみ計測 OFF (**同一 object・検証対象外**: 計測ブロックが未コンパイル) | `baa100ff` | 0 | 870 | 24 | 0 | **2008** | 2091 |
| L0_lnkOFF | C + リンク時 EXPORTS のみ外す | `baa100ff` | 0 | 870 | 24 | 0 | **2008** | 2091 |
| R1_rtON | A + rt.o のみ計測 ON | `baa100ff` | 0 | 870 | 24 | 0 | **2008** | 2091 |

- 全構成で IR md5 が同一 (`baa100ff`)。post の差は無い。差は C 側のコンパイル flag だけ。
- 所要: 6 構成 (build + survey) で 3 分 22 秒 (`time` 実測)。

**変更点** (`m11_build.sh`): `M11_RT_INSTR` (rt.o の計測値)・`M11_OV_INSTR` (ov.o の計測値)・`M11_LINK_INSTR` (リンク時 EXPORTS) を追加。既定値は従来と同じ (`M11_INSTR_413060` と連動) なので、既定の build は変わらない。`m11_survey.mjs` は `_m11_dest_obs_n` が export されているときだけ dest 観測を読む (既定の出力は変わらない)。

## 2. 解釈

- **帰属**: −4 は rt.o の計測 flag。R0 (rt.o 計測 OFF) で既定 2012 に戻り、R1 (rt.o 計測 ON のみ) で 2008 に落ちる。
- **ov.o は検証対象外**: 本切り分けでは ov.o の計測 flag は無効 (計測コードが未コンパイル) のため、O0 (ov.o のみ OFF) は C と同一 object で 2008 になる。ov.o の寄与は本 REPORT では判定しない。`m11_ov.c` の `function_413060` 計測本体 (`m11_probe(8)`・`m11_dest_obs`) は `#if M11_OV_CLASSCREATE || M11_OV_413060` の内側 (REPORT_1542 §2 の推定と整合)。
- **リンク時 EXPORTS は寄与なし**: L0 は C と同じ 2008。
- **機序 (推定・未検証)**: noren 構成では IR から `m11_dest_obs` を呼ぶ wrapper が無い (`M11_PROBE_VARIANT=noren` は 413060 を wrapper 化しない)。したがって計測 ON の rt.o で**実行されるコードは同じ**。違うのは rt.o 内の静的データ (`g_dest_h`・`g_rec_st/len/rc/h`) と関数の有無によるリンク後の配置 (BSS/text のアドレス) のみ。−4 はアドレス依存の値 (ポインタ由来の判定・ハッシュ・配置) である可能性が高い。ただし配置が原因であることは**未確認** (配置だけを変える対照は未実施)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| rt.o の計測 flag が −4 を生む機序 (静的データの配置か・関数の有無か) | 計測 build の getmem 計数が既定と 4 ずれる。survey 判定には出ない | #1952 ([M11-N129]) |
| n=1 のみ。決定性 (n=2,3) は未測定 (REPORT_1542 で同 IR の A・C は n=3 で一致済み) | 帰属の再現性が未確認 | #1952 ([M11-N129]) |

子 issue: #1952 ([M11-N129])。親 #1701。

## 4. 再現

- `bash tools/m11/trap_triage/repro_1701_rt_ov.sh [N]` (N = 反復回数・既定 1)。`work/split_1701/table.tsv` に出力。前提: `m11_gen_ir2.sh` 実行済み・`FL_WIN64_DIR` 設定・[EMSDK] 配置済み。
- 測定 commit `fb3c40c3`。

## 5. 測定 commit からの差分と HEAD での再測定

- `git diff fb3c40c3 00083cdb -- tools/m11/m11_build.sh tools/m11/m11_rt.c tools/m11/m11_ov.c tools/m11/m11_post.py tools/m11/m11_survey.mjs` (main 側の測定コード差分): `m11_build.sh` の `-DM11_ENTRY_PROBE=${M11_ENTRY_PROBE:-0}` 追加・ov.o の stamp 追加・EXPORTED_FUNCTIONS への `_m11_fe_get,_m11_fe_clear` 条件付き追加、`m11_ov.c` の `function_417b70` の `#if M11_ENTRY_PROBE` 囲み、`m11_survey.mjs` 1 行。**既定 (`M11_ENTRY_PROBE=0`) では `#if` が偽・EXPORTS 不変**で、ov.o のソースは既定 build で同じ内容になる (`#if` 偽)。ただし stamp 追加により ov.o は初回に 1 回再コンパイルされる。build 結果が同一であることは未確認 (再測定が必要)。
- 測定 commit からの本 PR の差分 (`git diff fb3c40c3 HEAD -- tools/m11/m11_build.sh tools/m11/m11_ov.c`) は、上記 main 側差分 + 本 PR の `M11_RT_INSTR`・`M11_OV_INSTR`・`M11_LINK_INSTR` 追加 (既定 build 不変)。
- **前処理レベルの確認 (HEAD `709996a8`・実測)**: `M11_ENTRY_PROBE=0` 相当の `-D` (計測系 flag は全て既定値) で `m11_ov.c` を `cc -E -P` した出力を、測定 commit `fb3c40c3` の `m11_ov.c` と比較した。両者 1689 行で `cmp` 一致 (差分 0)。これは ov.o の前処理結果が同一であることの確認で、object (`.o`) や IR の同一性は未確認。
- **HEAD での再測定は未実施 (素材不足・fix run 時点)**: `$ARTIFACTS_DIR` には `fl-win64.tar.zst` のみで、`work-m11`・`toolchain-emsdk`・`toolchain-retdec` が無い。`tools/m11/work/`・emsdk・retdec も存在しないため `m11_build.sh` は `/opt/emsdk` の不在で止まり、`repro_1701_rt_ov.sh` は実行できない。§1 の数値は測定 commit `fb3c40c3` の値であり、HEAD の値ではない。再測定は PR 本文の `oc_artifacts: fl-win64 work-m11 toolchain-emsdk toolchain-retdec` 指定で再起動して行う。
- **測定コード差分の全文 (`git diff fb3c40c3 d19f47c4 -- tools/m11/m11_build.sh tools/m11/m11_ov.c`)**: 以下。この差分は build 経路 (ov.o の再コンパイル判定・EXPORTS・`#if` 囲み) に入るため、§6 の基準では再測定が必要。`M11_ENTRY_PROBE=0` では `#if` 偽・EXPORTS 不変だが、object・IR の同一性は未確認。

```diff
--- a/tools/m11/m11_build.sh (`git diff fb3c40c3 d19f47c4 -- tools/m11/m11_build.sh tools/m11/m11_ov.c` の内容。hunk ヘッダの行番号を除く)
+++ b/tools/m11/m11_build.sh
@@ -25,7 +25,7 @@ M11_OV_INSTR="${M11_OV_INSTR:-$M11_INSTR_413060}"   # #1701: ov.o をコンパ
 M11_LINK_INSTR="${M11_LINK_INSTR:-$M11_INSTR_413060}"   # #1701: リンク時の EXPORTS (_m11_dest_obs_* 等) を足すか。既定は M11_INSTR_413060 と同じ
 M11_DEST_READ="${M11_DEST_READ:-1}"   # #944: 0 = 413060 後の dest 読出し (指紋) を止める。読出しが挙動を変えるかの切り分け用。既定 1
 M11_FIX_535BF2="${M11_FIX_535BF2:-0}"   # #714: 1 = m11_ov.c の function_535c11/535bf2 転記 (IR 未定義 535c2e・境界 535c11 の再現); 0 = lift 版 (既定)
-CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=$M11_LB_BASE -DM11_OV_CLASSCREATE=$M11_OV_CLASSCREATE -DM11_OV_414AD0=$M11_OV_414AD0 -DM11_FIX_652500=$M11_FIX_652500 -DM11_OV_413060=$M11_OV_413060 -DM11_NEG_413060=$M11_NEG_413060 -DM11_DEST_READ=$M11_DEST_READ -DM11_INSTR_413060=$M11_INSTR_413060 -DM11_FIX_535BF2=$M11_FIX_535BF2 -DM11_INSTR_K12=${M11_INSTR_K12:-0} -DM11_INSTR_40FF70=${M11_INSTR_40FF70:-0} -DM11_TRACE_ISOLATE=${M11_TRACE_ISOLATE:-1}"
+CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=$M11_LB_BASE -DM11_OV_CLASSCREATE=$M11_OV_CLASSCREATE -DM11_OV_414AD0=$M11_OV_414AD0 -DM11_FIX_652500=$M11_FIX_652500 -DM11_OV_413060=$M11_OV_413060 -DM11_NEG_413060=$M11_NEG_413060 -DM11_DEST_READ=$M11_DEST_READ -DM11_INSTR_413060=$M11_INSTR_413060 -DM11_FIX_535BF2=$M11_FIX_535BF2 -DM11_INSTR_K12=${M11_INSTR_K12:-0} -DM11_INSTR_40FF70=${M11_INSTR_40FF70:-0} -DM11_TRACE_ISOLATE=${M11_TRACE_ISOLATE:-1} -DM11_ENTRY_PROBE=${M11_ENTRY_PROBE:-0}"
 # image 終端 (SizeOfImage 0x18c0000) + LB_BASE が GLOBAL_BASE (0x10000000) 以内であること
@@ -185,6 +185,9 @@ if [ "$(cat work/ov_trace_isolate.stamp 2>/dev/null || echo 1)" != "${M11_TRACE_
 echo "${M11_TRACE_ISOLATE:-1}" > work/ov_trace_isolate.stamp
 # #882: 40ff70 観測 probe の ON/OFF で古い ov.o を再リンクしない
 if [ "$(cat work/ov_instr_40ff70.stamp 2>/dev/null || echo none)" != "${M11_INSTR_40FF70:-0}" ]; then rm -f work/obj/ov.o; fi
+# #1894: entry probe (417b70 の ov 版) の ON/OFF で古い ov.o を再リンクしない
+if [ "$(cat work/ov_entry_probe.stamp 2>/dev/null || echo 0)" != "${M11_ENTRY_PROBE:-0}" ]; then rm -f work/obj/ov.o; fi
+echo "${M11_ENTRY_PROBE:-0}" > work/ov_entry_probe.stamp
 echo "${M11_INSTR_40FF70:-0}" > work/ov_instr_40ff70.stamp
 echo "$M11_FIX_535BF2" > work/ov_535bf2.stamp
 CF="${CF_BASE//-DM11_INSTR_413060=$M11_INSTR_413060/-DM11_INSTR_413060=$M11_OV_INSTR}" cc m11_ov.c work/obj/ov.o work/boot_final3_sigs.h
@@ -199,7 +202,7 @@ emcc work/obj/*.o -o work/m11_boot.cjs.tmp \
   -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 \
   --no-entry -Wl,--export-all \
   -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPF32,HEAP32,HEAPF64,HEAPU32,HEAP64,wasmTable,addFunction \
-  -sEXPORTED_FUNCTIONS=$EXPORTS$( [ "$M11_LINK_INSTR" = 1 ] && echo ,_m11_dest_obs_n,_m11_dest_obs_hhi,_m11_dest_obs_hlo,_m11_dest_rec ) \
+  -sEXPORTED_FUNCTIONS=$EXPORTS$( [ "$M11_LINK_INSTR" = 1 ] && echo ,_m11_dest_obs_n,_m11_dest_obs_hhi,_m11_dest_obs_hlo,_m11_dest_rec )$( [ "${M11_ENTRY_PROBE:-0}" = 1 ] && echo ,_m11_fe_get,_m11_fe_clear ) \
   -Wl,--initial-memory="$INITMEM" -Wl,--max-memory="$MAXMEM" 2> work/link.log || { tail -30 work/link.log; exit 1; }
 mv work/m11_boot.cjs.tmp work/m11_boot.cjs
 python3 m11_postjs.py work/m11_boot.cjs 2>/dev/null

--- a/tools/m11/m11_ov.c (fb3c40c3 → d19f47c4)
+++ b/tools/m11/m11_ov.c
@@ -779,7 +779,13 @@ unsigned long long function_43a3f0(unsigned long long s, unsigned long long valu
  * 1 段 deref を 2 箇所とも落とし, lengths (スタックアドレス) を配列長, a を配列本体として扱った.
  * → GetMem に巨大サイズが渡り 0 を返して Error(reOutOfMemory) → Halt0 (survey halt0 の 17 unit 直接原因, #130).
  * 逆アセンブル (417b70..417fa2) から転記. 動的配列ヘッダ: hdr = data-16, [hdr+4]=refcnt, [hdr+8]=length. */
+#if M11_ENTRY_PROBE
+extern volatile int m11_fe_417b70;
+#endif
 unsigned long long function_417b70(unsigned long long a, unsigned long long ti, unsigned long long dimcnt, unsigned long long lengths) {
+#if M11_ENTRY_PROBE
+    m11_fe_417b70 = 1;
+#endif
     u64 p = Q(a);
     u64 len = Q(lengths);
     if ((long long)len <= 0) {
```
- **§5 の判定 (HEAD `d19f47c4` 時点・文字列レベルの確認のみ)**: 既定 (`M11_ENTRY_PROBE=0`) での変化は次のとおり。(a) `CF` に `-DM11_ENTRY_PROBE=0` が増える (`#if` 偽のため C のコード生成は変わらない見込み)。(b) stamp 行の追加により、初回 build で ov.o が 1 回再コンパイルされる。(c) EXPORTED_FUNCTIONS の文字列は `M11_ENTRY_PROBE=0` では変わらない (追加部分が空に展開される)。object・IR・getmem の同一性は未確認で、再測定で確認する。
- 参考 (前回記録・本 run では未再現): 前 HEAD `69f3dd3b` で `repro_1701_rt_ov.sh 1` を再実行した記録は A=2012 / C=2008 / R0=2012 / O0=2008 / L0=2008 / R1=2008、全構成 IR md5 `baa100ff`・undefined symbol 0・870/24/0。所要 3 分 21 秒。
