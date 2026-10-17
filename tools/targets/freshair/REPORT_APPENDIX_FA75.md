# Fresh Air REPORT 付録 (#5451 / FA-75): KH のみ snap-in Delay の param offset→意味 (機械語の読み)

- 親: #4976 (FA-60)。前段: [REPORT_APPENDIX_FA60.md](REPORT_APPENDIX_FA60.md) §4。判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。
- 位置づけ: Delay だけを扱う (Disperser は子 #5624 (FA-76))。静的な機械語の読みのみ。差分実行 (C4〜C6) はしない。製品 KPI は動かしていない。

## §1. 結論

- **部分達成**。KH 側 P の読み出しは 8 オフセットすべてを機械語で確認した。時間・同期・音符分割の役割は読めた (§2)。
- 未確定: KH の `+0x18`・`+0x1c`・`+0x20` の意味、SC 側 P の 5 オフセット (`0x9ee4`・`0x9f38`・`0x9f74`・`0x9fbc`・`0xa004`) の意味、**KH と SC の P オフセットの対応**。したがって受入条件 (param offset→意味の確定) は未達。PR は `Refs #5451`。
- 追加: KH `+0x10` は、遅延線の書き戻しに掛かる係数 (帰還量) と読める (確度 中。§2 の表の行)。意味ラベルは差分実行で未確認のため、確定扱いはしない。

## §2. KH 側 P (`this+0x3188`) の読み (Delay process `0x1802ed7f0`)

素材: `HeartCore.core_64` (`work-liftlib-targets`)。`disasm.py` で 3291 B を逆アセンブル。

| P オフセット | 読み方 (機械語) | 読み (推定を含む) |
|---|---|---|
| `+0x0` (float) | `[rsp]` 経由。`[rdx+0x3188]` の値を `cmp dword [rax+0xc]` が 0 のとき `movss xmm1,[rax]` で直接使う | 同期オフ時の遅延時間 (秒)。確定度: 高 (分岐構造から) |
| `+0x4` (int) | `mov edx,[rax+4]`・`cvtsi2sd xmm2,edx` | 同期オン時の音符分子。確定度: 高 |
| `+0x8` (int) | `dec r8d`・`cmp r8d,5`・`ja`・テーブル引き | 分割の選択 (1〜6)。確定度: 高 |
| `+0xc` (int) | `cmp dword [rax+0xc],0` の分岐 | 同期フラグ (0 = オフ・非 0 = オン)。確定度: 高 |
| `+0x10` (float) | `movss xmm12,[rax+0x10]` (`0x1802ed930`) → 目標値として `[rdi+0xb4]` に入る (`0x1802edc07`・`0x1802eda93`)。即時経路では `[rdi+0xb0]`・`[rdi+0xb8]` にも入る (`0x1802eda9c`・`0x1802edbf0`)。サンプル毎のループで `[rdi+0xb0]`→`[rdi+0xb4]` を `[rdi+0xa8]`・`[rdi+0xac]` の進行率で補間し `[rdi+0xb8]` に書く (`0x1802ee127`〜`0x1802ee143`)。その `[rdi+0xb8]` を遅延線の読み出しに掛けて、混合結果を同じ遅延線に書き戻す (`0x1802ee2c7`・`0x1802ee4c1`) | 遅延線の書き戻しに掛かる係数 (帰還量)。確度: 中 (機械語の構造から。意味は差分実行で未確認) |
| `+0x18` (byte) | `movzx ebp,byte [rax+0x18]` | 不明 (モードフラグと推定)。確定度: 低 |
| `+0x1c` (float) | `movss xmm11,[rax+0x1c]`・`mulss xmm11,xmm11` → `[rdi+0x118/0x11c/0x120]` | 不明 (2 乗して 3 箇所に格納。幅・深さの類と推定)。確定度: 低 |
| `+0x20` (float) | `movss xmm10,[rax+0x20]` → `[rdi+0x130/0x134/0x138]` | 不明 (3 箇所に格納)。確定度: 低 |

- 同期オン時の遅延時間 (推定): `P+0x4` × `table[P+0x8 - 1]` ÷ (テンポの値 `[r8+0x58]`)。テーブルは `0x181563298` の 6 要素 `{2/3, 1/2, 1/3, 1/4, 1/6, 1/8}` (確認済み)。
- 同期オフ時: 遅延時間は `P+0x0` をそのまま使う。
- 表の「推定」は、格納先の使い方まで追っていない。`+0x10`〜`+0x20` は格納先の構造体メンバの意味を読んでいない。

## §3. SC 側 P (`ctx+0x90`) の読み (Delay process `0x180ba8ad0`)

素材: `SlateCore.core_64` (`tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/`)。2551 B を逆アセンブル。

| P オフセット | 読み方 (機械語) | 読み |
|---|---|---|
| `0x9ee4` | `movss xmm9` → 直接 `[rbx+0xec]`・`[rbx+0xf0]` 等へ格納 | 不明 (遅延時間側の状態と推定)。確定度: 低 |
| `0x9f38` | `mulss xmm12`・関数 `0x18100c790` へ渡す | 不明。確定度: 低 |
| `0x9f74` (byte) | `movzx ecx,byte` → `[rsp+0x128]` 経由で後段の分岐 | フラグ (推定)。確定度: 低 |
| `0x9fbc` | `movss xmm8` → `[rbx+0x134]`・`[rbx+0x138]` 等へ格納 | 不明 (KH の格納先と同形の状態と推定)。確定度: 低 |
| `0xa004` | `movss xmm11` → `[rbx+0x14c]`・`[rbx+0x150]` 等へ格納 | 不明。確定度: 低 |

- SC 側の呼出先 `0x18100c790`・`0x180ba88a0` と KH 側の `0x180fc6870`・`0x180fc6d70` の同一性は未確認。対応の根拠にしない。

## §4. KH ⇄ SC の対応 (未確定)

- 両側とも P を `[rdx+0x3188]`・`[rcx+0x90]` から読むが、**構造体が別** (KH の P と SC の P のオフセットは別の体系)。
- 格納先の形 (KH `[rdi+0xb0..0xb8]`・`[rdi+0x118..0x120]`・`[rdi+0x130..0x138]` と SC `[rbx+0xec..0xf0]`・`[rbx+0x12c..0x134]`・`[rbx+0x14c..0x150]`) は似るが、対応は確定していない。
- よって「KH `+0xN` ⇄ SC `0x9xxx`」の一対一の写像は書けない。QuickEq (FA60 §2) のように `call` の引数 slot で対応を確定する作業が残る。

## §5. 検証 (測定 commit と再現)

- 測定 commit: `466d59d58` (`ks_fa75_delay_map.py` に KH `+0x10` の帰還経路 14 行の検査を追加した commit。本 PR の REPORT は、この commit の上に積む)。
- 再現: `python3 tools/targets/freshair/ks_fa75_delay_map.py <HeartCore.core_64> <SlateCore.core_64>` (素材 `work-liftlib-targets` を `tar --zstd -xf` で展開したもの)。
- 実測 (`466d59d58`・素材あり・`work/fa75_run_466d59d58.txt`): `real 15.407 s`・`user 14.902 s`・EXIT=0・load 1 分値 0.44 (19:29 時点)。OK 29 件・NG 0 件。
- 出力 (要点):

```
OK KH P+0x0 ... OK KH P+0x20 (8 件すべて)
OK SC P+0x9ee4 ... OK SC P+0xa004 (5 件すべて)
OK KH table 0x181563298 = 0.666667, 0.5, 0.333333, 0.25, 0.166667, 0.125
OK KH feedback @0x1802ed930 ... @0x1802ee2c0 (16 件)
OK: Delay param 読み出しの検査 (意味ラベルは未確定)
EXIT=0
```

- 判定の限界: この検査は「期待するオフセットと命令が機械語に現れる」ことだけを見る。意味ラベルは検査していない。帰還経路の検査は、命令の並びが REPORT の記述と一致することの確認で、機械語の構造からの読みである。
- 鮮度: `git diff 466d59d58 HEAD -- tools/targets/freshair/*.py tools/targets/freshair/*.sh` の出力は、本 PR の commit 後に 0 行とする (REPORT のみを変える)。

## §6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| KH の `+0x18`・`+0x1c`・`+0x20` と SC の `0x9ee4`・`0x9f38`・`0x9f74`・`0x9fbc`・`0xa004` の意味 (KH `+0x10` は帰還量と読めた・確度 中) | Delay の差分 param 写像が未確定 | #5451 (Refs・残件) |
| KH と SC の P オフセットの対応 (`call` 引数 slot での連鎖検査) | 同上 | #5451 (Refs・残件) |
| 呼出先 `0x18100c790`・`0x180ba88a0` (SC) と `0x180fc6870`・`0x180fc6d70` (KH) の同一性 | 対応の根拠が足りない | #5451 (Refs・残件) |
