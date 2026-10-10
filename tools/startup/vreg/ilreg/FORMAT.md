# FORMAT.md — FLEngine `0x10c7cd0` 登録パーサ / ILRegKey 書式 (静的解読)

対象: `FLEngine_x64.dll` 26.1.7 win64 (ImageBase `0x400000`, 22,227,016 B)。
VA はすべて Ghidra 表記の絶対 VA。根拠は逆アセンブル (capstone) と Ghidra decompile の実測であり、
推定には (推定) を付ける。再現: `python3 scripts/pedis.py <VA> <len>`,
`python3 scripts/extract_constants.py`, `node verify/test_golden.mjs`。

## 0. 結論 (先出し)

1. **`0x10c7cd0` (32,177 B) は「レジストリ値の読取 → ILRegKey 復号 → マシン突合 → ティア別期限判定 →
   `byte[0x14f84a8]` への bit 反映」を 1 関数で行う**。判定の実体は `|<キー>:<YYYYMMDD>:` 形の
   機能レコードと `|id:<マシン識別文字列>` レコードであり、**MachineGuid・ComputerName・AppData 路の
   SHA-256 と突合する** (§3, §6)。
2. **vreg seed のプレースホルダ `WEBSTUDIO-ACTIVATED-PLACEHOLDER` はこの判定を「通らない」**。
   平文に `|<キー>:<日付>:` / `|id:…` レコードを生成できないため、全ティア grade 0 →
   `gradeChar = 0x40` (表示上「Update registration」)・`byte[0x14f84a8]` は bit1/2 含め 0 のまま
   (§7)。ただし **bit0 (=1 で Trial 表示) を立てる書込経路はこのビルドでは死蔵コード** であり、
   パーサ実行後の bit0 は常に 0 (=「登録済み」側の読み) になる (§7.4)。
3. ILRegKey 値は **16 進文字列エンベロープ + VM 復号** (`FUN_008d0380` → バイトコード 687 B
   @ `0x14111e0`) で平文になる。VM インタプリタの完全実装は次段 (§8)。
4. `Software\Image-Line\Registrations\` 直下の `FL Studio user name` / `webpass` / `FLS Info` /
   `license plate` は**表示用グローバルへの保存のみ**で、ILRegKey の検証には入らない (§2.2)。

## 1. 関数と呼び出し関係 (実測)

| VA | サイズ | 役割 | 根拠 |
|---|---|---|---|
| `0x10c7cd0` | 32,177 B | 本体 (登録パーサ)。caller は `0x10d50d0` (Shared 読取系), `0x11cde20` (Fire Edition チェック) | `tools/startup/work/func_index.tsv` 行 51342 |
| `0x10c7850` | 894 B | 残日数計算。`Shared\General` の値 `HSD` (逆回し防止の最高既知日) とファイル時刻で今日を補正 | 本解読 decompile |
| `0x10c7530` | 455 B | 登録情報表示 (`gradeChar > 0x40` で "Registered to: <名前>") | 同 |
| `0x8e6150` | 663 B | `observeRegistration()` 相当 (`FL Studio*` サブキーの ILRegKey 非空検査) — CAB-94 済 | vreg REPORT §6 |
| `0x8cfd20` / `0x8cfdc0` / `0x8cf800` | 147/170/192 B | 文字列 box 化 (9 バイト/文字レコード, `c^0xe0` / `c>>8^0x21`) と delta 付き box | 同 |
| `0x8d0580` / `0x8d0380` | 413/497 B | 16 進アンパック + **VM 復号** (§5) | 同 |
| `0x8e6660` / `0x442770` | 226/279 B | `YYYYMMDD` (8 文字) → Delphi TDate。**8 文字以外・不正値は 0 を返す** | 同 |
| `0x8e6770` | 1,461 B | 平文の先頭グループ分割 (§6.1) | 同 |
| `0xbf89b0` / `0xbf86f0` / `0xbf8b40` | 144/699/665 B | SHA-256 初期化 (H=`6a09e667…5be0cd19`) / 圧縮 (K 表 @ `0x13b102c`, 64 語実測) / 後処理 | 同 |

## 2. 入力 (読む registry 値とマシン情報) — 受入要件 1

### 2.1 レジストリ (`tools/startup/work/reg_raw.csv` の `010c7cd0` 行 + 実機械語)

| # | 値 | 呼出 VA | 用途 |
|---|---|---|---|
| 1 | `HKCU\Software\Image-Line\Registrations\` → `FL Studio user name` | `0x10c87b8` | グローバル `0x15e43f8` へ (表示用) |
| 2 | 同 → `FL Studio webpass` | `0x10c87f5` | `0x15e4bd0` (表示用) |
| 3 | 同 → `FLS Info` | `0x10c8832` | `0x15e3b00` (表示用) |
| 4 | 同 → `FL Studio license plate` | `0x10c886f` | `0x15e19f8` (表示用, `0x10c7530` で優先表示) |
| 5 | `HKCU\Software\Image-Line\Registrations\FL Studio 26.1` → `ILRegKey` | `0x10c94bc/0x10c94da` | **本体検証の入力** |
| 6 | `HKLM\…\Registrations\FL Studio 26.1` → `ILRegKey` (HKCU フォールバック) | `0x10c94fb/0x10c952c` | 同 |
| 7 | `HKLM\SOFTWARE\Microsoft\Cryptography` → `MachineGuid` (生 Win32: `RegOpenKeyExA` access `0x20019` = KEY_READ\|KEY_WOW64_64KEY) | decompile 内 | マシン識別文字列 (§3) |
| 8 | `HKCU\Software\Image-Line\Shared\General` → `HSD` (読み書き, `0x10c7850`) | `0x10c7b33/0x10c7b4e/0x10c7b55` | 「今日」の逆回し防止 |

### 2.2 レジストリ以外のマシン情報 (マシン識別文字列の素)

呼出順にハッシュへ積まれる (§3):

1. `SHGetFolderPathW(0, 0x1a=CSIDL_APPDATA, 0, 0, buf)` — `SHFolder.dll` を `LoadLibraryW` して動的取得 (`0x10c7cd0` 冒頭)。
2. `GetComputerNameExW(ComputerNameNetBIOS=0)`。
3. 上表 #7 の `MachineGuid`。

## 3. マシン識別文字列 (確定)

`0x10c7cd0` 内で構築されグローバル `0x15e1358` へ保持される文字列。証拠アドレスは本関数内。

```
seed  = lowByte(AppData経の各UTF-16 unit) ++ lowByte(ComputerName各unit) ++ lowByte(MachineGuid各unit)
digest= SHA-256(seed)                       # 32B — 0xbf89b0/0xbf86f0/0xbf8b40, K表 0x13b102c
hex64 = uppercase(hex(digest))              # 64 文字 (小文字 'a'-'z' を 'A'-'Z' へ, 0x10c92bf-0x10c92ce)
dashed= hex64 を 8 文字ごとに '-' 挿入      # 64+7 = 71 文字 (i&7==0, i≠1, i≠最終, 0x10c92f7-0x10c9354)
ck    = Σ(各文字 c について (c*2 - 3)) & 0xFF を 71 文字分積算   # 8bit 演算, 0x10c93bf-0x10c93d0
machineString = dashed + '-' + hex2(ck)     # 74 文字 (ck は小文字 hex 2 桁, 0x10c93fd-0x10c941b)
```

例: `XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-xy`
(verify/test_golden.mjs T1 群が node:crypto に対する再現を確認)。
注意: 非 ASCII (日本語パス等) は**下位バイトのみ**ハッシュに入る (AppendChar が 1 レコード=1 unit、
SHA-256 ブロック充填が `*(byte*)dst = char` のため)。mac 版は別解読 (対象外)。

## 4. ILRegKey 値のエンベロープ (確定部分)

`ILRegKey` 値 (REG_SZ) は人間可読ではない。復号は 3 段:

1. **box 化** `FUN_008cfd20(box; value; wipe)` — 各 UTF-16 unit を 9 バイトレコード化
   (`FUN_008cf800`: `rec[2]=lo^0xe0, rec[4]=hi^0x21`, 他はレコード自身のアドレス下位バイト派生)。
   box は `PTR_DAT_008cf6c8` のクラス。呼出の第 4 引数 `DAT_010d0b1e=1` で復号後に入力文字列をゼロ消去。
2. **16 進アンパック** `FUN_008d0580` (`0x8d0580`): 各文字を `'0'..'9' → c-0x30 / 以外 → c-0x37`
   でニブル化し 2 文字→1 バイト。**文字数は奇数可** (切り捨て。最終ニブルは records 領域直後の
   1 バイトに余剰書込される = 実装上のスラック書込、振る舞いに影響なし)。字数 = バイト数×2 が
   理想だが検査はしない (garbage-in)。
3. **VM 復号** `FUN_008d0380` (§5)。

## 5. VM 復号 (`FUN_008d0380`) — 構造は確定、完全実装は次段

- プログラム: **687 バイト @ `0x14111e0`** (`work/vmprog.bin` に抽出済)。
- 実行器: `FUN_0055d810` (variant スタック VM)。ストリーム/コンテキスト生成 `FUN_008c5eb0`,
  プログラムロード `FUN_008c7c10`, 実行 `FUN_0055d810`。
- 引数 (push 順): 入力バイト列ストリーム, 出力レコード列ストリーム, サイズ n, `9`, `0xe0`, `0x21`,
  `2`, `4`, コールバック (`FUN_008c7450` 経由) — 9 バイトレコードと XOR 定数はこの並びと一致。
- 出力: n レコードの平文文字列 (インターフェース `+0x38` as-string / `+0x40` 長 / `+0x58` char-at)。
- `FUN_008e7080` が `(入力, 出力)` のインターンキャッシュ (`DAT_015f9468`) を持つ。

**次段作业**: `FUN_0055d810` 系のオペコード表を実装して reader に組み込む (REPORT §次タスク)。

## 6. 平文の構造 (確定: 分割/突合の機械語、先頭フィールド構成は (推定) 含む)

### 6.1 分割 (`FUN_008e6770`, セパレータ定数 `0x8e6db8`=`:`, `0x8e6dc8`=`|`)

- 最初の `:` より前 → **head**。最初の `:` が `|` より先に無い (または `:` 無し) 場合は全体が head。
- head の次から `:` 区切りで field0 (`F0`), field1 (→ `YYYYMMDD` として日付化), 残り → **rest**。
- `FUN_008e6770` の参照定数: `|LL=OFF` (`0x10d0b4c`, delta −16), `|LL=` (`0x10d0b68`, delta −33),
  `TRSLA` (`0x10d0b80`, delta −20) — delta は `FUN_008cfdc0` の short 加算 (下位 16bit)。
  `|LL=<数値>` が見つかれば StrToIntDef 相当で数値化して `0x15e43a8` へ。`|LL=OFF` は数値化スキップ。
  `TRSLA` が見つかれば `0x15e0e90` = "1" (`0x10d0b98`)。

### 6.2 レコード (rest 内, `|` 始まり)

| レコード | 意味 | 突合先 |
|---|---|---|
| `\|<キー>:<YYYYMMDD>:` | 機能キー別の有効期限。キーはティア表 (§7.1) | 日付判定 (§7.2) |
| `\|id:<machineString>` | **マシン束縛**。§3 の文字列と完全一致検索 (`\|id:` 接頭辞は `0x10d0bd8` の `9b 96 6c` から −0x32 で生成) | machineString |
| `\|LL=<n>` / `\|LL=OFF` | 数値フィールド (意味未同定 (推定): license level/数) | グローバル保存のみ |
| `TRSLA` (生文字列) | フラグマーカー (意味未同定 (推定)) | グローバル保存のみ |

### 6.3 重複検出フラグ (`0x15e1b10`)

`0x10ca4e4`-`0x10ca52f` の走査で rest に特定キー (`0x793b`=31035, `0x792c`=31020, `0x7922`=31010
を `FUN_0043a7e0` = IntToStr 化した語) を含むか検査し、含めば 1。reader では単純に
`"|31035"|"|31020"|"|31010"` の含有で再現 (接頭辞 3 文字の変換文字列連結の詳細は (推定))。

## 7. 判定フロー (確定 — 逆アセンブルでピン留め)

### 7.1 ティア表 (`0x15b7f00`, DWORD 列)

| イテレーション | gradeChar | 第一次キー | 第二次キー (fallback) |
|---|---|---|---|
| 0 | `0x41` 'A' | 31000 | 2147483647 (=評価省略) |
| 1 | `0x42` 'B' | 31010 | 31005 |
| 2 | `0x43` 'C' | 31020 | 2147483647 |

キーの意味 (製品/機能 ID の同定) は未同定 (推定)。マスク `DAT_010d0be0` = 6 → grade 1/2 のみが
フラグ操作の対象。

### 7.2 各ティアの grade 計算 (第一次: `0x10cad1c`-`0x10cb991`)

1. **marker** (`0x65b`): head が空 (平文が `:` 始まり) なら 1。head 非空の場合は
   `FUN_008e5e90(head, [], 0)` が常に −1 を返すため charsum 比較 (`%s:%s:` テンプレート
   `0x10d0bbc` + `FUN_008e6e30` の 5 回 charsum 正規化) に到達**しない** (死蔵)。
   → `marker==0` なら grade 0 確定 (`0x10cae5c` je)。
   (実ライセンス平文が `:` 始まりなのかは実データ確認事項 — reader は `strictHead` オプションで両対応)
2. **期限前倒し判定**: 前回値 `[0x66c]` 日が正で今日以内なら grade=1 確定 (`0x10cae62`-`0x10cae7b`)。
3. マシン突合 (`0x10cb6b8`-`0x10cb728`): rest に `|id:<machineString>` があれば 'L'、無くても
   重複フラグが立てば 'L'、無ければ '+'。**'L' のみ次へ** ('+'/'c' は grade 0)。
4. 機能レコード (`0x10cb741`-`0x10cb98a`): rest から `|<キー>` を検索し、直後の `:` に続く
   次の `:` までを 8 文字日付として `FUN_008e6660` で日付化。
   **grade = 2 (有効) / 日付が 0 (8 文字不正 or 不正値) も grade 2** / 日付 ≤ 今日なら grade 1。
5. 第二次キーは第一次 grade ≠ 2 のときのみ評価 (`0x10cbb28`-`0x10cbb38`)。
   grade 2 → `flag |= 2`、grade ∈ {1,2} → `flag |= 4` (`0x10cd0b8`/`0x10cd105`)。

### 7.3 フラグと UI への反映

| 条件 | 効果 | アドレス |
|---|---|---|
| 初期化 | `byte[0x14f84a8] = 0` (`0x10d08d8`=0) | `0x10c876d` |
| 第一次ティア grade 2 | `gradeChar = 0x41+i`、`flag &= 0xfd`、`flag &= 0xfb` | `0x10cbb03`-`0x10cbb25` |
| 第二次ティア grade 2 | `flag \|= 2` (Fire edition bit)、`gradeChar` 更新 | `0x10cd0b8` |
| 第二次ティア grade ∈{1,2} | `flag \|= 4` | `0x10cd105` |
| 残日数 ≤ 0 (`0x10c7850` < 8 && < 1) | `gradeChar = 0x3f` ('?') | `0x10cf4a4`-`0x10cf4c6` |
| `Pos("Please remember to register", ログ文字列) > 0` | `flag \|= 1` | `0x10cf4c9`-`0x10cf4ed` |
| gradeChar < 0x41 | ボタン ID 3 "Update registration" (名前空なら 4 "Buy / register") | `0x10cf531`-`0x10cf58f` |
| gradeChar < 0x44 | ボタン ID 1 "Upgrade registration" | 同 |
| その他 | ボタン ID 2 "Registration details" | 同 |
| `gradeChar > 0x40` | `0x10c7530` が "Registered to: <名前>" を表示/ログ名に反映 | `0x10c7530`, `0x11be5b8` |

### 7.4 bit0 (Trial bit) はこのビルドで死蔵

`flag |= 1` は全バイナリ中 **1 箇所のみ** (`0x10cf4e6`)。条件の第 2 引数の文字列は関数冒頭で
0 初期化 (`0x10c8192`) され以後**書込みなし** (0x10c7cd0 内の `[rbp+0x48c8]` アクセスは
0x10c8192/0x10cf4d0/0x10cfa6a の 3 箇所のみ) → `Pos(...)` は常に 0 → bit0 が立つ経路は無い。
`0x15e0698` は `0x14f84a8` への唯一のポインタ (.data 全走査で確認) なので、他経路からの設定も無い。
読み側 (`test al,1`: `0x11be5b8`, `0x11b2f0b`, `0x11a332b` 等約 10 箇所) は bit0=1 で
"Please remember to register" 系に分岐するが、本ビルドでは静的に到達しない。
**→ CAB-106 の動的観測では「bit0 は常に 0」を最初の仮説に置くこと。**

## 8. vreg seed プレースホルダの判定 — 受入要件 2

入力: `data/seed.json` license group
(`ILRegKey = WEBSTUDIO-ACTIVATED-PLACEHOLDER` @ HKCU/HKLM × `FL Studio 26.1`/`FL Data`,
user name = `WebStudio User`, webpass/FLS Info = `webstudio`, license plate = `WebStudio`)。

| 段 | 結果 | 根拠 |
|---|---|---|
| 存在検査 (`FUN_008e6150`) | **通る** (CAB-94 で自動テスト済み) | vreg REPORT §6 |
| エンベロープ | 31 文字 (奇数) → 15 バイトの garbage pack。16 進としても非正規 (`W`,`B`,`S`,`T`,`U`,`D`,`I`,`-` 等はニブル規則外の値に写像されるだけ) | §4, test T2b |
| VM 復号 | garbage → `|<キー>:<日付>:` / `|id:…` レコードを含む平文は生成されない (書式を満たす前提の構造が入力に無いため。VM 出力の詳細は次段) | §5-§6 |
| ティア判定 | 全ティア grade 0 → `gradeChar = 0x40`, flag = 0 | §7 |
| 表示 | "Registered to: <名前>" は**出ない** (0x40 は 0x40 より大きくない)。ボタン = "Update registration" (ID 3) | §7.3 |
| bit0 | 0 のまま (そもそも立つ経路が無い) | §7.4 |

**結論: プレースホルダは「拒否される」(登録状態としては無効扱い) だが、クラッシュ・例外・
bit0 立ては起きない。ユーザへの示しは「Update registration」表示。**

### vreg seed への統合手順 (実装は次段 — CAB-213 以降)

1. `verify/reader.mjs` を `tools/startup/vreg/js/` へコピーし、`Vreg` の `expectedLicense()` を
   reader の `judge()` に接続する (入力: seed の MachineGuid + VFS 上の AppData パス + ComputerName)。
2. `licenseMode: 'external'` (ユーザ .reg 投入) のときは、`.reg` の `ILRegKey` 値を
   `envelopeHexPack` → VM 復号 → `splitFirstGroup` で検査し、`|id:<machineString>` が自マシンと
   一致するかを表示に使う (判定の強制はしない — 無力化方針は維持)。
3. seed 側は現状維持でよい: プレースホルダは「存在検査は通すが本検証は通らない」値であり、
   エンジンの挙動 (Update registration 表示) はユーザ方針 (無力化・無条件通過) と矛盾しない。
   bit0=1 (Trial 表示) にしたい場合も、本ビルドではエンジン自身が bit0 を立てないため
   vreg 側の `licenseFlagBit0` 制御は効かない点に注意 ( lifting 後の観測で再確認)。
4. VM 実装後に「正当書式の合成」が必要になった場合は CAB-115 (ユーザ起点 import) の入力を
   reader で検証するのみに留め、生成はしない (チケット方針)。

## 9. 未解決 (正直に)

1. **VM バイトコード (687 B) のオペコード意味論** — 復号の完全再現には必要。構造 (ストリーム×2,
   サイズ, 9/0xe0/0x21/2/4 引数) までは確定。
2. **平文 head の実データ構造** — marker ゲートが「head 空」を要求する (§7.2-1) ため、
   実ライセンス平文が `:` 始まりか、head に別の意味 (チェックサム等) があるかは VM 実装後に
   実データ (ユーザの .reg) で確定する。reader は `strictHead` で両経路を試せる。
3. `|LL=<n>` / `TRSLA` / ティアキー 31000/31005/31010/31020 の意味 — 数値の実測のみ。
4. mac (FLEngine_x64.dylib) の同機能は未解読 (別機会)。
5. FUN_008e7080 のインターンキャッシュ (`DAT_015f9468`) は同一入力の再復号を省略するだけ
   (振る舞いに影響なしと (推定))。
