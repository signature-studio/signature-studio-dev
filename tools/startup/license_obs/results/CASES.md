<!-- 自動生成: python3 tools/startup/license_obs/run_cases.py (人手編集禁止) -->

# 0x10c7cd0 の実機械語実行結果 (unicorn)

| case | 終了 | flag byte[0x14f84a8] | gradeChar | button ID | 未実装 API | 値読取 (distinct) | 所要 s |
|---|---|---|---|---|---|---|---|
| A1 ILRegKey 無し (cl=0) | ok | 0x00 | 0x40 | 0 | - | 5 | 0.03 |
| A2 ILRegKey 無し (cl=1 Fire check) | ok | 0x00 | 0x40 | 0 | - | 5 | 0.03 |
| A3 ILRegKey 無し + 別 MachineGuid / ComputerName / AppData | ok | 0x00 | 0x40 | 0 | - | 5 | 0.03 |
| A4 ILRegKey 無し + MachineGuid 取得失敗 | ok | 0x00 | 0x40 | 0 | - | 4 | 0.03 |
| D2 空文字列の ILRegKey | ok | 0x00 | 0x40 | 0 | - | 6 | 0.03 |
| B1 vreg seed のプレースホルダ (cl=0) | UcError: Invalid memory read (UC_ERR_READ_UNMAPP | — | — | — | - | 6 | 0.02 |
| B2 vreg seed のプレースホルダ (cl=1) | UcError: Invalid memory read (UC_ERR_READ_UNMAPP | — | — | — | - | 6 | 0.02 |
| D1 16 進 128 文字の非正規 ILRegKey | UcError: Invalid memory read (UC_ERR_READ_UNMAPP | — | — | — | - | 6 | 0.03 |
| N1 gradeChar 初期値 imm 0x40→0x42 に改変 (0x10ca56f) | ok | 0x00 | 0x42 | 1 | - | 5 | 0.03 |
| N2 bit0 を立てる or の直前の jle を nop 化 (0x10cf4e4) | ok | 0x01 | 0x40 | 3 | - | 5 | 0.03 |
| N3 FLAG の初期化値 imm 改変: store 元 0x10d08d8 を 0x04 に (.data) | ok | 0x04 | 0x40 | 0 | - | 5 | 0.03 |

## 値読取の内訳 (case A1 / A4 / B1)

### A1 ILRegKey 無し (cl=0)
- `HKCU\Software\Image-Line\Registrations :: FL Studio license plate`
- `HKCU\Software\Image-Line\Registrations :: FL Studio user name`
- `HKCU\Software\Image-Line\Registrations :: FL Studio webpass`
- `HKCU\Software\Image-Line\Registrations :: FLS Info`
- `HKLM\SOFTWARE\Microsoft\Cryptography :: MachineGuid`

### A4 ILRegKey 無し + MachineGuid 取得失敗
- `HKCU\Software\Image-Line\Registrations :: FL Studio license plate`
- `HKCU\Software\Image-Line\Registrations :: FL Studio user name`
- `HKCU\Software\Image-Line\Registrations :: FL Studio webpass`
- `HKCU\Software\Image-Line\Registrations :: FLS Info`

### B1 vreg seed のプレースホルダ (cl=0)
- `HKCU\Software\Image-Line\Registrations :: FL Studio license plate`
- `HKCU\Software\Image-Line\Registrations :: FL Studio user name`
- `HKCU\Software\Image-Line\Registrations :: FL Studio webpass`
- `HKCU\Software\Image-Line\Registrations :: FLS Info`
- `HKCU\Software\Image-Line\Registrations\FL Studio 26.1 :: ILRegKey`
- `HKLM\SOFTWARE\Microsoft\Cryptography :: MachineGuid`

