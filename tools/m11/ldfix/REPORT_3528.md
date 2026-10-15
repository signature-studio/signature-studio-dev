# LD-160 (#3528): F3d 既定化前検証の残り — 55 関数の機械語・IR 突合と audit の HEAD / F3d 比較 (#2833 残)

既知類型との関係 (docs/DEFECTS.md): 該当なし。F3d (上流 `xor i64 0,0` の load 復元) の経緯は `REPORT_2660.md` §2.3・§9。

## 1. 結論

- F3d 対象 58 関数 (3 対象 45b170・45d0a0・45f560 を含む) を機械語と突合した。入口ブロックの `movzx word ptr [B]` の由来 argN と、IR の挿入 load (`%ldfxt*`) の argK が **58/58 で一致**した (`results/f3d_crosscheck_3528.tsv`)。確認できない関数は 0 で、既定化の除外対象は無い。
- negative control: 45b170 の挿入 load の argK を 2 から 1 に書き換えると、その 1 関数だけ NG になる (OK 57 / NG 1)。突合は誤りを検出できる。
- audit (`audit_lsf_ssa_e2e.sh`) は HEAD (`b706fb666`) と F3d の両方の `boot_final3.ll` で rc=0・7/7 完走した。7 step の出力は **HEAD と F3d で 1 行も違わない** (§3)。ただし audit の母集団 225 関数に入る F3d 対象は 4 関数だけで、残り 54 関数への影響は観測できない。
- **既定化しない**。`ldfix.py` の `if tag == 'f3d' and passes is None` の除外は残し、`ldfix.py` は変えない (§4)。
- 本 PR は production の IR 生成経路を変えない。

## 2. 突合 (機械語 ↔ IR)

方法: `tools/m11/ldfix/f3d_crosscheck_3528.py`。

- 対象: HEAD の `boot_final3.ll` と F3d 版 (`ldfix.py --passes f3d`) で本体が変わった関数。58 件で、`f3d.json` の `f3d_vas` と一致した。
- 機械語: 入口ブロック (IR の `dec_label_pc_<VA>` に割り当たる命令) の `movzx r16, word ptr [B]` のうち、disp 0・基底が rsp/rbp 以外のもの。基底 B の由来 argN は、guard (`fix_f3d` の `base_resolves_to_arg`) と別に、Win64 引数レジスタ (rcx=1・rdx=2・r8=3・r9=4) から reg→reg の mov と rbp/rsp の spill slot を経由して追跡した。他の命令で書かれた reg と call 後の揮発 reg は由来を失う。
- IR: 変更行の `%ldfxtN = load i16, ptr %argK` (`inttoptr` 経由を含む) の K。削除行は `xor i64 0,0` 1 行、挿入は load 1 本 (と zext) であること。
- 判定 OK: 機械語の該当 movzx がちょうど 1 本で、由来 argN = IR の argK。

| 判定 | 件数 | 内訳・注記 |
|---|---|---|
| OK | 58 | argK 1: 50 関数・argK 2: 5 関数・argK 3: 3 関数 |
| NG | 0 | — |

- argK 2 の 5 関数: 45b170・45b550・45bc90・45fb20・651b00。argK 3 の 3 関数: 45ff50・460ae0・4615f0。残り 50 関数は argK 1 (全件は TSV)。
- 3 対象は `REPORT_2660.md` §2.3 の結論と一致する (45b170 = arg2、45d0a0・45f560 = arg1)。
- 入口に movzx word が複数ある関数: 442b00 (3 本)・651b00 (4 本)。突合の対象は disp 0・非 frame 基底の 1 本だけで、残りは disp 付きか frame 基底のため対象外 (TSV の `mach_movzx_word_entry` 列)。

negative control (`f3d_crosscheck_3528.py` の判定が効くこと): F3d 版 IR の 45b170 の `ldfxt*_p = inttoptr i64 %arg2 to ptr` を `%arg1` に書き換えた IR を同じ式で与えた。結果は 45b170 のみ NG (`mach_argn` 2 ・ IR argK 1)、OK 57 / NG 1。

突合の範囲: 由来 argN と挿入 load の argK の一致までを見る。挿入 load の値と後段の比較 (`trunc i64 .. to i16` / `and`) の定数が機械語の比較定数と一致するかは見ていない。guard の IR 側条件 (`fix_f3d`) で確かめているのは「挿入先の xor が 1 本」まで。

## 3. audit: HEAD と F3d の比較

- HEAD: `b706fb666` の `work-m11` 素材の `boot_final3.ll` (sha256 `010451ad…`。main の `tools/m11/work/` と同一)。
- F3d: 同じ IR に `ldfix.py --passes f3d` を掛けた版 (58 関数・`f3d_fns`=58・`f3d_ambiguous`=21・`f3d_base_unresolved`=3・`f3d_arg_missing`=2)。
- 実行: `audit_lsf_ssa_e2e.sh` を前景で 2 回。HEAD 2 m 44.8 s (rc 0・7/7)・F3d 2 m 44.2 s (rc 0・7/7)。nproc 4。
- 差: 出力ログは HEAD と F3d で `diff` 0 行 (7 step とネガティブコントロール NC0〜NC7 を含む)。step 2 の `ssa.json` は 225 関数すべて同一。
- 母集団: `ssa.json` の 225 関数のうち F3d 対象は 4 関数 (45b170・45d0a0・45e3c0・45f560)。この 4 関数の record も変わらなかった。残り 54 関数は audit の母集団に無く、audit では観測できない。

HEAD の step 値 (本 run・`b706fb666` の素材):

| step | 主要値 |
|---|---|
| 1/7 `audit_lsf.py` | lsf 90 site / 解決不能 370 site / 169 関数 |
| 2/7 `audit_lsf_ssa.py` | alg1 26・alg2 38・alg3 77 関数 (alg1 ∪ alg2 = 41) |
| 3/7 `window_recount.py` | window_pairs 420・window_not_in_dataflow 0 |
| 4/7 `dyn_xcheck.py` | 既知 TRUE_DROP 8 関数: match 2・mismatch 3・unexec 3。解決不能 169 関数: match 25・mismatch 52・unexec 92 |
| 5/7 `tally_510.py` | store 宛 192 site: DROP 89 site / 51 関数・UNDETERMINED 2 site |
| 6/7 `negctl_510.sh` | NC0〜NC7 完走 |
| 7/7 `spill_classify_1161.py` | spill 宛 178 site: 確定 147・判定不能 30・未判定 1。TRUE_DROP 関数 32。`results/spill178_1161.tsv` と一致 |

注記: step 1〜5 の値は `REPORT_2660.md` §5 と一致する。step 7 だけは §5 の値 (109/28/41・TRUE_DROP 21) と違う。§5 は `4e85ea56` 時点の値で、現 main の `results/spill178_1161.tsv` は 147/30/1 であり、本 run の HEAD 側もこれに一致する。

## 4. 既定化の判断: しない

`REPORT_2660.md` §9.3 の見送り理由のうち、突合 (受入 1) と audit の比較 (受入 2) は本節で済んだ。残る理由で既定化を見送る。

1. 効果が観測できない。e2e (`REPORT_2660.md` §9.1) で F3d 適用 IR の到達 stage・survey・通過 unit・trap は HEAD と同一だった。audit も差 0 である。既定化しても観測できる改善が無いまま、58 関数の本番 IR を変えることになる。
2. audit の差 0 は、F3d 対象 54 関数に影響が無いことの証拠にならない (§3 の母集団)。
3. 既定化した状態を再測定していない。コミット済み HEAD で `m11_gen_ir2.sh` → `m11_e2e.sh` を既定の経路で実行していない (§9.1 は F3d を明示した実行)。
4. guard の negative control (効く入力での FAIL) は未測定。`REPORT_2660.md` §2.5 の入力では全ガードが効いていない。

既定化の判断を覆す条件: 1 の効果が観測されること、または既定化したコミット済み HEAD の e2e と 4 の negative control が揃うこと。どちらも本 run の範囲を超える。前提を持つ #2834 (LD-135) の扱いに関わるため PM に返す (§5)。

コード差分 (確認): `git diff b706fb666 HEAD -- tools/m11/ldfix/ldfix.py tools/m11/ldfix/audit_lsf_ssa_e2e.sh tools/m11/ldfix/results/drops_510.tsv tools/m11/ldfix/results/spill178_1161.tsv` は 0 行。本 PR の新規は `f3d_crosscheck_3528.py`・`REPORT_3528.md`・`results/f3d_crosscheck_3528.tsv` のみ。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 既定化の判断: 効果の実測・既定化したコミット済み HEAD の e2e 再測定・guard の効く入力の negative control・挿入 load の値と後段の比較定数の一致 | #2834 (LD-135) の前提「F3d を既定化すると判断したこと」が未成立。4 site の判定と results 更新は未着手 | #2834 へのコメント (前提は PM が決める) |
| 既定 e2e の pin (STRICT_DONE 56・SURVEY_OK_EXACT 872) と本 snapshot の不一致 (HEAD でも発生・`REPORT_2660.md` §9.1) | 既定 e2e が rc=1 で終わる (F3d の影響ではない) | #2834 へのコメント (本 issue の本文が「別途扱う」とした件の引継ぎ) |

## 6. 再現手順

1. F3d 版 IR: `python3 tools/m11/ldfix/ldfix.py tools/m11/work/boot_final3.ll $T/boot_final3.f3d.ll --pe $PE --passes f3d --report $T/f3d.json` (`f3d_fns`=58)。
2. 突合: `python3 tools/m11/ldfix/f3d_crosscheck_3528.py tools/m11/work/boot_final3.ll $T/boot_final3.f3d.ll --pe $PE --report $T/f3d.json > tools/m11/ldfix/results/f3d_crosscheck_3528.tsv` (OK 58 / NG 0)。
3. negative control: 45b170 の `ldfxt*_p = inttoptr i64 %arg2 to ptr` を `%arg1` に書き換えた IR を手順 2 と同じ式で与える (NG 1)。
4. audit: HEAD は `M11_WORK=tools/m11/work LD_WORK=tools/liftdiff/work bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh`。F3d は `M11_WORK` に `tools/m11/work/*` の symlink を並べ、`boot_final3.ll` だけを手順 1 の出力に差し替えた dir を渡す。`RUNNER_TEMP` を変えて出力先を分ける。
5. `PE` は `fl-win64` の `extracted/block00031_PE.bin`。`$T` は `$RUNNER_TEMP` 配下の作業用 dir。
