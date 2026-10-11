# 自動生成: `python3 tools/icall/disp_size/report_tables.py`

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。

### census (capstone の disp 位置/長さ vs dispfix 真値)
| サンプル | 命令数 | disp 有 | rip 相対 | rip 誤り (率) | disp32 非 rip 誤り | 誤り計 (nop 除く) | 関数 誤り有/全 |
|---|--:|--:|--:|--:|--:|--:|--:|
| OTT F (icall closure 282 関数) | 17789 | 5134 | 985 | 103 (10.46%) | 29 | 132 (115) | 17/282 |
| OTT F 線形 sweep (参考) | 18864 | 5333 | 1002 | 105 (10.48%) | 79 | 184 (117) | 20/282 |
| FLEngine M11 closure (7,421 関数) | 341713 | 139708 | 27839 | 501 (1.80%) | 490 | 991 (988) | 264/7421 |
| Fruity Balance closure (67 関数) | 4216 | 1501 | 203 | 14 (6.90%) | 12 | 26 (26) | 11/67 |
| Fresh Air SlateCore closure (131 関数) | 6267 | 2052 | 231 | 16 (6.93%) | 19 | 35 (26) | 8/131 |
| KH HeartCore gain+infra (196 関数) | 12578 | 3865 | 1153 | 111 (9.63%) | 52 | 163 (135) | 27/196 |
| FLEngine_x64.dll (全 .pdata) | 2566540 | 1058904 | 136207 | 2542 (1.87%) | 4877 | 7419 (7340) | 1590/57816 |
| Fresh Air SlateCore (全 .pdata) | 3526710 | 1363751 | 55496 | 2751 (4.96%) | 6587 | 9338 (6026) | 2877/25063 |
| KH HeartCore (全 .pdata) | 4995580 | 1682527 | 125547 | 4439 (3.54%) | 16724 | 21163 (11916) | 6952/111666 |
| Serum2 win64 vst3 (全 .pdata) | 2515362 | 807737 | 91724 | 3751 (4.09%) | 19289 | 23040 (15063) | 4916/33791 |
| Delphi plugin 133 DLL (全 .pdata) | 68681048 | 25703502 | 2791307 | 87126 (3.12%) | 263037 | 350163 (340853) | 53640/1837410 |
| mac Fruity Mach-O x86_64 slice (LC_FUNCTION_STARTS) | 67002757 | 25540240 | 3107415 | 31007 (1.00%) | 1463476 | 1494483 (143620) | 739006/1274001 |

全 sample 合計: rip 相対 mem.disp 値の検証 6339109 件中 不一致 0 / imm_offset 不整合 0 / 誤りの原因 = 66 prefix 1903831 + VEX2.pp66 3306 + その他 0 / 67 付き rip 相対 0 / phantom disp 0

### ツール別の影響 (対象命令 = そのツールが disp を見る命令)

| ツール | disp の使い方 | サンプル | 対象命令数 | capstone 誤り (率) | 関数 hash 変化 |
|---|---|---|--:|--:|--:|
| inventory/fw_overlap.py, p0c/kernel_matrix.py | disp_size==4 の全 disp32 をゼロ化 | Delphi 133 DLL | 10153246 | 350163 (3.45%) | 51645/1837410 (2.81%) |
| inventory/win_funcs.py | rip 相対 disp32 のみゼロ化 | Delphi 133 DLL (hash は 180 PE) | 2791307 | 87126 (3.12%) | 38369/2012968 (1.91%) |
| framework/fw_prep.py (同規約・編集禁止) | 同上 | FLEngine 全 .pdata / Balance closure | 136207 / 203 | 2542 (1.87%) / 14 (6.90%) | win_funcs と同規約 |
| inventory/mac_funcs.py | rip 相対のみ | mac Fruity x86_64 slice | 3107415 | 31007 (1.00%) | SimSynth で 20/340 (全体未計測) |
| icall_rewrite.py (modrm 自前計算) | disp 位置を modrm から算出 | OTT F | 985 | 影響 0 (e2e 89/89 bit 一致; modrm_tail_len == dispfix) | - |
| mem.disp 値のみ使用 (x64c.py, liftlib/mc.py, khmach.py, m11 ldmach.py, serum2/freshair scripts ほか 42 ファイル) | address+size+mem.disp | 全 sample の rip 相対 | 6339109 | 値不一致 0 | - |

### 関数 fingerprint への影響 (Delphi plugin)

| 規約 (使用スクリプト) | 関数数 | hash が変わる関数 | distinct hash legacy→fixed | ≥13 DLL 共有 hash legacy→fixed | framework 判定関数 |
|---|--:|--:|--:|--:|--:|
| fw_overlap: md5, 全 disp32 (fw_overlap.py / kernel_matrix.py), 133 DLL | 1837410 | 51645 (2.81%) | 47487→40492 | 10836→10875 | DLL 当たり中央値 12475→12529, fw_fraction 中央値 0.958→0.966 |
| win_funcs: sha1, rip 相対 disp32 (win_funcs.py / framework/fw_prep.py), 180 PE | 2012968 | 38369 (1.91%) | 53046→46117 | 11266→11306 | 1755661→1762730 (非fw→fw 7069 / fw→非fw 0) |

legacy 再現性: fw_overlap 集計 == stored fw_overlap.json: True / win_funcs hash == stored winfuncs/*.json: 180/180 PE

### prefix matrix

| opsize 区分 | case 数 | capstone disp_size 誤り | disp_offset 誤り | imm 誤り | dispfix 不一致 |
|---|--:|--:|--:|--:|--:|
| no66 | 846947 | 9400 | 0 | 0 | 0 |
| opsize16 | 405036 | 252028 | 0 | 0 | 0 |
| rexw+66 | 443743 | 0 | 0 | 0 | 0 |
