# LIFTLIB-5 (#342) 付録 E — tan / tanf bit-exact・SVF 未達 (REPORT §23 の本文)

> REPORT.md §23 から分割移動 (内容は削除していない)。節番号 §23.x は本体と同一。結論は [`REPORT.md`](REPORT.md) §23。


- 既知類型との関係: 該当なし (DEFECTS.md D1a〜D16 未登録。新類型行案は §23.7)
- 検証起点 commit: `14d5bc8` (コミット済み HEAD を ws-342 worktree で実行。以降の commit は REPORT のみ)

### 23.1 結論
| leaf (leafspec 40 scenario) | LIFTLIB-4 | LIFTLIB-5 |
|---|---|---|
| tan 1801a9be0 | 11/40 | **40/40** (mismatch 0 / crash 0) |
| tanf 1801ba860 (spec 新設) | — | **40/40** |
| SVF reset 180126040 | 2/40 + crash 8 + trap 1 | **20/40** + crash 7 + mismatch 13 + trap 2 (**未達**) |
| cvt 1801bc890 | 11/40 + crash 23 + trap 6 | 26/40 + crash 14 + mismatch 0 + trap 0 |
| exp / log | 40/40 / 32/40 + crash 8 | 不変 |

tan / tanf は `expect_match_min: 1.0` で gate 化した。SVF は未達のため gate 無し。

### 23.2 原因と修復 (tan)
1. **call の def 範囲** (`mc.py`): call は VOLATILE 全部を def にしていたため、callee が書かない `r10` (入口 sign) が call を跨ぐと bind 不能。callee 機械語の書込集合 (推移閉包) に絞る (`LL_NO_CALLEE_PRESERVE`)。
2. **領域の多定義 bind** (`p1.py`): 領域は D からしか入らないが、生存側 S だけが書く def も候補に入れて復元不能になっていた。領域に流れる def に限定 (`LL_NO_REGION_DEFS`)。
3. **setcc の i1** (`p1.py`): `xor r,r ; setcc r8` の結果が i1 で GPR bind に使えなかった。setcc と**同一の機械語 block** の直前 8 命令内に同 reg の 32bit 以上のゼロ化 (`xor r,r`) がある時のみ `zext i1 → i64` で復元 (`LL_NO_SETCC_I1`)。block を跨ぐ・8/16bit の xor は信用しない (§23.7)。
4. **合流点 dead reg** (`p1.py`): 合流で live でない reg が束縛不能でも領域全体を捨てていた。dead なら合成せず捨てる (`LL_NO_DEAD_JOIN`)。
5. **GPR rsp spill/reload** (`p1.py`): `mov [rsp+k], r64` / 逆を領域内で扱う (`LL_NO_GPR_SPILL`)。reload は領域内の**全 pred 経路**で store 済みの slot に限る (§23.7)。現行の ott_leaf closure では一度も使われない (§23.4)。
6. **ret / RX の複製 call** (`leafabi.py`): p1 が call を複製すると単一 SSA が ret を支配しない。全複製の戻りを alloca (i128) に store し ret/RX 前で load (`LL_NO_RET_PHI`)。RX は call 後の xmm0 読み手を全て差し替える (`LL_NO_RX_ALL`)。
7. すべて `mc.LEAF_EXT` (leaf cfg のみ ON) の内側。FA/KH/OTT 既定は不変 (§23.4)。

### 23.3 ハーネス修正 (SVF/cvt の測定が変わった理由)
`native_runner.c` / `wasm_runner.mjs` は MS x64 ABI の引数レジスタを「gpr/xmm 独立カウント (SysV 的)」で割り当てていた。MS x64 は**位置**で決まる (第 N 引数 = rcx/rdx/r8/r9 か xmm0..3 の N 番目)。`(this, float, float)` の 2 つ目の float が xmm0 に入り xmm2 が 0 になっていたので、位置対応に直した。これで SVF 2/40 → 20/40、cvt 11/40 → 26/40 (trap 6 → 0)。`diff.py` に `ret_bits` を追加 (f32 戻りは下位 32bit のみ比較)。

### 23.4 ネガティブコントロール (tan leafspec 一致数, 各 switch を 1 つだけ止めた実測)
| switch | tan | 判定 |
|---|---|---|
| (全 ON) | 40/40 | — |
| `LL_NO_CALLEE_PRESERVE=1` | 11/40 | 効いている |
| `LL_NO_REGION_DEFS=1` | 11/40 | 効いている |
| `LL_NO_SETCC_I1=1` | 11/40 | 効いている |
| `LL_NO_DEAD_JOIN=1` | 11/40 | 効いている |
| `LL_NO_RET_PHI=1` | emcc 失敗 (does not dominate) | 効いている |
| `LL_NO_GPR_SPILL=1` | 40/40 | tan 不要。**SVF も 20/40 + mismatch 13 + trap 2 + crash 7 で不変**、全 leaf の一致数も不変。出力 `ott_leaf_fixed.ll` が全 ON と byte 一致 (md5 `8e5f6a76…`) = 現行 closure では語彙が一度も使われない |
| `LL_NO_RX_ALL=1` | 40/40 | tan 不要。**SVF は 20/40 + mismatch 13 + trap 2 + crash 7 で不変**、全 leaf の一致数も不変。IR は 1 site 差 (`rx_threaded` 32→31 / `rx_nodomin` 2→1) |

### 23.5 検証 (実測)
`bash tools/liftlib/liftlib_e2e.sh` (コミット済み HEAD `448a6d89`、nproc=4、2026-10-13): **ALL PASS / real 5m19.813s (319.8 s) / 開始 load 0.35 → 終了 load 1.03, 0.82, 0.44**。unit T1〜T22 **ALL UNIT TESTS PASS** (T17b は `LL_XRET_*` 未設定で skip)・FA 400/400・KH 366/366・OTT checks 8/0・`--auto none` 系 PASS・SIMD 205 mnemonic mismatch 0・注入 94/94 (偽陽性 0)。leafspec は §23.1 の表と同一 (tan 40 / tanf 40 / exp 40 / log 32+crash 8 / SVF 20+mismatch 13+trap 2+crash 7 / cvt 26+crash 14)。
- 検証 HEAD `448a6d89` は `d7da2d2` merge 後の SR-4 対応 commit。`pefile` / `capstone` は runner に未導入だったため `python3 -m pip install pefile capstone numpy` で入れてから実行 (初回の空振りは import 失敗で即 FAIL・副作用なし)。
- SR-4 pilot (`tools/targets/serum2/sr4/`) は本 run で素材 `plugins-serum2` が取得されていないため**未実測**。代わりに、位置対応を leaf spec (`abi: ms_pos`) に限定し、SR-4 の既定経路 (独立カウンタ) はコード上 main と同一 (`M pos` 行なしの分岐は main の旧コードそのもの) にした。SR-4 の再測定は素材取得後に別途行う。
- 旧実測 (`7e00ff2`、real 2m21.641s) より長い。`7e00ff2`→`14d5bc8` は main の merge (iargs T16 ほか) と §23.7 の修正を含む。T16 単体は `REPORT_APPENDIX.md` §17 に 123.4 s と記録済み (推定: 差分の主因)。
- 前提: `work-liftlib` の tarball 内 symlink が `<WORK_ROOT>/webstudio/...` (`<WORK_ROOT>` = 旧 worktree 配置の作業ルート) の絶対パス。`<WORK_ROOT>/webstudio → ws-342` の symlink が無いと `regress` の OTT が `FileExistsError` (`os.path.exists` は dangling symlink で False)。`REPORT_APPENDIX_B.md` §15.3 と同件。
- 経過: LEAF_EXT 導入前は OTT 既定で emcc 失敗 + T15 が 15→14 でずれたため、拡張を leaf cfg に限定した。

### 23.5a SR-4 回帰対応 (PR 差し戻し 1)
位置対応 (MS x64 の第 N 引数 = xmm N / gpr N) を全 spec の既定にしていたため、main の SR-4 pilot (K 番目の float → xmm K の独立カウンタ前提) の経路が変わり得た。対応: シナリオ先頭の `M pos` 行 (spec `"abi": "ms_pos"`) で位置対応をオプトインし、既定 (行なし) は main と同じ独立カウンタ。leaf 6 spec (tan/tanf/exp/log/svf/cvt) のみ `ms_pos`。SR-4 spec・pilots.tsv は無変更。
- 根拠: `native_runner.c` / `wasm_runner.mjs` の既定分岐は main の旧コードと同一。leaf 6 spec の一致数は §23.5 の実測と同じ。

### 23.6 未解決 (起票先)
| 未解決 | 起票先 |
|---|---|
| SVF 20/40: mismatch 13 + trap 2 + crash 7。`this+0x10/0x14/0x18` (tanf 結果 `%18` を読む addss/mulss) の xmm0 差し替えが RetDec の insn.addr ずれで一部効かない | #342 (Refs で継続) |
| cvt: 26/40 + crash 14 (CRT 経路 `jmp *rax`) | #256 系 (leaf native CRT 経路) |

### 23.8 SVF 追補 (#342 継続): reader 索引のずれ修正 (LEAF_EXT 内)
- 原因: `_rx_thread` は 1 call の全 xmm0 読み手に 1 つの `Binder` (`FuncIndex` の `(bi, li)`) を使っていた。前の読み手で `zext` 行を挿入すると後続の行位置がずれ、後続の読み手が 1 行前の別命令 (例: 0x180126092 の `addss` が `store` 行を指す) に差し替えていた。
- 修正: 読み手ごとに `Binder` を作り直す (`leaf_ext("REINDEX")`、ablation `LL_NO_REINDEX=1`)。
- 実測 (SVF 180126040, `leafspec --n 40 --only svf`): 修正前 match 20 / mismatch 13 → **修正後 match 24 / mismatch 9** (native_crash 7・wasm_trap 2 不変)。読み手対応は 0x180126092→`%30 = addss`, 0x180126096→`%31 = mulss`, 0x1801260a7→`%38`, 0x1801260b0→`%43` で機械語と一致。
- 残 mismatch 9: `this[0..3]` (0x180126080 の store = tanf 戻りの直接 store) と `this[16..18]`。**40/40 は未達**。残因は未特定 (tanf 戻りの上位 bit / store 幅の扱いの候補。次の調査対象)。
- 検証: コード HEAD `a6d181f4` / PR head `5a2dcbc2` (`5a2dcbc2` は docs のみで、検証対象のコードは `a6d181f4` と同一)。`bash tools/liftlib/liftlib_e2e.sh` = **ALL PASS / rc 0 / real 396 s / 終了直後 load 1.05, 0.97, 0.67** (nproc=4、開始時 load は未計測)。素材 tarball 内の絶対 symlink は run 限りで張り替えて解決し、永続化しない。unit ALL PASS・FA 400/400・KH 366/366・OTT checks 8/0・注入 94/94・exp 40 / tan 40 / tanf 40 / log 32+crash 8 / cvt 26+crash 14 不変。

### 23.7 レビュー指摘への対応 (Copilot 2 件 + oc-reviewer)
| 指摘 | 対応 | 確認 |
|---|---|---|
| `leafabi._ret_thread`: `fresh` を phi 分岐が定義前に呼ぶ | `fresh(va, base)` をループ前に束縛。`_rx_one` の phi load 名 (L313 同型) は衝突検査を block 内 → 関数全体へ | T19。修正前コード (`3dd3438`) では `UnboundLocalError` を再現、修正後は PASS |
| `p1._setcc_value`: 後方走査が block 境界を跨ぐ | setcc と同一の機械語 block 内に限定。あわせて 8/16bit の `xor` は上位 bit を消さないので除外 | T20 (合成機械語 3 形: 同一 block=復元 / 別 block=拒否 / 8bit xor=拒否)。修正前は別 block も復元 |
| `p1._rsp_gpr` reload (L927 同型): 領域全体の「store 済み」集合で判定 = 片経路の store を全経路と誤認 | `st["__gw"]` に載せ、合流で全 pred の交わりを取る | 現行 closure では未使用 (§23.4)。出力 IR は修正前後で byte 一致 |
| 検証が head と不一致 / 相互参照 §15→§23 | §23.5 を最終 head で再実測。PR 本文の参照を §23.4 / §23.6 に修正 | §23.5 |
| 未測定の switch | SVF で on/off を実測 | §23.4 |

修正前後で `work/ott_leaf/ott_leaf_fixed.ll` の md5 は同一 (`8e5f6a76…`)、leafspec 一致数も同一 (tan 40 / tanf 40 / exp 40 / log 32+crash 8 / SVF 20 / cvt 26)。上記 3 件は**現行 closure の出力を変えない潜在バグの封じ込め**。

DEFECTS.md 行案 (編集は PM 判断):

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|---|
| D17 (案) | ours (p1) | 新規 (潜在) | `xor r,r ; … ; setcc r8` の上位 56bit=0 を block 境界越しに推定し, setcc を通らない経路で `zext i1→i64` が不定上位 bit を持つ | 機械語の後方走査が基本ブロックを無視 | 実 leaf では未発現 (tan の xor は同一 block)。合成機械語で再現 (T20-B) | setcc の def 復元で xor が同一 block に無い | 同一 block・32bit 以上の xor に限定 |

### 23.9 tanf 大引数の不一致 (#1087 / LIFTLIB-13) — 原因の切り分け (未修正)
- **入力**: `work/1087/tanf_wide.json` (gitignore 領域。spec `vars[0].gen` を `unif[-1e12,1e12]` に広げ、`mix` は既定 0.6/0.2/0.2 のまま)。spec 本体 (`specs/ott_leaf_tanf.json`) は無変更。
- **実測 (コード HEAD `8e077944` = origin/main)**: `leafspec` 40 scenario で **match 33 / mismatch 7 / native_crash 0 / wasm_trap 0**、gate FAIL (rate 0.825)。既定 spec 込みの `targets/ott_leaf.json` 全 6 spec 実行では tanf 40/40・SVF 24/40 (mismatch 9 / crash 7 / trap 2) で、#342 時点の 20/40 から §23.8 の修正後の値と一致 (再現済み)。
- **不一致の形**: 7 件すべて |x| ≥ 1e11。wasm の戻りは **±150725.0 (0x48133140 系) の定数に張り付き**、native は `tan(x)` と一致する (例: x=1.9119e11 → native −25.9959 / wasm 150725.0)。|x| ≤ 8.4e6 の 33 件は全件一致。
- **機械語の分岐 (capstone, `OTT_vst2_win64.dll`)**: tanf `0x1801ba860` の閾値は `|x|` ≤ π/4 (fast path), `|x|` < 2^-13 (poly), `|x|` < 2^23 (`cvttpd2dq` による中間還元 `0x1801ba955`〜)。**`|x|` ≥ 2^23 は Payne-Hanek 還元 (`0x1801ba9c8`〜、128bit テーブル積・`bsr`・`shr`・`cmp rcx,0`・`jae`/`jl`/`je`)** に入る。大引数の 7 件はここを通る。
- **IR の該当箇所 (`function_1801ba860`, `ott_leaf_w_fixed.ll`)**: Payne-Hanek の分岐条件が機械語のフラグに対応していない。`jae 0x1801baa70` (shr 後の CF) は `br i1 true`、その後の `jcc` は `br i1 false` / `br i1 undef` に畳まれ、負号・丸めの側の分岐が脱落する。`bsr` と `cmp rcx,0` の ZF/SF も IR のどの比較にも結線されていない (`bsr`・`shr` のフラグは helper・p1 のどちらにも無い)。
- **#1087 本文の仮説 (`cvttpd2dq` の INT32_MIN 規約) との関係**: 大引数で通るのは `cvttpd2dq` の分岐ではなく Payne-Hanek 分岐。`x86_cvtt_f2i32` 単体の誤りは支持されない。
- **SVF への波及 (未確定)**: SVF 残 mismatch 9 の `this[0..3]` は tanf 戻りの直接 store。tanf の大引数不一致が SVF の残差を説明するかは未検証 (SVF 側の引数は別計算のため、tanf の `x` を再計算して突合する必要がある)。
- **未解決 (起票先)**: flag-folding (`bsr` / `shr` / `cmp` の CF・ZF・SF を分岐に再結線する) の修正と、修正後の tanf wide 40/40 + SVF 再測定 → 子 issue (下記 §23.9 の起票先)。

### 23.10 LIFTLIB-17 (#1330) — Payne-Hanek 分岐のフラグ流れ (機械語側の確定)
- **素材**: `OTT_vst2_win64.dll` (`$HOME/analysis/plugins/ott/binaries/`)、IR は `tools/liftlib/work/ott_lb10000/ott_lift.ll` (line 12060 付近)。コードは未変更 (解析のみ・e2e 未実施)。
- **機械語 (capstone 逆アセンブル、`0x1801ba9c8`〜`0x1801bab26`)**: フラグを消費する命令と、その直前の定義を VA 順に示す。

  | VA | 命令 | 定義元 (フラグ) | 消費 |
  |---|---|---|---|
  | `0x1801baa3a`〜 | `mul rcx` → `add r10,rax` | (mul の CF/OF) | — |
  | `0x1801baa4a`〜`0x1801baa50` | `sub rcx,r11` / `shr rax,cl` | `shr` の CF (最後に押し出された bit) | `0x1801baa53` `jae 0x1801baa70` |
  | `0x1801baa70` | `adc rax,0` | CF (上の `jae` とは別の CF 読み) | — |
  | `0x1801baa90` | `bsr rcx,r10` | `bsr` の ZF (src==0 で ZF=1) | `0x1801baa94` `jne 0x1801baab0` |
  | `0x1801baab7` | `cmp rcx,0` | `cmp` (SF/ZF/CF) | `0x1801baabb` `jl 0x1801baae0` / `0x1801baabd` `je 0x1801bab00` |

- **p1 の処理 (`tools/liftlib/liftlib/passes/p1.py`)**:
  - `shr` reg,imm の handler (line 1455-1466) は値だけ更新し `st["fl"] = None` にする。`shr rax,cl` (レジスタ shift) は handler に入らず、フラグは前段の状態のまま残る。
  - `bsr` は p1 に handler が無く (grep で一致なし)、ZF を追跡しない。
  - `flag_consumers` (line 73) は `defs_before(va,"flags") == {A}` (comis 起点) の jcc だけを拾う。したがって `jae` / `jne` / `jl` / `je` はいずれも comis 由来ではないため、分岐の再構成 (dropped/folded 経路) の対象外になっている。
- **IR との対応 (VA 順からの推定・未検証)**: `dec_label_pc_1801ba9c8` の `br i1 true` が `jae 0x1801baa70` に、`dec_label_pc_1801baa70` の `br i1 false` が `jne 0x1801baab0` に、`dec_label_pc_1801baab0` の `br i1 false` が `jl 0x1801baae0` に、`dec_label_pc_1801baabd` の `br i1 undef` が `je 0x1801bab00` に当たると読める。どの値が畳まれたかは IR の `%` 定義を追うまで確定しない。
- **修正の方向 (案)**: p1 に整数 flag 生成 (`shr` reg,cl の CF / `bsr` の ZF / `cmp rcx,0` の SF・ZF) を追加し、上の 4 分岐を `icmp` で再結線する。これは comis 起点の `p1` 経路とは別の経路になる。実装と測定は子 issue に分ける。

### 23.11 残作業 (起票先)
- 整数フラグ再結線 (`shr`/`bsr`/`cmp` の flag 追跡 + 4 分岐の再結線) の実装 → #1687 (LIFTLIB-18)。
- 修正後の `leafspec` tanf wide 40/40、SVF 180126040 の `--n 40` 再測定、`liftlib_e2e.sh` ALL PASS → #1687。

### 23.12 LIFTLIB-18 (#1687) — 修正前の実測 (ベースライン・未修正)
- **測定 commit**: `4ed14f65` (main)。`git diff 4ed14f65 origin/main -- tools/liftlib` = 0 行 (同一コード)。
- **素材**: `work-m6-ott` / `work-liftlib` / `work-icall` / `work-liftlib-targets` / `analysis-ott-binaries` / `toolchain-*` を展開 (`$ARTIFACTS_DIR`)。
- **IR の現状** (`ott_leaf_fixed.ll`・`function_1801ba860`): `br i1 true` (jae 0x1801baa53) / `br i1 false` (jne 0x1801baa94) / `br i1 false` (jl 0x1801baabb) / `br i1 undef` (je 0x1801baabd)。4 分岐すべてが畳まれたまま。
- **p1 の未対応 (機械語)**: `shr rax,cl` (レジスタ count) / `bsr` / `adc rax,0` / `cmp rcx,0` は p1 に flag 生成の handler が無い。`bts`・`btr`・`mul`・`not`・`movd xmm4` 等も同じ block にある。
- **leafspec 実測** (`targets/ott_leaf.json --n 40`、16.4 s、開始 load 1.54 / 終了 1.49):

  | spec | match | mismatch | native_crash | wasm_trap |
  |---|---|---|---|---|
  | exp | 40 | 0 | 0 | 0 |
  | log | 32 | 0 | 8 | 0 |
  | tan | 40 | 0 | 0 | 0 |
  | tanf (既定) | 40 | 0 | 0 | 0 |
  | svf (180126040) | 24 | 9 | 7 | 2 |
  | cvt | 26 | 0 | 14 | 0 |

- **tanf wide** (`unif[-1e12,1e12]`、spec の `mix` は既定どおり、`work/1687/` の gitignore 領域): **match 15 / mismatch 25 / native_crash 0 / wasm_trap 0** (gate FAIL、目標 40/40)。§23.9 の 33/40 (8e077944) とは値が違う。原因は未切り分け (spec の seed/生成の差の候補)。
- 既定経路 (tan / tanf / exp の既定 spec) は本ベースラインで不変。修正の対象は整数 flag 経路のみ。

### 23.13 LIFTLIB-19 (#1709) — 再現と原因の切り分け (コード未変更)
- **測定 commit**: `09723d9e` (origin/main 時点)。`git diff 09723d9e HEAD -- tools/liftlib` は本 PR の REPORT 追記のみ。
- **素材**: `work-m6-ott` / `work-liftlib` / `analysis-ott-binaries` / `toolchain-*` を展開。`tools/*/work` は gitignore のため、検証 worktree には本体からコピーして使用 (本体の work は未変更)。
- **再現 (leafspec `--n 40`、real 13.996 s = 1 回目の実測)**:
  - tanf wide (`mix` 第 1 枝のみ `unif[-1e12,1e12]`): **match 15 / mismatch 25 / native_crash 0 / wasm_trap 0** → §23.12 と一致 (ベースライン再現)。
  - 既定 spec `ott_leaf_tanf`: **match 40 / mismatch 0** (不変)。
  - 注: `gen` 全体を `unif[-1e12,1e12]` に置換すると 0/40 になる。mix の |x| 小域 (既定 spec の 40% 近傍) が落ち、比較対象が無くなるため。第 1 枝だけを広げること。
- **不一致の形**: wasm の戻りは全件 `0x48133140` / `0xc8133140` (±150725.0) に張り付く。
- **原因の切り分け (RetDec raw `.ll` の段階)**: `tools/m6/work/ott.drc.ll` の `function_1801ba860` (raw line 123/132/138/141 ほか) では、Payne-Hanek の 4 分岐が既に `br i1 true` / `false` / `false` / `undef` に畳まれている。raw IR に `shr`・`bsr`・`adc`・`mul` の `__asm_` 呼び出しは 1 件も残っておらず (`and` / `icmp` / `udiv` に展開済み)、整数 flag の材料が p1 の入力に無い。
- **p1 の現状**: `cmp reg,imm/reg` は `("int", ...)` flag として扱えるが、`shr reg,cl`・`bsr`・`adc` の flag 生成は無い (`liftlib/passes/p1.py` line 1455-1466 は値のみ)。
- **結論**: 修正は「p1 に flag 生成を足す」だけでは完結しない。RetDec raw から失われた整数 flag を機械語 (`0x1801baa3a`〜`0x1801bab26`) から復元する入口が要る。受入条件 (40/40・SVF・e2e) は未達。
- **起票先**: 下記 §23.14。

### 23.14 残作業 (起票先)
- 整数 flag の復元 (機械語 `0x1801baa3a`〜`0x1801bab26` の `shr cl` / `bsr` / `adc` / `cmp rcx,0` の CF/ZF/SF を p1 に追加し、RetDec raw で畳まれた 4 分岐を `icmp` で再結線する) → #1948 (LIFTLIB-20・親 #1709)。
- 受入条件 (tanf wide 40/40・SVF `--n 40` 再測定・`liftlib_e2e.sh` ALL PASS) → #1948 で扱う。
- 親 #1709 は #1948 完了まで open のまま (本 PR は `Refs #1709` のみ。`Closes` は付けない)。
