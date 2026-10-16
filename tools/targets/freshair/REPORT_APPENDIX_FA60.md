# Fresh Air REPORT 付録 (#4976 / FA-60): KH のみ snap-in 4 組の param offset→意味 (機械語の読み)

- 親: #4053 (FA-50)・#3740 (FA-44)。判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。前段: [REPORT_APPENDIX_FA44.md](REPORT_APPENDIX_FA44.md) §4。
- 位置づけ: 写像の根拠を機械語の読みで残す。差分実行 (C5・C6) はしない。製品 KPI は動かしていない (静的・機械語の読みのみ)。

## §1. 結論

| クラス | 写像の根拠 (機械語) | 結果 |
|---|---|---|
| QuickEq | §2 | 写像は機械語の読みで対応確認済み (表は逆アセンブルと一致)。**意味ラベル・呼出先の同一性は未確定**のため、4 組の受入条件は未達 |
| Delay | — | 未確定。KH 側 `this+0x3188` の読み出しを一部だけ確認。SC 側は P+0x9ee4・0x9f38・0x9f74・0x9fbc・0xa004 の 5 件 |
| Disperser | — | 未確定。KH 側の P 読み出しを自動抽出できず (§4)。SC 側は P+0x9bec・0x9dc4・0x9e0c・0x9e54 を確認 |
| Phaser | — | 未確定。KH 側 P+0xc・+0x10・+0x14 と SC 側 P+0x9dc4・0x9e18・0x9e54・0x9e9c・0x9ee4 を確認。対応づけは未了 |

**全 4 組の受入条件は未達** (部分達成。PR は `Refs #4976`)。QuickEq は写像の対応 (5 組) まで確認したが、意味ラベルと呼出先の同一性が未確定のため、受入の「確定」には届かない。Delay・Disperser・Phaser は §5 に残す。

## §2. QuickEq の写像 (確定できた範囲)

素材 `work-liftlib-targets` の `HeartCore.core_64` (KH) と `SlateCore.core_64` (SC) を capstone で逆アセンブルし (`disasm.py`)、再現スクリプト `ks_fa60_quickeq_map.sh` で行の存在を検査した。

| 側 | P の取得 | 読み出し | 渡し先 (同一の設計関数呼出の引数) |
|---|---|---|---|
| KH `0x18035fb10` | `mov rax,[rdx+0x3188]` | P+0 → `[rsp+0x20]`・P+4 → `[rsp+0x28]`・P+8 (`movd`) → `[rsp+0x30]` | `call 0x180362700` |
| KH | 同上 | P+0xc → `xmm2`・P+0x10 → `xmm3` | 同上 |
| SC `0x180ac5550` | `mov rax,[rcx+0x90]` | 0x9dc4 → `[rsp+0x20]`・0x9e0c → `[rsp+0x28]`・0x9e54 → `[rsp+0x30]` | `call 0x180ad5ce0` |
| SC | 同上 | 0x9e9c → `xmm2`・0x9ee4 → `xmm3` | 同上 |

- 対応 (機械語の読みで確認済み): KH P+0 ⇄ SC 0x9dc4、KH P+4 ⇄ SC 0x9e0c、KH P+8 ⇄ SC 0x9e54、KH P+0xc ⇄ SC 0x9e9c、KH P+0x10 ⇄ SC 0x9ee4。
- 確認の仕方: 5 組それぞれについて「P の load → 同じ引数 slot (`[rsp+0x20]`/`[rsp+0x28]`/`[rsp+0x30]`) か xmm2/xmm3 への渡し → 同じ `call`」の連鎖を `ks_fa60_quickeq_map.sh` が順に検査する。途中で base (`rax`) と渡す register、slot が書き換わらないことも見る。
- 過去の食い違い (解消済み): 旧スクリプトは SC 0x9dc4 の直後の `movss [rsp+0x30], xmm1` だけを見ており、0x9e54 の load を見ていなかった。その行は 0x9e54 の load に対応するもので、0x9dc4 の読みではない (表は正しい)。スクリプトを 5 組の連鎖検査に直した (§3)。
- 限界: 呼出先 (`0x180362700` と `0x180ad5ce0`) が同じ関数かは未確認。引数の対応だけを確定した。P+8 と 0x9e54 は KH が整数 (`movd`)、SC が float (`movss` を経由) として読むので、型の一致は未確認。
- 意味ラベル (周波数の下端・上端、Q、フラグ) は引数の並びからの推定で、機械語だけでは確定していない。SC の 0x9dc4 は float として渡し、Phaser の読み (`mov ebp,[rcx+0x9dc4]`) では int として使うため、型は関数ごとに違う可能性がある。
- 差分実行 (C4・C5) は未実施。

## §3. 検証 (測定 commit と再現)

- 再現: `bash tools/targets/freshair/ks_fa60_quickeq_map.sh` (素材 `work-liftlib-targets` を展開したもの)。
- 測定 commit: `9b329513c` (`ks_fa60_quickeq_map.sh` を 5 組の連鎖検査に直した最後の commit)。この commit の上に REPORT の更新だけを積む。
- 再現: `bash tools/targets/freshair/ks_fa60_quickeq_map.sh` (素材 `work-liftlib-targets` を展開したもの。`tar --zstd -xf` で `tools/targets/kilohearts/work/winpkg/HeartCore.core_64` と `tools/targets/freshair/work/win` を展開)。
- 実測 (commit `9b329513c`・素材あり・`work/fa60/run_9b329513c.txt`): real 17.288 s・user 16.669 s・EXIT=0。load 1 分値 0.53 (14:17 時点)。出力:

```
OK KH P+0: load 18035fbcc (xmm4) -> [rsp+0x20] @18035fbf1 -> call 0x180362700 @18035fc04
OK KH P+4: load 18035fbd0 (xmm5) -> [rsp+0x28] @18035fbeb -> call 0x180362700 @18035fc04
OK KH P+8: load 18035fbc7 (xmm1) -> [rsp+0x30] @18035fbe5 -> call 0x180362700 @18035fc04
OK KH P+0xc: load 18035fbda (xmm2) -> xmm2 @18035fbda -> call 0x180362700 @18035fc04
OK KH P+0x10: load 18035fbd5 (xmm3) -> xmm3 @18035fbd5 -> call 0x180362700 @18035fc04
OK SC 0x9dc4: load 180ac55fd (xmm1) -> [rsp+0x20] @180ac560b -> call 0x180ad5ce0 @180ac5611
OK SC 0x9e0c: load 180ac55df (xmm0) -> [rsp+0x28] @180ac5605 -> call 0x180ad5ce0 @180ac5611
OK SC 0x9e54: load 180ac55d7 (xmm1) -> [rsp+0x30] @180ac55f7 -> call 0x180ad5ce0 @180ac5611
OK SC 0x9e9c: load 180ac55ef (xmm2) -> xmm2 @180ac55ef -> call 0x180ad5ce0 @180ac5611
OK SC 0x9ee4: load 180ac55e7 (xmm3) -> xmm3 @180ac55e7 -> call 0x180ad5ce0 @180ac5611
OK: QuickEq 写像 5 組の機械語の連鎖を確認 (意味ラベル・呼出先の同一性は未確認)
EXIT=0
```

- 旧 (commit `53bb7ce63` のスクリプト・部分検査) の出力は `OK: 部分検査のみ ...`、EXIT=0 だった。新しいスクリプトの判定とは別物なので、写像の根拠には旧出力を使わない。
- 鮮度: `git diff 9b329513c HEAD -- tools/targets/freshair/*.sh tools/targets/freshair/*.py` の出力は 0 行 (REPORT の更新のみ)。
- Delay・Disperser・Phaser の逆アセンブルは `work/fa60/` (gitignore) に出した。判定には使っていない。

## §4. 未確定の理由 (残り 3 組)

- **Delay**: process `0x1802ed7f0` (KH) と `0x180ba8ad0` (SC) は長い (KH 3291 B・SC 2551 B)。KH 側は P を `[rdx+0x3188]` と `[rbx+0x3198]` (`0x3198` は別の state) から読むため、P の読み出しを全部追うには時間が足りなかった。
- **Disperser**: KH 側 `0x180316480` の P 読み出しを、単純な抽出では拾えなかった (P が `[rbx+0x3188]` を経由して保持される)。手で追う必要がある。
- **Phaser**: KH 側 P+0xc・+0x10・+0x14 は読まれているが、SC 側の 0x9dc4〜0x9ee4 との呼出先の対応が未確定。

## §5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| QuickEq の意味ラベル (周波数下端・上端・Q・フラグ) と呼出先 (`0x180362700`・`0x180ad5ce0`) の同一性 (写像の対応は確認済み) | 差分の param 写像の意味が未確定 | #4976 (Refs・残件) |
| Delay の param 写像 (KH P 読み出しの全件確定) | 差分実行の前提が無い | #4976 (Refs・残件)。同一 scope の #4977 (残件 B) とも重なるため、起票はしていない |
| Disperser の param 写像 | 差分実行の前提が無い | #4976 (Refs・残件) |
| Phaser の param 写像 (KH P+0xc〜0x14 と SC 側の対応) | 差分実行の前提が無い | #4976 (Refs・残件) |

- 子 issue は起票していない: 同じ残件の issue が既にあり (#4977 `[FA-61] ... 残件 B`・#4978 `[FA-60] ... SC 側 process 特定: Resonator (#4047 残件)`)、重複を避けた。

# Fresh Air REPORT 付録 (#4978 / FA-60): KH Resonator process の SC 側対応 (呼出元と vtable の照合)

- 親: #4047 (FA-49)。前段: [REPORT_APPENDIX_FA45.md](REPORT_APPENDIX_FA45.md) §4 (未特定)・[REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §3 (共有関数 0x1803df070 の注記)。
- 判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。本付録は差分判定をしない (対応の特定だけ)。

## §1. 結論

- **SC 側の process VA は特定できなかった。** KH Resonator process `0x180743390` (373 命令・2020 B・外部 call 2 回) に対応する SC の関数は、vtable・呼出元・全関数の総当たりのいずれでも見つからなかった。
- 受入条件 (「特定できなければ、理由を REPORT に書く」) の分岐で満たす。理由は §4。
- 機械で候補にできる最大値は SC `ResonatorDsp` slot 12 `0x180624b80` (373 命令・ratio_M 0.0402)。命令数だけ一致し、構造は一致しない。対応とは判定しない。

## §2. 測定 (commit `728090329`)

- 測定 commit: `728090329` (`tools/targets/freshair/ks_resonator_fa60.py` を追加した最後の commit。本 PR はこの commit の上に REPORT と DOC_MAP を足す)。
- 再現: `python3 tools/targets/freshair/ks_resonator_fa60.py <HeartCore.core_64> <SlateCore.core_64> out.json` (素材 `work-liftlib-targets`。`tar --zstd -xf` で `tools/targets/freshair/work/win` と `tools/targets/kilohearts/work/winpkg/HeartCore.core_64` だけ展開)。
- 実測 (commit `728090329` の状態で実行): `real 21.014 s`・`user 21.449 s`・EXIT=0。load 1 分値 0.49 (13:48 時点)。同じ内容のスクリプトを commit 前にも 1 回実行し、`result.json` の md5 は一致 (`99331b2b8d17`)。
- 前提の再確認: `ks_identity.py` の全体実行 (`main`) は 2.99 s・EXIT=0 (測定 commit 前の HEAD で再現)。
- 鮮度: `git diff 728090329 HEAD -- tools/targets/freshair/ tools/targets/kilohearts/snapins/ tools/targets/kilohearts/scripts/` の出力は本 PR の REPORT・DOC_MAP 以外の `.py`/`.sh` 変更を含まないこと (下記 §5)。

## §3. 照合の結果

(a) SC `ResonatorDsp` vtable (`0x1810d8588`・17 slot) の各関数と KH process の M 列比 (`ks_identity.py` の `norm` を使用。命令数 3 以上の slot)。

| SC slot | SC VA | 命令 | B | ratio_M | 共有定数数 |
|---|---|---|---|---|---|
| 0 | 0x1806249d0 | 35 | 131 | 0.1078 | 1 |
| 3 | 0x1803e01a0 | 10 | 38 | 0.0313 | 3 |
| 4 | 0x1806252e0 | 57 | 222 | 0.0884 | 3 |
| 5 | 0x1803df070 | 225 | 907 | 0.1505 | 3 |
| 8 | 0x180624ad0 | 10 | 35 | 0.0522 | 0 |
| 10 | 0x180460e60 | 14 | 51 | 0.0620 | 0 |
| 11 | 0x180624b00 | 35 | 126 | 0.0588 | 1 |
| 12 | 0x180624b80 | 373 | 1759 | 0.0402 | 3 |
| 13 | 0x180625290 | 16 | 75 | 0.0566 | 2 |
| 15 | 0x180625260 | 6 | 36 | 0.0317 | 4 |

- 最大は slot 5 (0.1505) で、§FA45 §4・2739 §3 の制御層の共有関数 `0x1803df070` と同じ。Resonator の process ではない。
- slot 12 は命令数が一致するが、構造は一致しない (呼出先が `0x180624a60` と `0x18103fd60`。KH process は同じ `0x180fbc1f4` を 2 回呼ぶ)。
- 共有定数 (`.rdata` の参照先 8 B と即値) の積集合は全 slot で 0〜4 件。KH process の定数集合は 43 件。

(b) SC 全関数 (`.pdata`・300〜3000 B・22,527 関数の開始点) の総当たり M 列比 (上位 10)。

| ratio_M | SC VA | 命令 | B |
|---|---|---|---|
| 0.2930 | 0x180e5c720 | 330 | 1665 |
| 0.2688 | 0x18002a9d0 | 133 | 590 |
| 0.2651 | 0x1803df850 | 223 | 954 |
| 0.2577 | 0x1802d1740 | 178 | 809 |
| 0.2554 | 0x180d30910 | 230 | 923 |
| 0.2518 | 0x18010c2c0 | 191 | 979 |
| 0.2500 | 0x180d0fa90 | 123 | 493 |
| 0.2484 | 0x1800b1640 | 247 | 1234 |
| 0.2482 | 0x180558840 | 175 | 725 |
| 0.2445 | 0x1802dc680 | 126 | 626 |

- 上位はすべて ratio_M 0.29 以下。`0x180e5c720` は Reverb の SC 側 process (2739 §3 の表) で、Resonator ではない。全候補の上位で一致と言える閾値 (例: 0.8 以上) を超えるものは無い。

(c) SC の Resonator 関連 vtable (`ResonatorDsp`・`ResonatorDspModel`・`ResonatorController`・`UIResonator` ほか) の slot を参照する関数 (RIP 相対・即値)。

| 参照される slot | 参照元の件数 | 補足 |
|---|---|---|
| 0x1803b4070 | 177 | 多くの vtable が共有する関数。対応の根拠にならない |
| 0x1803df050 | 51 | 参照元が多い共有関数。対応の根拠にならない |
| 0x1803df070 (slot 5) | 1 (0x1803df580) | 参照元は 1 件だけ。Resonator の process を呼ぶ経路とは断定できない |
| 0x180c90f00・0x180c93ba0・0x180d196a0 ほか | 1〜7 件 | 他 snapin と共有 |

- `ResonatorController` (`0x1810d9248`・KH 側は 20 slot) と `UIResonator` (`0x1810d9350`) の参照元は、SC 側で 2 件・1 件 (それぞれ `0x180636670`・`0x180636740`・`0x180636a70`)。これらはコントローラ/UI の関数で、DSP の process ではない。

## §4. 特定できなかった理由

1. **候補の不在**: SC 全関数の総当たりで、KH process と M 列比 0.3 以上の関数が無い (最大 0.2930)。命令列の構造が KH 側と別物。
2. **vtable 上の対応が無い**: KH `ResonatorDsp` の slot 14 (process) に対応する SC の slot を決められない。SC の `ResonatorDsp` slot 12 は命令数だけ一致し、構造は一致しない (§3 (a))。
3. **共有関数の混入**: vtable の最大 M 比 slot (5) は制御層の共有関数で、`ks_identity.py` の max-ratio 規則では対応を決められない (2739 §3 と同じ問題)。
4. **呼出元の照合の限界**: SC の参照元は RIP 相対・即値の検出に限る。関数ポインタ経由の間接呼出 (vtable 経由の呼出) は検出していない。これを追うには、呼出規約と vtable の位置を静的に読む作業が要る (本 run の時間内に未実施)。

結論: 機械的な照合では対応を確定できない。特定には、SC の `ResonatorDsp` の vtable 構築経路を読む (手作業の静的読み) が必要。

## §5. 本付録の範囲

- 追加: `tools/targets/freshair/ks_resonator_fa60.py` (測定ツール)・本付録・DOC_MAP の登録。
- 本付録は、既存の判定基準 (2739 §1) の対象外。差分実行は行わない (C3 の SC 側ハーネスが無い)。

## §6. 受入条件への対応

- 受入 (SC 側の process VA を特定。特定できなければ理由を REPORT に書く): **特定は未達**。理由 (§4) を REPORT に書いた。受入条件の分岐を満たす。

## §6b. 追加照合 (commit `ce6400502`・#4978 2 回目 run)

- 測定 commit: `ce6400502` (`ks_resonator_fa60.py` に (d) 呼出先の r 列照合を追加した commit)。
- 実測: `python3 tools/targets/freshair/ks_resonator_fa60.py <HeartCore.core_64> <SlateCore.core_64> out.json`・`real 38.432 s`・`user 38.826 s`・EXIT=0・load 1 分値 0.40 (15:22 時点)。
- 結果の要点:
  - vtable 数: KH `ResonatorDsp` 20 slot、SC 17 slot。slot 番号の対応は決められない (前回の「KH slot 14 = process」は、SC 側に対応する slot が無いため未確定)。
  - SC `ResonatorDsp` slot 14 は共有スタブ `0x1803b4070` (`ret` のみ)。
  - (d) は KH process の呼出先ごと (`for t in cal`) に r 列 (数値を潰した比較) を SC 全関数 (100〜3000 B) と照合する。process 本体 `0x180743390` の r 列は (d) の対象外で、比較していない。
  - 呼出先 `0x180fbc1f4` (52 命令・238 B) の SC 側最良候補は `0x181048180` (53 命令・r 列比 0.5905)。この関数は `ecx` による分岐のあるピッチ変換で、呼出先の構造と一致しない。対応とは判定しない。
  - process 本体 (0x180743390) の r 列は照合していない。そのため process 本体の SC 側対応は、r 列の観点では未確定のまま。
  - (d) の全出力は本ファイルに貼っていない。(d) を再実行するには `HeartCore.core_64` / `SlateCore.core_64` が要るが、現在の素材 (`fl-win64`) には含まれない。
- 鮮度: `git diff ce6400502 HEAD -- tools/targets/freshair/ks_resonator_fa60.py` の差分は docstring の 1 行 (「3 つ」→「4 つ」と (d) の説明) だけで、測定に使うコードは不変。測定 commit の結果は有効。

## §7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SC `ResonatorDsp` の vtable 構築経路を静的に読み、KH process の SC 側対応を確定する | Resonator の差分 (C4〜C6) の前提が無い | #4047 (FA-49・親) |
| Resonator の SC 側実機ハーネス作成 | 同上 (C3 の SC 側) | #4980 (FA-67・#4047 残件) |

## §8. 関数ポインタ表 0x1810d7430 の reader 特定 (#5694 / FA-80・親 #5682・#5628)

- 測定 commit: `51664ee93` (`ks_vtable_reader.py` の近傍集計を含む最後のコード commit)。
- 素材: `work-liftlib-targets` の `SlateCore.core_64` (36,285,952 B、`tools/targets/freshair/work/win/Fresh Air/`)。
- 実測: `python3 tools/targets/freshair/ks_vtable_reader.py <SlateCore.core_64> 0x1810d7430 0x1810d7340`・EXIT=0・`real 52.75 s`・`user 52.64 s`・load 1 分値 0.78 (測定前 0.50)。
- 表 = vtable A (`0x1810d7340`) の `+0xf0` (slot 30)。検索形式ごとの結果:
  - 絶対値 qword (`0x1810d7430`)・RVA dword (`0x10d7430`)・vtable 絶対値・即値・disp の絶対値・rip 相対 ea: **0 件** (表を直接指す参照は無い)。
  - rip 相対 `lea` で vtable を指すもの (vptr 設定): 3 件。`0x1805ede78` (ctor `0x1805ede50`)・`0x1805edf5a` (`0x1805edf50`)・`0x1805edfba` (`0x1805edfb0`)。いずれも ea = `0x1810d7340` (vtable A の先頭)。
  - vtable A を設定する ctor の呼出元: `0x1805caef1` (`call 0x1805ede50`) のみ。
  - `[reg+0xf0]` の読み: 3,090 件 (any base)。うち間接 `call`/`jmp`: 56 件。`0x1805ede50`・`0x1805edf50`・`0x1805edfb0` の内部には `[reg+0xf0]` の間接 call は無い (`0x1805edf1f` の `mov dword ptr [rsi+0xf0], 0x3f800000` は書込み)。
  - 表近傍 `±0x200` の rip 相対参照 51 件 (`lea` 9・`movsd` 14・`mulsd` 14・`addsd` 3・`movss` 8・`maxss` 2・`addss` 1)。`lea` 9 件の ea は `0x1810d7290`・`0x1810d7258`・`0x1810d72c8`・`0x1810d7340`・`0x1810d73d0`・`0x1810d7478`・`0x1810d7580` で、表 `0x1810d7430` 本体は指さない。浮動小数の読みも表 `0x1810d7430` の値ではない (ea は `…7460`・`…7468` 等の別スロット)。
- 結論: 表 `0x1810d7430` を**直接**読む reader は、rip 相対・即値・基底+添字の静的形では 0 件で特定できない。読み手は vptr (`this` の vtable 経由) による `[reg+0xf0]` の間接 call/load のみ。reader の関数名は、呼出元が vptr の型 (オブジェクト) に依存するため、静的だけでは確定しない。
- 限界: `[reg+0xf0]` 3,090 件のうち、どの object の vtable を読んでいるかは未追跡 (型推定なし)。`mov reg,[reg+0xf0]` の直後の `call reg` は (逐次 4 命令以内) 0 件。
- 未解決 (起票先): vptr の型推定 (どのオブジェクトが vtable A を持つか) → #5628 (FA-78) の実行順測定に渡す。
