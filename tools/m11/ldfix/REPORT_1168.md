# #1168 (LD-36) D17 修復 pass 続き: 複数 load の CELL_COLLAPSED 調査 (部分達成)

**判定: 未達 (調査のみ)**。修復 pass は未実装。受入条件 1〜3 は未達、4 は未実施。PR は `Refs #1168`。
実装は子 issue `[LD-47]` に分割 (親: #1168)。

前提: `REPORT_968.md` §4。単一 load 規則 (`fix_d17.py`) の対象外の 28 関数 / 53 site。

## 1. 再現 (`audit_lsf_ssa.py`, work-m11 のみ)

- 測定 commit: `916d9932` (`tools/m11` のコードを最後に変えた commit。以降の変更は docs のみ)
  - 訂正 (LD-47 review, §4 参照): 上記の「`tools/m11` のコードを最後に変えた commit」と「以降は docs のみ」は誤り。`tools/m11` の非 md 変更は `916d9932..12586095` に 18 件ある。`tools/m11` のコードを最後に変えた commit は `02e2c5a2` (`12586095` の祖先)。本 §1 の実測の基準は §4 の測定 commit `12586095` とする。
- 素材: `[WORK-M11]` (`docs/REFERENCES.md` §1。取得指定 `oc_artifacts: work-m11`、展開先 `tools/m11/work/`)
- 鮮度の証跡 (`git diff 916d9932 HEAD -- tools/m11`、`*.md` を除く): 空 = コード差分 0 (`git diff 916d9932 HEAD --name-only -- tools/m11` の結果は `*.md` のみ)
  - 訂正 (LD-47 review): 上記の証跡は誤り。`916d9932` 以降の `tools/m11` 非 md 差分は 0 件ではない。鮮度の正本判定は §4 の e2e 経路 (3 ファイル) の差分 0 を参照。

- cfg は glob をクォートして渡す (`'../work/boot*.drc.config.json'`)。クォートしないと `boot0` 1 本だけになり、
  集計が `lsf_sites_arg 29` になる (誤り)。クォートすると `90 / 370 / 169` となり、REPORT_968 の修復前と一致する。
- 修復前の store 宛 CELL_COLLAPSED 関数は 49、うち K を読む IR load が 1 本の 21 関数を除く 28 関数が対象。

## 2. 対応付けの調査結果

対象 28 関数 (K 単位で 32 組。IR load が 1 本だけの K は除く) の対応付けを検討した。本節には数値を書かない。K ごとの本数の比較は §5 (deref 連鎖の数え方) が唯一の正本。

- 機械側の rip 参照には、load 以外 (store 先・アドレス計算) も含まれる。そのため本数の差だけでは対応を決められない。
- 同じ K を読む load が同一関数内に複数あり、かつ型 (`load ptr` / `load i32`) が混在する例がある (`e53810`, K=`0x11e0120`: `load ptr` 1 本と `load i32` 1 本)。型だけでは一意に決まらない。
- `11d47c0` (K=`0x11e0120`) は IR load 2 本が同一型 (`load i32`) で、機械側の site 2 本 (`mov dword ptr [rax], ecx`) も同型。順序で対応させる根拠はあるが、本数が一致する他の関数で検証していない。

結論: 機械語 site と IR load の対応は本数・型・幅だけでは決まらない。対応規則は、機械側の**値の流れ** (rip セル → レジスタ → store 先) を追う必要がある。
単純な順序対応を入れると、誤った load を `%cellp` 経由に書き換えて silent miscompile を起こすおそれがあるため、本 run では規則を書かない。

## 3. 次の作業 (子 issue `[LD-47]`)

- 機械語 site ごとに「rip セル → 読んだレジスタ → 使う load」の連鎖を追い、load と site を 1 対 1 で結ぶ。
- 結べた load だけを `fix_d17.py` の拡張で修復。結べない load は触らない。
- ネガコン (修復を外すと store 宛 CELL_COLLAPSED が戻る) を追加。
- 検証: `audit_lsf_ssa.py` の store 宛 CELL_COLLAPSED の減少、`emcc -c` の構文検証。
- 受入条件 2 (CELL_COLLAPSED 0) は、上記の対応付けがすべて結べた場合にだけ達成可能。結べない site が残れば、その時点で数を報告する。

## 4. LD-47 (#1375) 実測: 現 HEAD での基準値と訂正 (2026-10-14)

測定 commit: `12586095` (前回 fix run で測定。`tools/m11` の非 md 差分は `12586095` から `70d02dba` まで 0 件)。

- 訂正: §3 の「修復前 53 site」は誤り。`REPORT_968.md` §2 の表では 53 は**修復後**の値。現 HEAD の修復前は store 宛 CELL_COLLAPSED **86 site / 49 関数**。
- 訂正: §1 の鮮度記述「`916d9932` 以降はドキュメントのみ」は誤り。`git diff --name-only 916d9932 HEAD -- tools/m11` の非 md は **18 件**、`git diff --numstat 916d9932 HEAD -- tools/m11` の非 md は **+698 / -27** (本節の旧記載「51 件・988 行」は誤り。LD-47 review で計測し直した)。`tools/m11` のコードを最後に変えた commit は `02e2c5a2` (`12586095` の祖先)。
- 訂正: §1 の「空 = コード差分 0」の証跡も誤り。測定 commit `12586095` から本 PR の HEAD までの `tools/m11` の非 md 差分は 0 件ではない (件数は HEAD ごとに変わるため本文に書かない。`git diff --name-only 12586095 HEAD -- tools/m11 | grep -v '\.md$'` で再計算する)。e2e の経路 (`fix_d17_e2e.sh`・`audit_lsf_ssa.py`・`fix_d17.py`) はこの範囲で変更なし (`git diff --quiet 12586095 HEAD -- <3 files>` が 0)。`m11_build.sh`・`m11_gen_ir2.sh`・`ldfix.py` 等は e2e スクリプトから呼ばれない。上記の再現は測定 commit `12586095` の tools/m11 で行った。

e2e (`bash tools/m11/ldfix/fix_d17_e2e.sh`、foreground、31 秒、emcc rc=0。測定 commit `12586095`):

| 項目 | 修復前 | 修復後 (fix_d17.py) |
|---|--:|--:|
| store 宛 CELL_COLLAPSED site | 86 | 53 |
| store 宛 CELL_COLLAPSED 関数 | 49 | 28 |
| store 宛 CELL_DEEP site | 19 | 52 |
| spill 宛 CELL_COLLAPSED site | 37 | 37 |
| alg3 flagged 関数 | 77 | 58 |
| 修復した関数 / cell | — | 24 / 29 |

- 再現: K を読む IR load が複数本の K 組は 28 関数・32 K 組 (issue の 28 関数 / 32 組と一致)。この 28 関数に含まれる store 宛 CELL_COLLAPSED は修復前で 56 site。
- 1:1 規則は未実装。ネガコンも未実装 (対象の修復関数が無いため)。受入条件 1・3 は未達。受入条件 4 (emcc 構文検証) は `fix_d17.py` の修復 IR (単一 load 規則のみ) に対して通過を確認した。
- 残作業: 機械語 site ごとの rip セル → レジスタ → load の連鎖追跡 (未着手)。issue #1375 のまま継続する。

再測定 (PR #1539 fix run、2026-10-14、HEAD `70d02dba` + 本 commit の REPORT のみ差分。コードは `12586095` と同一):
素材 `[WORK-M11]` と `[EMSDK]` を展開 (`$ARTIFACTS_DIR` に配置済み。`tools/m11/work/` に展開)。`bash tools/m11/ldfix/fix_d17_e2e.sh` を foreground で実行: 31 秒、emcc rc=0、load 0.37→0.68。
出力 JSON (`$RUNNER_TEMP/fix_d17_e2e/ssa_{base,fix}.json`) から数えた値は上表と一致: 修復前 store CC site 86 / 関数 49、store CELL_DEEP 19、spill CC 37 → 修復後 store CC 53 / 関数 28、store CELL_DEEP 52、spill CC 37。alg3 flagged 77 → 58。

## 5. LD-47 (#1375) 対応付けの調査: 1:1 規則は未実装 (部分達成)

測定 commit: `7fc1088f` (origin/main)。以降の `tools/m11` のコード差分は、`tools/m11/ldfix/survey_d17_multiload.py` の追加と、main 取り込み由来の `tools/m11/trap_triage/probe1507_listB.mjs` の 2 件。

- 素材: `[WORK-M11]` を `tools/m11/work/` に展開。ツールチェーンは `[EMSDK]` (`docs/REFERENCES.md`)。
- e2e: `bash tools/m11/ldfix/fix_d17_e2e.sh` (foreground、emcc rc=0)。測定値は §4 を参照。

調査 (`survey_d17_multiload.py`、foreground、rc=0): 複数 load の K 組 32 のうち、dec_label_pc ブロック単位で「IR の K 読み出し本数 = 機械語の rip セル → deref 連鎖の本数」が一致したのは **8 組**。
- 不一致 24 組の例: `100a3d0` K=`11e35c8` IR 5 / 機械 8、`128f9e0` K=`11e26a0` IR 14 / 機械 5、`ff63f0` K=`11e14a0` IR 15 / 機械 16。
- ブロック一致 8 組 (`126bdb0`/`11e3550`、`128ade0`/`11e0390` など) も、同一ブロック内の load の順序は本数だけでは決まらない。

結論: 機械語 site と IR load の 1:1 対応は、本数・型・ブロックのどれでも安全に決められない。誤った load を `%cellp` 経由に書き換えると silent miscompile になるため、規則は入れていない。受入条件 1 (1:1 規則の実装)・3 (ネガコン) は未達。受入条件 2 (store 宛 CELL_COLLAPSED の減少) も、本 run の修復 pass は単一 load 規則のみのため、§4 の残 site 数のまま。

次の作業 (#1375 で継続): 機械語側で rip セル → レジスタ → 後続 store/load の値の流れを命令単位で追う (`ldmach.py` 系の既存追跡を流用できるか要調査)。結べた load だけを修復し、結べない site 数を報告する。

## 6. #1740 (LD-61) 1:1 対応付け pass `link_d17.py` (部分達成)

測定 commit: `543e7320` (`tools/m11/ldfix/link_d17.py` と `link_d17_e2e.sh` を追加した commit。e2e は 2 回とも同値)。
再現: `bash tools/m11/ldfix/link_d17_e2e.sh` (foreground、26 秒、load 0.09、emcc rc=0)。素材 `[WORK-M11]` は `M11_WORK` で指定。

規則 (ブロック単位・順序に依らない): 機械語の `mov rA,[rip+X]` の直後 3 命令以内に rA を基底にした `mov rD,[rA]` (disp 0) があり、
rA を壊す命令・分岐・call が挟まらず、rD が後続で読まれる chain を、同じ dec_label ブロック内の IR K 読み出し load と結ぶ。
結ぶのは「ブロック内の IR load がちょうど 1 本・chain がちょうど 1 本・幅一致」のときだけ。それ以外は触らない。

| 項目 | 値 |
|---|--:|
| 複数 load の K 組 (IR 2 本以上) | 32 |
| 複数 load の IR load 総数 | 151 |
| 1:1 で結べた load | 11 (K 組 9 / 関数 9) |
| 結べない load | 140 |

e2e の実測 (store 宛 CELL_COLLAPSED):

| 段階 | site | 関数 | CELL_DEEP site | alg3 flagged |
|---|--:|--:|--:|--:|
| 修復前 | 86 | 49 | 19 | 77 |
| fix_d17 のみ (ネガコン) | 53 | 28 | 52 | 58 |
| fix_d17 + link_d17 | 47 | 26 | 58 | 54 |

`emcc -c` (fix + link 後の IR) rc=0。ネガコンは link を外した段階 (53 / 28) で、修復を外すと 86 / 49 に戻る。

結べなかった内訳 (理由の凡例: `multi_in_block` = 同ブロック IR load 2 本以上、`mach_only` = IR 側に load が無い chain、
`ir_only` = chain が無い IR load、`width_or_chain` = 幅が合わない・chain が途中で壊れる・rD が使われない):

| 関数 | K | IR load | 機械 chain | 結べた | 結べない (理由) |
|---|---|--:|--:|--:|---|
| 100a3d0 | 11e35c8 | 5 | 9 | 0 | mach_only 1, multi_in_block 5 |
| 1046780 | 11e4018 | 3 | 3 | 0 | width_or_chain 3 |
| 1046a30 | 11e31a8 | 2 | 4 | 0 | mach_only 1, multi_in_block 2 |
| 11c8d20 | 11e09f8 | 2 | 9 | 0 | mach_only 7, multi_in_block 2 |
| 11c90f0 | 11e3f38 | 3 | 4 | 0 | mach_only 1, multi_in_block 3 |
| 11ca870 | 11e1cd8 | 6 | 10 | 0 | mach_only 4, multi_in_block 5, width_or_chain 1 |
| 11d44b0 | 11e4628 | 4 | 17 | 1 | mach_only 13, width_or_chain 3 |
| 11d47c0 | 11e0120 | 2 | 3 | 2 | mach_only 1 |
| 11d47c0 | 11e4628 | 13 | 14 | 0 | mach_only 1, multi_in_block 2, width_or_chain 11 |
| 11d4df0 | 11e2eb8 | 5 | 6 | 0 | multi_in_block 2, width_or_chain 3 |
| 11e79d0 | 11e3550 | 5 | 6 | 1 | mach_only 1, multi_in_block 3, width_or_chain 1 |
| 126bdb0 | 11e1cd8 | 4 | 5 | 0 | mach_only 1, multi_in_block 3, width_or_chain 1 |
| 126bdb0 | 11e3550 | 3 | 3 | 1 | width_or_chain 2 |
| 1280530 | 11dfda8 | 7 | 7 | 1 | multi_in_block 4, width_or_chain 2 |
| 128ade0 | 11e0390 | 2 | 2 | 2 | - |
| 128c320 | 11e0ff8 | 3 | 3 | 0 | multi_in_block 2, width_or_chain 1 |
| 128f9e0 | 11e26a0 | 14 | 17 | 0 | ir_only 1, mach_only 1, multi_in_block 9, width_or_chain 4 |
| 12af5c0 | 11e3140 | 3 | 3 | 0 | multi_in_block 3 |
| 12c92e0 | 11e4018 | 3 | 4 | 0 | mach_only 1, multi_in_block 3 |
| 12d6920 | 11e0b20 | 2 | 2 | 1 | width_or_chain 1 |
| 1365660 | 11e13a8 | 2 | 2 | 0 | multi_in_block 2 |
| 1365660 | 11e1c70 | 4 | 6 | 0 | mach_only 2, multi_in_block 3, width_or_chain 1 |
| d0cee0 | 11e4080 | 11 | 13 | 0 | mach_only 2, multi_in_block 3, width_or_chain 8 |
| d28b00 | 11e3aa0 | 2 | 3 | 1 | multi_in_block 1 |
| dc0f70 | 11e4018 | 2 | 3 | 0 | multi_in_block 2 |
| dc1440 | 11e4018 | 3 | 4 | 0 | multi_in_block 2, width_or_chain 1 |
| e2a8a0 | 11e27f0 | 2 | 3 | 0 | multi_in_block 2 |
| e53810 | 11e0120 | 2 | 4 | 0 | mach_only 2, width_or_chain 2 |
| e5af90 | 11e4018 | 2 | 2 | 0 | multi_in_block 2 |
| e814c0 | 11e09f8 | 2 | 3 | 1 | mach_only 1, width_or_chain 1 |
| ff63f0 | 11e0ff8 | 13 | 13 | 0 | multi_in_block 13 |
| ff63f0 | 11e14a0 | 15 | 16 | 0 | multi_in_block 14, width_or_chain 1 |

注: 結べた 11 件は形 (ブロック内 1 対 1・幅一致) で結んだもので、実行時の値の一致は検証していない (emcc 構文検証と store 宛の減少のみ)。
`ff63f0` / `128f9e0` / `d0cee0` のように 1 ブロックに IR load が多い例は、ブロック内の順序を機械語の値の流れで追う必要があり、本 pass の範囲外。

残作業 (未解決): 結べない 140 load (K 組 32 のうち 9 組だけが一部結べた)。ブロック内に IR load が複数ある場合の順序対応は、機械語の `rD` の後続使用先まで追う拡張が要る。子 issue 起票先は PR 本文の未解決表。

## 7. #1923 (LD-69) 同一ブロック複数 load の使用種類による対応付け (結べた数は増えず)

測定 commit: `5a654b99` (`tools/m11/ldfix/link_d17.py` を変えた commit)。
再現: `bash tools/m11/ldfix/link_d17_e2e.sh` (foreground、48 秒、load 0.28、emcc rc=0)。素材 `[WORK-M11]` `[EMSDK]` 展開済み。

追加した規則: 同一ブロックの IR load (1 本以上) と chain (1 本以上) が同数で、
IR 側 = load 値の最初の使用命令 (`store` / `add` / `sub` / `and` / `or` / `xor` / `icmp` / `zext` / `sext`)、
機械側 = rD の最初の使用命令 (`mov [mem],rD` → `store`、`add` → `add` など) が両側で**重複なく一意**、
かつ種類の集合が一致し、種類ごとの幅が一致するときだけ結ぶ。それ以外は結ばない。
機械側の追跡窓は従来どおり (rD の後続 8 命令)。

結果: 結べた数は 11 のまま (`by_use_kind` = 0)。ネガコン・emcc の結果も §6 と同一。

| 段階 | site | 関数 | CELL_DEEP site | alg3 flagged |
|---|--:|--:|--:|--:|
| 修復前 | 86 | 49 | 19 | 77 |
| fix_d17 のみ (ネガコン) | 53 | 28 | 52 | 58 |
| fix_d17 + link_d17 (§6 と同じ) | 47 | 26 | 58 | 54 |

理由 (`ff63f0` K=`11e14a0`、`100a3d0` K=`11e35c8`、`128f9e0` K=`11e26a0` を確認):
- IR 側は同一ブロックの load の最初の使用種類が揃う例が多い (`ff63f0` は 11 本中 10 本が `add`、`100a3d0` は全 5 本が `sext`)。種類では一意にならない。
- 機械側は chain の多くが `dst_unused` (rD の使用先が後続 8 命令の外) か `base_clobbered` (rA が途中で壊れる)。窓を広げると誤結合のおそれがあるため広げていない。

結べない load 数 (関数・K 単位) は §6 の表がそのまま正 (今回の変更で変化なし)。残作業は子 issue へ (PR 本文の未解決表を参照)。受入条件のうち「値の流れで順序を決める」「store 宛 CELL_COLLAPSED の減少」は未達。
