<!-- 自動生成: python3 tools/startup/license_obs/run_cases.py (人手編集禁止) -->

# 0x10c7cd0 の実機械語実行結果 (unicorn)

| case | 終了 | flag byte[0x14f84a8] | gradeChar | button ID | VM 復号 / head / machine 突合 / record 検索 / tier 適用 / tier skip (到達回数) | 未実装 API | 値読取 (distinct) |
|---|---|---|---|---|---|---|---|
| A1 ILRegKey 無し (cl=0) | ok | 0x00 | 0x40 | 0 | 0/3/3/0/0/3 | - | 5 |
| A2 ILRegKey 無し (cl=1 Fire check) | ok | 0x00 | 0x40 | 0 | 0/3/3/0/0/3 | - | 5 |
| A3 ILRegKey 無し + 別 MachineGuid / ComputerName / AppData | ok | 0x00 | 0x40 | 0 | 0/3/3/0/0/3 | - | 5 |
| A4 ILRegKey 無し + MachineGuid 取得失敗 | ok | 0x00 | 0x40 | 0 | 0/3/3/0/0/3 | - | 4 |
| A5 ILRegKey 無し・unit 初期化なし (#107 時点の条件) | ok | 0x00 | 0x40 | 0 | 0/3/3/0/0/3 | - | 5 |
| D2 空文字列の ILRegKey | ok | 0x00 | 0x40 | 0 | 0/3/3/0/0/3 | - | 6 |
| B1 vreg seed のプレースホルダ (cl=0) | ok | 0x00 | 0x40 | 3 | 1/3/0/0/0/3 | - | 6 |
| B2 vreg seed のプレースホルダ (cl=1) | ok | 0x00 | 0x40 | 3 | 1/3/0/0/0/3 | - | 6 |
| B3 vreg seed のプレースホルダ + 別 MachineGuid / ComputerName / AppData | ok | 0x00 | 0x40 | 3 | 1/3/0/0/0/3 | - | 6 |
| NB0 B1 + unit 初期化なし (ハンドラ表が無く 0x8c9d7c で停止) | UcError: Invalid memory read (UC_ERR_READ_UNMAPP | — | — | — | 1/0/0/0/0/0 | - | 6 |
| D1 16 進 128 文字の非正規 ILRegKey | ok | 0x00 | 0x40 | 3 | 1/3/0/0/0/3 | - | 6 |
| D3 16 進 8 文字の非正規 ILRegKey | ok | 0x00 | 0x40 | 3 | 1/3/0/0/0/3 | - | 6 |
| N1 gradeChar 初期値 imm 0x40→0x42 に改変 (0x10ca56f) | ok | 0x00 | 0x42 | 1 | 0/3/3/0/0/3 | - | 5 |
| N2 bit0 を立てる or の直前の jle を nop 化 (0x10cf4e4) | ok | 0x01 | 0x40 | 3 | 0/3/3/0/0/3 | - | 5 |
| N3 FLAG の初期化値 imm 改変: store 元 0x10d08d8 を 0x04 に (.data) | ok | 0x04 | 0x40 | 0 | 0/3/3/0/0/3 | - | 5 |
| NB1 B1 + 復号 VM 入口 0x8d0380 を ret に改変 (復号結果 head が変わる) | ok | 0x00 | 0x40 | 3 | 1/3/0/0/0/3 | - | 6 |
| NB2 B1 + tier 判定の 4 ゲート (marker/charsum/machine/record) を nop 化 → tier 適用が実行される | ok | 0x00 | 0x43 | 1 | 1/3/3/3/3/3 | - | 6 |
| NB3 B1 + marker/charsum/machine の 3 ゲートのみ nop 化 (record ゲートが残り apply へ届かない) | ok | 0x00 | 0x40 | 3 | 1/3/3/3/0/3 | - | 6 |

## 復号結果 head (0x8e6770 の先頭グループ; 0x10cad6e 時点の UTF-16LE 生バイト先頭 16 B)

| case | head (hex) | 3 tier で同一 |
|---|---|---|
| A1  | `` (0 文字) | True |
| A2  | `` (0 文字) | True |
| A3  | `` (0 文字) | True |
| A4  | `` (0 文字) | True |
| A5  | `` (0 文字) | True |
| D2  | `` (0 文字) | True |
| B1  | `ab003400810018002f00f300b100cc00` (15 文字) | True |
| B2  | `ab003400810018002f00f300b100cc00` (15 文字) | True |
| B3  | `ab003400810018002f00f300b100cc00` (15 文字) | True |
| D1  | `9e00a3001800a5004200f4009c00b900` (64 文字) | True |
| D3  | `97008000a200ac00` (4 文字) | True |
| N1  | `` (0 文字) | True |
| N2  | `` (0 文字) | True |
| N3  | `` (0 文字) | True |
| NB1 | `12356b8cc4675dfeb6590f30688bc162` (15 文字) | True |
| NB2 | `ab003400810018002f00f300b100cc00` (15 文字) | True |
| NB3 | `ab003400810018002f00f300b100cc00` (15 文字) | True |

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

