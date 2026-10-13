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
