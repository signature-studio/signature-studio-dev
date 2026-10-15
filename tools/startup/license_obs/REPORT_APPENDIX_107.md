# 付録 — #107 残項目: inline HWID ×24 と `== 0x3f` 26 の突合 (本 REPORT §6・§9)

日付: 2026-10-15 / 測定 commit: `3d615fc3` / 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/startup/license_obs/probe_hwid.py` (6.6 s)。

## 9.: 「inline HWID ×24」と「`== 0x3f` 比較 26」の突合 (`probe_hwid.py`; 結果 `results/probe_hwid.json`)

目的: §6 の未解決「`== 0x3f` 26 (本調査) と 24 (GATES/ilreg) の不一致」を解消し、GATES G04 の「MachineGuid+GetComputerNameExW+SHGetFolderPathW を読む同型コード ×24」の定義を機械的に確認する。
定義 (プローブ内): API = 関数内の call 先の import 名 (直接 call は宛先の thunk `jmp qword ptr [rip+IAT]` を 1 段たどる。`call [rip+IAT]` は IAT を直接指すときだけ解決)。STR = rip 相対で `MachineGuid`・`SOFTWARE\Microsoft\Cryptography` の ASCII 文字列を指す命令を持つ。G3f = gradeChar を `cmp ..., 0x3f` で比較する関数 (`results/flag_sites.json`)。

| 定義 | 関数数 n | G3f (26) との重なり |
|---|---:|---:|
| H1 GetComputerNameExW と SHGetFolderPathW を同一関数で呼ぶ | 0 | 0 |
| H2 GetComputerNameExW と RegOpenKeyExA/W・RegQueryValueExW を同一関数で呼ぶ | 24 | 3 |
| H3 MachineGuid / Cryptography 文字列を参照する | 24 | 3 |
| H4 GetComputerNameExW を呼ぶ | 25 | 3 |
| H5 SHGetFolderPathW を呼ぶ | 4 | 0 |

- **H2 = H3 (同一集合 24 件・差 0)**。API と文字列の独立な 2 定義が一致した。0x10c7cd0・0xf2dbb0・0x11dd800 は 24 に入る。0x10c7530 は 24 に入らない (GATES が別項目で挙げる関数で、HWID 側の所属は未確認)。
- **「SHGetFolderPathW との共起」は成立しない (H1 = 0)**。SHGetFolderPathW を呼ぶ 4 関数 (0x5a09f0・0x5a0c90・0x63b880・0x81bca0) は 24 のいずれにも入らない。よって GATES G04 補足・startup REPORT §1 の「MachineGuid+GetComputerNameExW+SHGetFolderPathW を読む同型コード ×24」は、同一関数内の共起としては誤り。24 の構成は GetComputerNameExW + Reg 系 (+ MachineGuid 文字列) である。文書を訂正した (GATES.md 補足・startup REPORT §1)。
- **「26 vs 24」は数の食い違いではなく母集団の違い**。26 は gradeChar (`[[[0x15e4790]]+0xd0]`) の `== 0x3f` 比較関数 (§3.2)、24 は HWID コードである。重なりは 3 件 (0xf2dbb0・0x11dd800・0x11a57c0) のみ。§6 の該当行は解消。

限界 (未解決): (a) 関数ポインタ表 (`.data` 内の関数アドレス) 経由の call は解決していない (493 件の `call [rip+..]` の大半が該当し、IAT 直接はその一部)。よって H1・H5 の 0 件・4 件は下限。(b) SHGetFolderPathW の呼出元 (AppData 取得) は未特定。
検証: 測定 commit `3d615fc3` (コードを変えた最後の commit)。`FL_WIN64_DIR=<fl-win64 展開先> python3 tools/startup/license_obs/probe_hwid.py` を commit 済み HEAD で実行: 6.6 s (実行直前の load average 0.52/0.34/0.17)、`results/probe_hwid.json` は再実行で cmp 一致。出力: functions=57,816・IAT 解決 738 名・STR 参照 VA 24・G3f=26。
