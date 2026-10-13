<!-- 自動生成: python3 tools/startup/license_obs/scan_consumers.py (人手編集禁止) -->

# byte[0x14f84a8] 全サイト (FLEngine_x64.dll 26.1.7)

- 走査: 関数 57816 / 命令 2580490 / 直接参照(0x14f84a8) 0 / ポインタ 0x15e0698 ロード 44 (read 38 / write 6 / other 0)
- 静的初期バイト = `00`、スロット値 = `0x14f84a8`

## write サイト

| 関数 | ロード VA | 操作 |
|---|---|---|
| `0x10c7cd0` | `0x10c876d` | store |
| `0x10c7cd0` | `0x10cbb14` | and 0xfd |
| `0x10c7cd0` | `0x10cbb1e` | and 0xfb |
| `0x10c7cd0` | `0x10cd0b8` | or 0x02 |
| `0x10c7cd0` | `0x10cd0fe` | or 0x04 |
| `0x10c7cd0` | `0x10cf4e6` | or 0x01 |

## read サイト (bit セット側 / クリア側の線形パス上の文字列)

| 関数 | ロード VA | 検査 | jcc | bit セット側の文字列 | bit クリア側の文字列 |
|---|---|---|---|---|---|
| `0xc225d0` | `0xc22636` | test mask 0x04 | je | Upgrade Fire to Producer Edition / 31041 / Upgrade Fire to Signature Bundle / 31042 |  |
| `0xc307e0` | `0xc30ccc` | test mask 0x04 | je | Save anyway / More information | More information |
| `0xc31890` | `0xc31e13` | test mask 0x04 | je | More information |  |
| `0xc32830` | `0xc328c2` | test mask 0x04 | je |  |  |
| `0xc33690` | `0xc336e2` | test mask 0x04 | je | Warning¦%s is in ¦trial¦ mode. / FL Studio / You can save this project but you must connect your Fire controller to open the project ag / More information | Buy FL Studio / Fire_Instructions |
| `0xc33690` | `0xc337f4` | test mask 0x04 | je | Fire_Instructions | RegOfTrial |
| `0xc33c10` | `0xc33c6d` | test mask 0x04 | je | Note¦This project was saved while %s was in ¦trial¦. / FL Studio / Please attach Fire controller and restart %s to open the project / FL Studio | Buy FL Studio / Fire_Instructions |
| `0xc33c10` | `0xc33d9c` | test mask 0x04 | je | Fire_Instructions | RegOfTrial |
| `0xecec70` | `0xececea` | test mask 0x04 | jne |  | Warning / Project backups to FL Cloud are not available in Trial mode. |
| `0xecf240` | `0xecf583` | test mask 0x04 | jne |  | (disabled in Trial mode) |
| `0xed1fc0` | `0xed2012` | test mask 0x04 | je | .zip |  |
| `0xefb0d0` | `0xefb208` | test mask 0x01 | jne |  |  |
| `0xf18b60` | `0xf18cde` | test mask 0x04 | jne |  |  |
| `0xf1d410` | `0xf1d422` | test mask 0x01 | je |  |  |
| `0xf1f1f0` | `0xf1f241` | test mask 0x04 | jne | Choose to back the project up to FL Cloud this time only or every time it's saved locally. / Back up once / Back up every save / Cancel | Warning / Project backups to FL Cloud are not available in Trial mode. |
| `0x1005820` | `0x100590b` | movzx ... and al, byte ptr [rip + 0x424] | - |  |  |
| `0x10c7cd0` | `0x10cf4f0` | test mask 0x01 | je | Upgrade registration | Upgrade registration |
| `0x10d1340` | `0x10d14cd` | test mask 0x02 | je |  | Your license has expired |
| `0x10d5980` | `0x10d5a3b` | test mask 0x01 | je | BoxEdition.txt | NotReggedTxt.txt |
| `0x10d5bf0` | `0x10d5bf9` | test mask 0x01 | je |  |  |
| `0x10d5c60` | `0x10d5c83` | test mask 0x01 | - |  |  |
| `0x10d5cf0` | `0x10d5cf8` | test mask 0x01 | je | BoxRegReminder |  |
| `0x1175890` | `0x117a04a` | test mask 0x04 | jne | The plugin versions of %s have been installed. / FL Studio / Installation successful¦%s / Important note: not every plugin host supports what's required for the %s plugins to work  |  VSTi installation / please select the folder where your other VST plugins are / FL Studio /  -  |
| `0x1195b10` | `0x1195b6f` | test mask 0x02 | je | Fire  /  [build  /  / plugin |  [build  /  / plugin |
| `0x11a3320` | `0x11a332b` | test mask 0x01 | jne | General / Last BRR date / General / Last BRR date | General / Last BRR date / General / Last BRR date |
| `0x11a3320` | `0x11a333a` | test mask 0x02 | jne | General / Last BRR date / General / Last BRR date | General / Last BRR date / General / Last BRR date |
| `0x11b2ac0` | `0x11b2f0b` | test mask 0x01 | - |  |  |
| `0x11bdea0` | `0x11bdf53` | test mask 0x04 | je |  |  |
| `0x11be0a0` | `0x11be5b8` | test mask 0x01 | je | Please remember to register | FL Studio 2026  / Registered to:  / UVSH |
| `0x11c2d80` | `0x11c41eb` | test mask 0x02 | je | Upgrade to Producer edition for more features... / Upgrade reminder | Update your expired license / ... |
| `0x11c68e0` | `0x11c6d0e` | test mask 0x04 | je |  |  |
| `0x1214160` | `0x1214193` | test mask 0x04 | je |  |  |
| `0x1214160` | `0x12141e3` | test mask 0x01 | je |  |  |
| `0x124dd00` | `0x124dd2a` | test mask 0x01 | je | Create account | My account |
| `0x13173a0` | `0x1322c3d` | test mask 0x04 | je |  |  |
| `0x135b3a0` | `0x135c258` | test mask 0x04 | jne |  | (disabled in Trial mode) |
| `0x1363af0` | `0x1363b9c` | test mask 0x04 | jne | untitled.flp / Warning / The project needs to be saved before it can be backed up to FL Cloud. / Save now | Warning / Project backups to FL Cloud are not available in Trial mode. |
| `0x1375990` | `0x13763be` | test mask 0x02 | je | Fire edition / BasicInitialization failed. | BasicInitialization failed. |

## gradeChar (`[[[0x15e4790]]+0xd0]` の 1 バイト) の連続形サイト (下限。追跡で増える形は末尾の節)

- 連続形 (0x15e4790 ロード → `mov r,[r]` → `mov r,[r+0xd0]` を辿る形): 196 (read 189 / write 7)
- `条件` は gradeChar に対する比較。`@0x40` = 未登録 ("Update registration" 状態) のとき実行される側、`@0x41` = 登録 (tier A) のとき実行される側

| 関数 | ロード VA | 操作 | 条件 | @0x40 (未登録) で実行される側の文字列 | @0x41 (登録) で実行される側の文字列 |
|---|---|---|---|---|---|
| `0xc307e0` | `0xc30cb6` | cmp imm 0x40 | gradeChar > 0x40 | Save anyway / More information | Save anyway / More information |
| `0xc31890` | `0xc31dfd` | cmp imm 0x40 | gradeChar > 0x40 | More information | More information |
| `0xc32b30` | `0xc32c3d` | movzx r8, byte ptr [rax] | - |  |  |
| `0xc34060` | `0xc3417d` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xc589b0` | `0xc5918c` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xc589b0` | `0xc59213` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xc589b0` | `0xc59236` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xc589b0` | `0xc5a7c1` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xdcaab0` | `0xdcb14d` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0xe5cd20` | `0xe5f562` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xe5cd20` | `0xe5f5e9` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xe5cd20` | `0xe5f60c` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xe5cd20` | `0xe60b97` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xe73950` | `0xe74431` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xe73950` | `0xe744b8` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xe73950` | `0xe744db` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xe73950` | `0xe75a66` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xe88710` | `0xe88e46` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xe88710` | `0xe88ecd` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xe88710` | `0xe88ef0` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xe88710` | `0xe8a47b` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xe972d0` | `0xe97963` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xe972d0` | `0xe979ea` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xe972d0` | `0xe97a0d` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xe972d0` | `0xe98f98` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xeb46a0` | `0xeb4cff` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xeb46a0` | `0xeb4d86` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xeb46a0` | `0xeb4da9` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xeb46a0` | `0xeb6334` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xecec70` | `0xececd4` | cmp imm 0x40 | gradeChar > 0x40 | Warning / Project backups to FL Cloud are not available in Trial mode. |  |
| `0xecf240` | `0xecf56d` | cmp imm 0x40 | gradeChar > 0x40 | (disabled in Trial mode) |  |
| `0xed1fc0` | `0xed1ffc` | cmp imm 0x40 | gradeChar > 0x40 | .zip | .zip |
| `0xefb0d0` | `0xefb217` | cmp imm 0x40 | gradeChar == 0x40 |  | vompdlfe / vompdlfe / PP¢£¤¢P¤jP |
| `0xf03cb0` | `0xf03e28` | cmp imm 0x40 | gradeChar > 0x40 | Don't unlock | Continue |
| `0xf18b60` | `0xf18cc8` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0xf1f1f0` | `0xf1f22b` | cmp imm 0x40 | gradeChar > 0x40 | Warning / Project backups to FL Cloud are not available in Trial mode. | Choose to back the project up to FL Cloud this time only or every time it's saved locally. / Back up once / Back up every save |
| `0xf22f20` | `0xf23e20` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf22f20` | `0xf23ea7` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xf22f20` | `0xf23eca` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf22f20` | `0xf25455` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xf22f20` | `0xf27f21` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf22f20` | `0xf27fa8` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xf22f20` | `0xf27fcb` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf22f20` | `0xf29574` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xf2dbb0` | `0xf2e294` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf2dbb0` | `0xf2e31b` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xf2dbb0` | `0xf2e33e` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf2dbb0` | `0xf2f8c9` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0xf3c870` | `0xf3ce9a` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0xf40840` | `0xf42526` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0xf40840` | `0xf42639` | cmp imm 0x40 | gradeChar > 0x40 | FL Studio / %s %s.%d | FL Studio / %s %s.%d |
| `0xf46420` | `0xf4644c` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0xf46490` | `0xf4b7d1` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf83a40` | `0xf84639` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf83a40` | `0xf846c0` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0xf83a40` | `0xf846e3` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0xf83a40` | `0xf85c6e` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x1005fa0` | `0x1005fce` | cmp imm 0x42 | gradeChar == 0x42 |  |  |
| `0x1005fa0` | `0x1005fe4` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1006080` | `0x10060d2` | cmp imm 0x42 | gradeChar == 0x42 |  |  |
| `0x10a7270` | `0x10a727d` | cmp imm 0x40 | gradeChar > 0x40 | free |  |
| `0x10a9170` | `0x10a9212` | cmp imm 0x40 | gradeChar > 0x40 | welcome_window_trial |  |
| `0x10a9170` | `0x10a927c` | cmp imm 0x40 (jcc: setbe) | - |  |  |
| `0x10a9170` | `0x10a92b5` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x10aaae0` | `0x10aaf32` | cmp imm 0x40 | gradeChar > 0x40 | customers / Free for customers / FREE FOR CUSTOMERS | free / customers / Free |
| `0x10b66a0` | `0x10b66a8` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x10b6700` | `0x10b6714` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x10b7770` | `0x10b787f` | cmp imm 0x40 | gradeChar > 0x40 | Sign in to import your FL Studio Web projects / Sign in / Sign in to your Image-Line account to import your FL Studio Web projects |  |
| `0x10b7770` | `0x10b7a9f` | cmp imm 0x40 | gradeChar > 0x40 | Sign in to load your Project backups / Sign in / Sign in to your Image-Line account to load your project backups | Loading your Project backups ... / Loading your Project backups |
| `0x10b8ae0` | `0x10b8ba4` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x10c7530` | `0x10c7543` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x10c7cd0` | `0x10ca55c` | write | - | | |
| `0x10c7cd0` | `0x10cbaf9` | write | - | | |
| `0x10c7cd0` | `0x10cd0c2` | write | - | | |
| `0x10c7cd0` | `0x10cf4b5` | write | - | | |
| `0x10c7cd0` | `0x10cf531` | cmp imm 0x40 | gradeChar > 0x40 | Buy / register | Upgrade registration |
| `0x10c7cd0` | `0x10cf547` | cmp imm 0x44 | gradeChar >= 0x44 | Upgrade registration | Upgrade registration |
| `0x10c7cd0` | `0x10cf610` | write | - | | |
| `0x10d1880` | `0x10d18f2` | movzx; cmp imm 0x41 | gradeChar >= 0x41 | /newreleases/?username=%s&productcodes=%s&productversions=%s | /newreleases/?username=%s&productcodes=%s&productversions=%s |
| `0x10d3a30` | `0x10d3a72` | write | - | | |
| `0x10d50d0` | `0x10d52fc` | movzx rcx, byte ptr [rax] | - |  |  |
| `0x10f3d30` | `0x10f444e` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x10f3d30` | `0x10f44d5` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x10f3d30` | `0x10f44f8` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x10f3d30` | `0x10f5a83` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x1105e40` | `0x1105e7c` | cmp imm 0x40 | gradeChar > 0x40 | Undo tests are disabled in Trial mode | Failed to open an empty project |
| `0x1144cc0` | `0x1144ce6` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1144f70` | `0x11453fc` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1145a70` | `0x1145ab2` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1145c60` | `0x1145c99` | cmp imm 0x40 | gradeChar > 0x40 |  | Welcome to  / FL Studio |
| `0x1146190` | `0x114625d` | cmp imm 0x40 | gradeChar > 0x40 |  in %s trial / Continue | Continue |
| `0x1146190` | `0x1146541` | cmp imm 0x40 | gradeChar > 0x40 |  trial | Start %0:s%1:s |
| `0x1146850` | `0x1146866` | cmp imm 0x40 | gradeChar > 0x40 |  trial |  |
| `0x1148900` | `0x1148995` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x1150320` | `0x11503c6` | cmp imm 0x40 | gradeChar > 0x40 | Online | News / P_Large |
| `0x1150ee0` | `0x1151018` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1150ee0` | `0x1151098` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1150ee0` | `0x11511fb` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1150ee0` | `0x11512d5` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1150ee0` | `0x1151a0c` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1150ee0` | `0x1151c5a` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1152210` | `0x1152271` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x11523e0` | `0x11523ef` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1152440` | `0x11524c2` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x11526a0` | `0x11526b3` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x1152b00` | `0x1152b52` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x1175890` | `0x1175f87` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1175890` | `0x117600e` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x1175890` | `0x1176031` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1175890` | `0x11775bc` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x1175890` | `0x117a030` | cmp imm 0x40 | gradeChar > 0x40 |  VSTi installation / please select the folder where your other VST plugins are / FL Studio | The plugin versions of %s have been installed. / FL Studio / Installation successful¦%s |
| `0x118a810` | `0x118b029` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x118a810` | `0x118b0b0` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x118a810` | `0x118b0d3` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x118a810` | `0x118c67c` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x1195b10` | `0x1195b37` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x1195b10` | `0x1195b59` | cmp imm 0x40 | gradeChar > 0x40 |  [build  /  / plugin | Fire  /  [build  |
| `0x1196c00` | `0x11995b9` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1196c00` | `0x1199640` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x1196c00` | `0x1199663` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1196c00` | `0x119abee` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x11a57c0` | `0x11a83ea` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x11a57c0` | `0x11a8471` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x11a57c0` | `0x11a8494` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x11a57c0` | `0x11a9a1f` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x11b2450` | `0x11b2514` | movzx r8, byte ptr [r8] | - |  |  |
| `0x11bdea0` | `0x11bdf3d` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x11bfc10` | `0x11bfda5` | movzx rdx, byte ptr [rax] | - |  |  |
| `0x11c71b0` | `0x11c728a` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x11c71b0` | `0x11c7b4b` | cmp imm 0x40 | gradeChar > 0x40 | Software\Image-Line\FL Studio 26 / General / Last start |  |
| `0x11cb000` | `0x11cd0c1` | write | - | | |
| `0x11d8f30` | `0x11d8fa7` | cmp imm 0x40 | gradeChar > 0x40 | (Trial) |  |
| `0x11dbdd0` | `0x11dbe3f` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x11dbdd0` | `0x11dbe74` | cmp imm 0x42 | gradeChar == 0x42 |  |  |
| `0x11dd800` | `0x11de6ea` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x11dd800` | `0x11de771` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x11dd800` | `0x11de794` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x11dd800` | `0x11dfd1f` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x11ee670` | `0x11ee761` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1201100` | `0x1201758` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1201100` | `0x12017df` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x1201100` | `0x1201802` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1201100` | `0x1202d8d` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x1207ac0` | `0x1208ffe` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x1207ac0` | `0x1209044` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x1207ac0` | `0x120908a` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x120d340` | `0x120d9ee` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x120d340` | `0x120da75` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x120d340` | `0x120da98` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x120d340` | `0x120f023` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x1214bb0` | `0x12152c0` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1214bb0` | `0x1215347` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x1214bb0` | `0x121536a` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1214bb0` | `0x12168f5` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x121adc0` | `0x121ade1` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x121f770` | `0x121f77b` | cmp imm 0x40 (jcc: seta) | - |  |  |
| `0x1223880` | `0x1223edf` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1223880` | `0x1223f66` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x1223880` | `0x1223f89` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1223880` | `0x1225514` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x12351a0` | `0x1235a3f` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x123dbc0` | `0x123e479` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x123dbc0` | `0x123e500` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x123dbc0` | `0x123e523` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x123dbc0` | `0x123faae` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x1254d10` | `0x12553ac` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1254d10` | `0x1255433` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x1254d10` | `0x1255456` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1254d10` | `0x12569e1` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x125ea00` | `0x1261813` | cmp imm 0x43 | gradeChar >= 0x43 |  |  |
| `0x125ea00` | `0x1261832` | cmp imm 0x42 | gradeChar >= 0x42 |  |  |
| `0x126ea00` | `0x126f0bb` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x126ea00` | `0x126f142` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x126ea00` | `0x126f165` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x126ea00` | `0x12706f0` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x128f9e0` | `0x129059b` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x128f9e0` | `0x1290622` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x128f9e0` | `0x1290645` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x128f9e0` | `0x1291bd0` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x1297250` | `0x12978d3` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1297250` | `0x129795a` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x1297250` | `0x129797d` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x1297250` | `0x1298f08` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x12f38b0` | `0x12f4205` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x12f38b0` | `0x12f428c` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x12f38b0` | `0x12f42af` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x12f38b0` | `0x12f5858` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x13173a0` | `0x131c55d` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x13173a0` | `0x131c5e4` | movzx rdx, byte ptr [rdx] | - |  |  |
| `0x13173a0` | `0x131c607` | cmp imm 0x40 | gradeChar == 0x40 |  |  |
| `0x13173a0` | `0x131dbb0` | cmp imm 0x3f | gradeChar == 0x3f |  |  |
| `0x13173a0` | `0x1322c27` | cmp imm 0x40 | gradeChar > 0x40 |  |  |
| `0x13562e0` | `0x1356582` | cmp imm 0x40 | gradeChar > 0x40 | Unlock / FL Studio | Open unlock window / Click "Open unlock window" after updating %s or buying new products. / FL Studio |
| `0x135b3a0` | `0x135c242` | cmp imm 0x40 | gradeChar > 0x40 | (disabled in Trial mode) |  |
| `0x1363af0` | `0x1363b86` | cmp imm 0x40 | gradeChar > 0x40 | Warning / Project backups to FL Cloud are not available in Trial mode. | untitled.flp / Warning / The project needs to be saved before it can be backed up to FL Cloud. |
| `0x13737a0` | `0x13737a4` | cmp imm 0x40 | gradeChar == 0x40 |  |  |

## gradeChar レジスタ追跡で増えた形 (連続形 196 に無い `[obj+0xd0]` 使用)

- 追跡: `0x15e4790` ロード (全 2422) の直後が `mov r2,[r1]` のとき r2 を 13 命令追い、`[r2+0xd0]` を使う最初の命令を拾う (r2 書換え/ret/jmp で打切り)。追跡形 266 ロード/102 関数 = 連続形 196 + 追加 70 (21 関数、うち連続形に無い関数 13)
- 追加の内訳 (命令種別): {'addr': 69, 'store': 1}。`addr` = `lea reg,[obj+0xd0]` (ポインタフィールドのアドレス取得 = 以降は退避先経由の間接アクセス)、`store` = フィールドへの書込

| 関数 | ロード VA | 使用 VA | 種別 | 命令 | 連続形に無い関数 |
|---|---|---|---|---|---|
| `0xe7a470` | `0xe7a5f1` | `0xe7a5fb` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xe7a470` | `0xe7a869` | `0xe7a873` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xe7a470` | `0xe7ab09` | `0xe7ab13` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xe7a470` | `0xe7ad7f` | `0xe7ad89` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xe7a470` | `0xe7affc` | `0xe7b006` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xf2dbb0` | `0xf323c9` | `0xf323d3` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf2dbb0` | `0xf3263f` | `0xf32649` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf2dbb0` | `0xf328b7` | `0xf328c1` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf2dbb0` | `0xf32b5d` | `0xf32b67` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf2dbb0` | `0xf339ac` | `0xf339b6` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf40840` | `0xf40c78` | `0xf40c82` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf40840` | `0xf40f1a` | `0xf40f24` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf40840` | `0xf41d9f` | `0xf41da9` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf40840` | `0xf42017` | `0xf42021` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf40840` | `0xf4228d` | `0xf42297` | addr | `lea rax, [rax + 0xd0]` |  |
| `0xf51fd0` | `0xf52195` | `0xf5219f` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xf51fd0` | `0xf52413` | `0xf5241d` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xf51fd0` | `0xf52698` | `0xf526a2` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xf51fd0` | `0xf52928` | `0xf52932` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xf51fd0` | `0xf53796` | `0xf537a0` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xf51fd0` | `0xf53a21` | `0xf53a2b` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xfeffe0` | `0xff0085` | `0xff008f` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xffbff0` | `0xffc2fe` | `0xffc308` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xffbff0` | `0xffc59f` | `0xffc5a9` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xffbff0` | `0xffd406` | `0xffd410` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0xffbff0` | `0xffd694` | `0xffd69e` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x103ca70` | `0x103cd95` | `0x103cd9f` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x103ca70` | `0x103d02e` | `0x103d038` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x103ca70` | `0x103de86` | `0x103de90` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x103ca70` | `0x103e106` | `0x103e110` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x103ca70` | `0x103e3a4` | `0x103e3ae` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x103ca70` | `0x103e62e` | `0x103e638` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x103ca70` | `0x103e8ba` | `0x103e8c4` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x10d50d0` | `0x10d52e3` | `0x10d52ed` | store | `mov qword ptr [rcx + 0xd0], rax` |  |
| `0x1183130` | `0x118335b` | `0x1183365` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x1183130` | `0x11835dc` | `0x11835e6` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x1183130` | `0x1183906` | `0x1183910` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x1183130` | `0x118453b` | `0x1184545` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x118a810` | `0x118f54e` | `0x118f558` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11bfc10` | `0x11bfe63` | `0x11bfe6d` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11bfc10` | `0x11c00fb` | `0x11c0105` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11bfc10` | `0x11c037a` | `0x11c0384` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11c71b0` | `0x11c72fc` | `0x11c7306` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11cb000` | `0x11cb384` | `0x11cb38e` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11cb000` | `0x11cc35b` | `0x11cc365` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11d9340` | `0x11d9613` | `0x11d961d` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x11d9340` | `0x11da43f` | `0x11da449` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x11d9340` | `0x11da6b6` | `0x11da6c0` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x11d9340` | `0x11da958` | `0x11da962` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x11d9340` | `0x11dabef` | `0x11dabf9` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x11d9340` | `0x11dae65` | `0x11dae6f` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x11dd800` | `0x11e284c` | `0x11e2856` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11dd800` | `0x11e368f` | `0x11e3699` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11dd800` | `0x11e3920` | `0x11e392a` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11dd800` | `0x11e3b91` | `0x11e3b9b` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11dd800` | `0x11e3e2c` | `0x11e3e36` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11dd800` | `0x11e40a3` | `0x11e40ad` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11dd800` | `0x11e4356` | `0x11e4360` | addr | `lea rax, [rax + 0xd0]` |  |
| `0x11fc770` | `0x11fd1bf` | `0x11fd1c9` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x11fc770` | `0x11fd7e8` | `0x11fd7f2` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x1231170` | `0x12311aa` | `0x12311b4` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x12875a0` | `0x128793a` | `0x1287944` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x12875a0` | `0x1287ba6` | `0x1287bb0` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x12875a0` | `0x1287e44` | `0x1287e4e` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x12875a0` | `0x1288c87` | `0x1288c91` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x12875a0` | `0x1288f2c` | `0x1288f36` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x12875a0` | `0x12891aa` | `0x12891b4` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x13582c0` | `0x1358586` | `0x1358590` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x1358870` | `0x135894e` | `0x1358958` | addr | `lea rax, [rax + 0xd0]` | ○ |
| `0x1366190` | `0x1366266` | `0x1366270` | addr | `lea rax, [rax + 0xd0]` | ○ |
