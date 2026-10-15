# 付録 — #107 残項目: inline HWID ×24 と `== 0x3f` 26 の突合 (本 REPORT §6・§9)

日付: 2026-10-15 / 測定 commit: `94875c48` (probe と結果 JSON を変えた最後の commit) / 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/startup/license_obs/probe_hwid.py` (6.5 s)。

## 9. 「inline HWID ×24」と「`== 0x3f` 比較 26」の突合 (`probe_hwid.py`; 結果 `results/probe_hwid.json`)

目的: §6 の未解決「`== 0x3f` 26 (本調査) と 24 (GATES/ilreg) の不一致」を解消し、GATES G04 の HWID 側の 24 関数の定義を機械的に確認する。
定義 (プローブ内。docstring が正本): API = 関数内の call 先の import 名 (直接 call は宛先の thunk `jmp qword ptr [rip+IAT]` を 1 段たどる。`call [rip+IAT]` は IAT を直接指すときだけ解決)。STR = rip 相対で `MachineGuid` (ASCII・UTF-16LE) または `SOFTWARE\Microsoft\Cryptography` (ASCII) を指す命令。DYN = rip 相対で UTF-16LE の `SHGetFolderPathW` または `SHFolder.dll` を指す命令 (動的解決の目印)。G3f = gradeChar を `cmp ..., 0x3f` で比較する関数 (`results/flag_sites.json`)。

| 定義 | 関数数 n | G3f (26) との重なり |
|---|---:|---:|
| H1 GetComputerNameExW と SHGetFolderPathW を同一関数で IAT 直接に呼ぶ | 0 | 0 |
| H2 GetComputerNameExW と RegOpenKeyExA/W・RegQueryValueExW を同一関数で呼ぶ | 24 | 3 |
| H3 STR (MachineGuid・Cryptography の文字列を参照) | 24 | 3 |
| H4 GetComputerNameExW を IAT 直接に呼ぶ | 25 | 3 |
| H5 SHGetFolderPathW を IAT 直接に呼ぶ | 4 | 0 |
| H6 DYN (SHGetFolderPathW・SHFolder.dll の UTF-16LE を参照) | 24 | 3 |
| H7 GetComputerNameExW を含み、SHGetFolderPathW を IAT 直接または DYN で使う | 24 | 3 |

- **H2 = H3 = H6 = H7 (同一集合 24 件・差 0)**。API・文字列・動的解決の独立な定義が一致する。0x10c7cd0・0xf2dbb0・0x11dd800 は 24 に入る。0x10c7530 はどの定義にも入らない (GATES が別項目で挙げる関数。HWID 側の所属は未確認)。
- **文字列の検索対象**: ASCII の `MachineGuid` は 0 件。UTF-16LE の `MachineGuid` は 24 件 (rip 参照 25 件)。ASCII の `SOFTWARE\Microsoft\Cryptography` は 24 件 (同 25 件)。旧版の H3 は後者だけを数えていたため、MachineGuid の検出とは言えなかった。
- **SHGetFolderPathW は 24 関数すべてが動的に呼ぶ**: 24 関数は UTF-16LE の `SHFolder.dll` と `SHGetFolderPathW` を rip 相対で参照し (各文字列 25 件・すべて `lea`)、IAT 直接の参照は持たない。逆アセンブルで確認した例 (0xbf94e0): `0xbf96bd` lea SHFolder.dll → `0xbf96c4` call LoadLibraryW の thunk → `0xbf96d7` lea SHGetFolderPathW → `0xbf96de` call 0x4235f0 (GetProcAddress を 2 回呼ぶラッパ) → `0xbf96ec` mov edx,0x1a (CSIDL_APPDATA) → `0xbf9703` call qword ptr [rbp+0x280] (名前で解決した関数ポインタ)。
- 旧版の「SHGetFolderPathW は同一関数で共起しない (H1 = 0)」は、IAT 直接の呼出しだけを数えた結果に基づく誤り。動的解決を取りこぼしていた。この記述は取り消す。
- IAT 直接で SHGetFolderPathW を呼ぶのは H5 の 4 関数 (0x5a09f0・0x5a0c90・0x63b880・0x81bca0) だけで、いずれも 24 に入らない。
- 「26 vs 24」は母集団の違い (変わらず)。26 は gradeChar の比較関数、24 は HWID コード。重なりは 3 件 (0xf2dbb0・0x11dd800・0x11a57c0) のみ。

限界 (未解決):
(a) 関数ポインタ表 (`.data` 内の関数アドレス) 経由の call は解決していない。H1・H5 の 0 件・4 件は下限。
(b) 24 関数内の rip 以外の間接 call (`call reg`・`call [reg+..]`) は **1,682 件** (逆アセンブル数)。呼出先は未解決で、24 は直接の import 参照と文字列参照で決めた下限。
(c) IAT 直接で SHGetFolderPathW を呼ぶ 4 関数の用途は未確認。

検証: 測定 commit `94875c48` を commit 済み HEAD で実行。`FL_WIN64_DIR=<fl-win64 展開先> python3 tools/startup/license_obs/probe_hwid.py`: 6.5 s (実行直後の load average 0.22/0.41/0.23)、`results/probe_hwid.json` は再実行で cmp 一致。素材は `fl-win64` の `extracted/block00031_PE.bin` (sha256 先頭 `b2c64da4`)。出力: functions=57,816・IAT 解決 738 名・G3f=26・G40=80・rip 以外の間接 call は全体 42,633 件 (H6 の関数内 1,682 件)。
