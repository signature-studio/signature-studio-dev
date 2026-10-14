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
- **HEAD での再測定は未実施**: 本 fix の時点でローカルに `toolchain-emsdk`・`toolchain-retdec`・`work-m11` が無い (`fl-win64` のみ)。素材が要るため、再測定の依頼は `oc_artifacts: fl-win64 work-m11 toolchain-emsdk toolchain-retdec` 指定で行う。§1 の数値は測定 commit `fb3c40c3` の値であり、HEAD の値ではない。
- 参考 (前回記録・本 run では未再現): 前 HEAD `69f3dd3b` で `repro_1701_rt_ov.sh 1` を再実行した記録は A=2012 / C=2008 / R0=2012 / O0=2008 / L0=2008 / R1=2008、全構成 IR md5 `baa100ff`・undefined symbol 0・870/24/0。所要 3 分 21 秒。
