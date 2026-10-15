# Fresh Air REPORT §11 付録 (#2739 / FA-34): Gain 以外の snap-in への差分実行の判定基準と振り分け

- 本体: [REPORT.md](REPORT.md) §11-2 ①。Gain の差分実行結果は [REPORT_APPENDIX_FA5.md](REPORT_APPENDIX_FA5.md) §A3・§A3-5。親: #52。
- 位置づけ: 判定基準 (§1) を実測より先に確定する。基準を当てた振り分け (§3) を残す。基準を変えるときは理由を書いて版を上げる (事後の変更はしない)。

## §1. 判定基準 (版 1・実測前に確定)

| 項目 | 基準 |
|---|---|
| C1 対象 | `ks_identity.py` の ID 一致 37 クラス。各クラスの `process_pair` (KH slot 14 と、SC の対応 slot の組) を 1 組とする |
| C2 除外 (stub) | `min(KH バイト数, SC バイト数) < 64` の組は process 比較の代表にしない |
| C3 両側ハーネス | 差分実行の対象は、SC 側の実機機械語ハーネス (`lift2/native/native_<x>.c`・`lift/native_gain.c`) と KH 側の登録 (`tools/targets/kilohearts/snapins/snapins.json` の key) の両方がある組だけ。両側が揃うまで「差分実行可」と書かない |
| C4 同一入力 | 同じ seed の乱数で case を生成し、両側へ同じ値を入れる (`ks_semantic_gain.c` の方式)。param の写像は機械語の読みで対応させたものに限り、根拠を書く |
| C5 判定 | 同一入力 N=200 case の L・R 出力と処理後 state の bit 一致。許容差は 0 (ulp 許容なし) |
| C6 読み | 200/200 一致 → 「この入力分布で bit 一致」まで。不一致 → bit 不一致の確定のみ。「意味が違う」とは断定しない (Gain の丸め形の差は §A3-5 のとおり、意味の違いと同じとは限らない) |
| C7 未実行 | C3 を満たさない組は実行しない。欠けている側のハーネスを理由に書く |

## §2. 振り分け規則

- `stub`: C2 に該当。
- `両側`: C3 を満たす。差分実行の対象。
- `SC のみ` / `KH のみ`: 片側だけのハーネスがある。欠けている側を書く (子 issue の対象は 1 PR あたり最大 3 件まで)。
- `なし`: 両側とも無い。判定はしない (#52 の残件として扱う)。

§3 の表は `tools/targets/freshair/ks_candidate_triage.py` が `ident.json` から機械的に作る。

## §3. 振り分け結果 (測定 commit `691ee7153`)

- 再現: `python3 tools/targets/freshair/ks_identity.py <HeartCore.core_64> <SlateCore.core_64> ident.json` → `python3 tools/targets/freshair/ks_candidate_triage.py ident.json` (素材 `work-liftlib-targets`)。
- 実測 (測定 commit `691ee7153`・素材 `work-liftlib-targets` を `$ARTIFACTS_DIR` から展開・nproc=4・load 1 分値 0.35): `ks_identity.py` 2.8 s・EXIT=0。`ks_candidate_triage.py` の出力は本節の表と **37 行一致** (表の行だけを diff して差分 0)。区分の内訳も一致。実装 run (`c3fef51c7`・2.9 s) では再生成した `ident.json` と表が byte 一致だった (当時の記録)。鮮度: `git diff 691ee7153 HEAD -- 'tools/targets/freshair/*.py' 'tools/targets/freshair/*.sh' 'tools/targets/freshair/lift/' 'tools/targets/freshair/lift2/' 'tools/targets/kilohearts/snapins/' 'tools/targets/kilohearts/scripts/'` の出力は 0 行 (以後の commit は本 REPORT のみ)。
- 振り分け表 (クラスは `ident.json` の `process_pair`。KH slot 14 と SC の対応 slot):

| クラス | KH VA | SC VA | KH B | SC B | ratio_M | 区分 | 欠けている側 |
|---|---|---|---|---|---|---|---|
| Bitcrush | 0x1802747a0 | 0x1806601b0 | 2092 | 1761 | 0.2297 | なし | SC と KH の両方 |
| Chorus | 0x18027fa70 | 0x1803df070 | 4039 | 907 | 0.1416 | なし | SC と KH の両方 |
| CombFilter | 0x1802899f0 | 0x1803df070 | 1187 | 907 | 0.2450 | なし | SC と KH の両方 |
| Compressor | 0x1802abc20 | 0x180775220 | 1724 | 1664 | 0.4358 | SC のみ | KH (snapins.json に key 無し) |
| Delay | 0x1802ed7f0 | 0x180ba8ad0 | 3291 | 2551 | 0.2027 | KH のみ | SC (実機機械語ハーネス無し) |
| Disperser | 0x180316480 | 0x180be1500 | 2311 | 3167 | 0.2256 | KH のみ | SC (実機機械語ハーネス無し) |
| Distortion | 0x1803295b0 | 0x1805b8290 | 4649 | 405 | 0.0795 | なし | SC と KH の両方 |
| Dualdelay | 0x18033b000 | 0x18086d1f0 | 3962 | 2969 | 0.1637 | なし | SC と KH の両方 |
| Dynamics | 0x18034f6e0 | 0x1808a4330 | 2093 | 2122 | 0.2528 | なし | SC と KH の両方 |
| Equalizer | 0x1803f1890 | 0x1806b1180 | 3293 | 2732 | 0.2075 | なし | SC と KH の両方 |
| Faturator | 0x180452f20 | 0x1803df070 | 3896 | 907 | 0.1574 | なし | SC と KH の両方 |
| Filter | 0x1804655e0 | 0x180b6f050 | 969 | 818 | 0.3351 | SC のみ | KH (snapins.json に key 無し) |
| Flanger | 0x18049bb50 | 0x180f7a600 | 6754 | 6368 | 0.1159 | なし | SC と KH の両方 |
| FrequencyShifter | 0x1804a6a20 | 0x1803df070 | 2776 | 907 | 0.1530 | なし | SC と KH の両方 |
| Gain | 0x1804b0380 | 0x180afe090 | 609 | 446 | 0.4753 | 両側 | - |
| Gate | 0x1804c2f50 | 0x1804ce700 | 1703 | 1599 | 0.2425 | KH のみ | SC (実機機械語ハーネス無し) |
| GraphicEq | 0x18037d210 | 0x180a59700 | 4413 | 3402 | 0.2613 | なし | SC と KH の両方 |
| Haas | 0x1804d0280 | 0x180498cd0 | 1175 | 981 | 0.3333 | KH のみ | SC (実機機械語ハーネス無し) |
| HostProxy | 0x180020660 | 0x180c201d0 | 41 | 67 | 0.7500 | stub | - |
| Ladder | 0x1804d9930 | 0x1803df070 | 620 | 907 | 0.2326 | なし | SC と KH の両方 |
| Limiter | 0x1804e8500 | 0x18094d9c0 | 1980 | 1588 | 0.3258 | KH のみ | SC (実機機械語ハーネス無し) |
| Micropass | 0x1807d8a60 | 0x1807f39b0 | 5155 | 3941 | 0.2491 | なし | SC と KH の両方 |
| Multipass | 0x1805488d0 | 0x180994f40 | 12209 | 4917 | 0.2727 | なし | SC と KH の両方 |
| PhaseDistortion | 0x18058fac0 | 0x180b373c0 | 10389 | 4693 | 0.0961 | なし | SC と KH の両方 |
| Phaser | 0x1807270d0 | 0x180a1bef0 | 2172 | 2208 | 0.3141 | KH のみ | SC (実機機械語ハーネス無し) |
| PitchShift | 0x1807328d0 | 0x18073a480 | 1202 | 1105 | 0.2739 | なし | SC と KH の両方 |
| QuickEq | 0x18035fb10 | 0x180ac5550 | 1754 | 2090 | 0.1870 | KH のみ | SC (実機機械語ハーネス無し) |
| Resonator | 0x180743390 | 0x1803df070 | 2020 | 907 | 0.1505 | KH のみ | SC (実機機械語ハーネス無し) |
| Reverb | 0x1807522d0 | 0x180e5c720 | 1843 | 1665 | 0.3118 | なし | SC と KH の両方 |
| Reverser | 0x18075c6d0 | 0x1807b0b40 | 1850 | 1566 | 0.2815 | なし | SC と KH の両方 |
| RingMod | 0x1807680b0 | 0x18050d730 | 1661 | 1485 | 0.2254 | なし | SC と KH の両方 |
| Stereo | 0x18080d4d0 | 0x1805ee2a0 | 1679 | 1117 | 0.3358 | KH のみ | SC (実機機械語ハーネス無し) |
| TapeStop | 0x180818bb0 | 0x180546270 | 9 | 9 | 1.0000 | stub | - |
| TranceGate | 0x18082fe30 | 0x1803df070 | 1147 | 907 | 0.2055 | なし | SC と KH の両方 |
| TransientShaper | 0x180841140 | 0x18057e150 | 3547 | 2274 | 0.3043 | なし | SC と KH の両方 |
| Unison | 0x18084dd90 | 0x1803df070 | 2684 | 907 | 0.1427 | なし | SC と KH の両方 |
| VocalFilter | 0x18085a730 | 0x1808e1f30 | 614 | 109 | 0.1951 | KH のみ | SC (実機機械語ハーネス無し) |

対象 37: KH のみ 10 / SC のみ 2 / stub 2 / なし 22 / 両側 1

表の注記 (表は機械出力のまま。注記は手書き):

- **SC VA `0x1803df070` (907 B) の 8 組** (Chorus・CombFilter・Faturator・FrequencyShifter・Ladder・Resonator・TranceGate・Unison) は、process の対応として成立しない。この VA は制御層から呼ばれる共有関数で、`lift2/build_ctl.sh` の ICALLS と `lift2/build_ctrl.sh` の `--icall` 一覧にも現れる。`ks_identity.py` は「命令数 3 以上の SC slot のうち M 比が最大の slot」を process_pair にするため、この共有関数が候補に選ばれた (ratio_M 0.14〜0.25)。この 8 組の SC 側 process は未特定で、判定基準 C1 の max-ratio 規則では対応が決まらない。規則を直すときは §1 の版を上げ、理由を書く。区分 (なし / KH のみ) はハーネスの有無だけで決まるので、§4 の結論は変わらない。
- **Gain 行**: 「§A3 で測定済み」は表の機械出力に無い手書きの注記。Gain の差分結果は [REPORT_APPENDIX_FA5.md](REPORT_APPENDIX_FA5.md) §A3 を参照。

## §4. 差分実行の結論 (C3 を満たす組)

- **両側 (差分実行できる組) は Gain だけ**。Gain の差分は既存の §A3 (同一 200 case で L/R/state の bit 一致 127/200)・§A3-5 (丸め形のモデル)・§A3-6 (機械語の ramp を KH 形に置換した native で 200/200、control は 127/200)。本付録での新規の差分実行は **0 件**。
- **SC のみ**: Compressor (0x180775220)・Filter (0x180b6f050)。SC 側の harness は動く (§5) が、KH 側の harness と snapins 登録が無いため差分は未実施。子 issue #3506 (Compressor)・#3507 (Filter)。
- **KH のみ** (10 組): Delay・Disperser・Gate・Haas・Limiter・Phaser・QuickEq・Resonator・Stereo・VocalFilter。KH 側の登録はあるが、SC 側の実機機械語ハーネスが無い。差分の対象外。起票先は #52 の残件。
- **なし** (22 組): 両側とも無い。判定しない (#52 の残件)。
- **stub** (2 組): TapeStop (9 B)・HostProxy (KH 41 B)。C2 により除外。

## §5. SC 側ハーネスの smoke (測定 commit `691ee7153`)

- 再現: `SC_CORE=<work-liftlib-targets の SlateCore.core_64> bash tools/targets/freshair/ks_sc_native_smoke.sh 20 [outdir]`。mlift の report から `iat_slots` を作り、同じ root・map・pokes で `native_comp` / `native_filter` を fma 0・1 で実行する。判定はしない。emsdk は不要 (`lift2/env.sh` は `/opt/emsdk` があるときだけ読む。`691ee7153` で修正。それ以前は emsdk の無い runner で無言に exit 1 した)。
- 実測 (測定 commit `691ee7153`・2 回実行、nproc=4、load 1 分値 0.24〜0.33。1 回目 9.51 s は lift2venv の作成を含む、2 回目 4.40 s。2 回の出力ファイルの md5 が一致、EXIT=0):

| ハーネス | fma | 行数 | ERR |
|---|---|---|---|
| Compressor (`native_comp.c`) | 0 | 20 | 0 |
| Compressor (`native_comp.c`) | 1 | 20 | 0 |
| Filter (`native_filter.c`) | 0 | 20 | 0 |
| Filter (`native_filter.c`) | 1 | 20 | 0 |

- 出力: 4 ファイル (`comp_n0`・`comp_n1`・`f_n0`・`f_n1`) の md5 は 2 回の実行で一致。fma 0 と fma 1 の出力も一致した (Compressor `af1c35e5aa66`・Filter `c6500f7db0e9`。このシナリオでは fma の違いが出力に現れていない。判定はしない)。stderr は 4 本とも 0 B。
- 注: 最初の試行では cwd に `pokes.txt` を置かずに実行し、Compressor が ERR 7/20 になった。`pokes.txt` (CRT 初期化の再現) を `FA_POKES` で渡すと ERR 0。smoke スクリプトは `FA_IAT`・`FA_POKES` を明示する。
- 限界: これは「SC 側の harness が実機機械語を実行できる」までの確認。出力の値が正しいこと (wasm・KH との一致) は未確認。

## §6. 受入条件への対応

- 受入 1 (判定基準の文書化): §1・§2 を実測より前に commit (`7e7b12f02`)。
- 受入 2 (ID 一致候補の差分実行、または実行できない理由): 新規の差分実行は 0 件。C3 を満たす組は Gain だけ。Compressor・Filter は SC 側だけ実行可能 (§5) で、KH 側 harness が無いことを理由に子 #3506・#3507 へ分けた。KH のみ 10 組・なし 22 組・stub 2 組は §4 に理由を書いた。
- 受入 3 (Gain 以外の判定を #52 に返す): Gain 以外は **未判定 (差分 0 件)**。#52 へ返す内容は §4・§7 の表。付録 [REPORT_APPENDIX_FA5.md](REPORT_APPENDIX_FA5.md) §A3-5 からも本節へ導線を置いた。

## §7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Compressor の KH 側 harness と同一入力の差分 (C4〜C6) | Compressor の意味同一性は未判定 | #3506 |
| Filter の KH 側 harness と同一入力の差分 (C4〜C6) | Filter の意味同一性は未判定 | #3507 |
| KH のみ 10 組の SC 側実機ハーネス (Delay・Disperser・Gate・Haas・Limiter・Phaser・QuickEq・Resonator・Stereo・VocalFilter) | 差分の対象が無い | #52 (残件) |
| なし 22 組 (両側とも無し) | 判定の対象外 | #52 (残件) |
| Gain の ramp 式 `(1-t)*a + t*b` がソースの意図か (§A3-6 の未解決。機械語の置換による 200/200 は §A3-6 で確認済み) | 「どちらが正しい式か」は未確定。Gain の判定の解釈に残る | #52 (残件) |
