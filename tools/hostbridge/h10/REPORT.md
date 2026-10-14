# REPORT — H10 / #218: Fruity Wrapper の wrapper chunk reader 解析

> 正本: `tools/hostbridge/h10/REPORT.md`。書式仕様は `tools/hostbridge/nfo/FORMAT.md` §8 (本解析で更新)。親 #99 (H9)。

最終更新 2026-10-13 / 検証起点 commit・実測は §6 / 再現: `bash tools/hostbridge/h10/h10_e2e.sh` (exit 0 = 全 PASS。前提: `FL_WIN64_DIR` に fl-win64 展開済み。Ghidra 不要)。evidence の再生成: `bash tools/hostbridge/h10/analysis/reproduce.sh` (Ghidra 12.1.4 + JDK 21 必須、`REGEN_FLE=1` で FLEngine 側も)。

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (静的解析のみで lift・IR pass を使っていない)。

## 0. 結論 (先出し)

- **判定: 3 つの確定事項 (①②③) を全て静的解析で確定した。** 対象は `Fruity Wrapper_x64.dll` 2.7.0.5653 (fl-win64 `block19091`)。別ビルド `block23676` は同ロジックを PE バイトで確認 (Ghidra 解析は未実施)。
- **① record 1/30/31/32 は Wrapper が補う (= 無くても受理)。** reader の record 表は 14 id (1, 2, 30, 31, 32, 50–58) だけで、未知 id は読まずに次 record へ seek する。欠落時の既定値は §2 の表。生成 DB が出さない 1/30/31/32/53/57 は全て任意。
- **② id 57 は VST2 の entry-point hint ではない。** 実体は `TVSTPlugin+0x9c4` = `dispatcher(effGetVstVersion = 58)` の戻り値 (u32、欠落時 1) で、読まれるのは bitness 不一致の時だけ。さらに `TVSTPlugin` ctor の呼出元は 1 箇所 (`fw:0x87c9ad`) のみで、**第 6 引数 (hint) は定数 0**。hint を DB/.fst に持たせる経路は存在せず、標準名 export (`main` / `VSTPluginMain` 系 26 綴り) で足りる。
- **③ 212 の flags: `0x10` = generator (FL 自身の reader で確定)、`0x80` は DB 生成経路で立たない。** `fle:0xf54900` は 212 の flags `& 0x10` で .fst の種別を 0x31 (generator) / 0x32 (effect) に決める。`0x80` は `fle:0xaac1e0` の writer が「呼出側の第 4 引数 ≠ 0」の時だけ立て、DB 生成経路 (`fle:0xaba880`) は常に 0 を渡す。
- **受理: 生成 .fst の chunk (5 entry) と実機 OTT.fst は Wrapper の reader に受理される** (version 8 は許容範囲 5–12 内。reader 模型 + PE バイト検査で確認)。ただし起動に至るかは「Wrapper → FL host の plugin 検索 (msg 7)」と「VST の module ロード」が通ることに依存し、**実物の実行検証は未実施** (§4、§7)。
- **生成器の変更は不要。** 訂正が要るのは文書側 3 点 (§5): chunk 先頭 u32 8 は kind でなく **format version**、`tools/flp` の `parseWrapperData` が id 50 を必須とするのは Wrapper の挙動と異なる、record 57/58 の意味。

## 1. 方法と対象 (実測)

| 項目 | 内容 |
|---|---|
| 対象 PE | `block19091_PE.bin` (Fruity Wrapper 2.7.0.5653 x64, sha256 先頭 16 桁 `31f012f6d741a113`, 20,653 関数) / `block23676_PE.bin` (`372bbc84e85f427d`) / `block00031_PE.bin` = FLEngine_x64.dll (`b2c64da40921cf26`, 59,009 関数)。関数数 = `functions_*.csv` の `wc -l` − 1 |
| 解析 | Ghidra 12.1.4 headless 自動解析: Wrapper 2 m 49.700 s (4 コア)、FLEngine 10 m 13.307 s (3 コア)。以降は `ghidra_scripts/Query.java` の読取クエリ (1 回 6–9 s、FLEngine 6–17 s) |
| 主張の検査 | ① `analysis/h10_check.py` (capstone: dispatch tree を命令列から抽象実行) ② `analysis/fle_check.py` ③ `analysis/evidence_check.py` (Ghidra decompile 文面) ④ `src/wrapper_reader.ts` (reader 模型) + `test/` |
| 主な関数 (fw: = block19091 の VA、base 0x400000) | `0x870da0` SaveRestoreState / `0x875af0` record reader (version ≥ 5) / `0x875800` legacy reader (≤ 4) / `0x8712b0` writer / `0x74a8e0`・`0x74a970`・`0x74aa40`・`0x74abd0` stream helper / `0x871fe0`+`0x79e540`+`0x79e850` host への plugin 検索 / `0x86e1a0` load / `0x86e9f0` LoadPlugin_Finish / `0x87c980` factory → `0x7a9db0` TVSTPlugin ctor |
| FL 側 (fle:) | `0xaac1e0` 212 writer / `0xaac300` .fst writer / `0xaba880` DB 生成の呼出元 / `0xf54900` .fst 種別判定 / `0xf46490` .fst・.flp plugin loader の 212 case / `0xf3c870` project writer / `0x915750`・`0x915220` plugin locate と応答整形 |

## 2. wrapper chunk (event 213) reader の確定仕様 [確: 命令列 + decompile]

**ゲート (`fw:0x870da0`)**: 先頭 u32 `ver` を読み、`ver > 12` → 拒否 (エラー通知 5)、`ver == -1` → 無視、`ver ≤ 4` → legacy reader、`5 ≤ ver ≤ 12` → record reader。Wrapper 自身の writer は常に 12 を書く (`fw:0x870e97`)。FL 11.5.5 の DB writer (`fle:0xa9eff0`) は 8 を書く。**この u32 は kind でなく format version**。reader が `false` を返した場合は raw stream を `+0xf6c` に保持して再保存でも state を失わない。

**record loop (`fw:0x875af0`)**: header = `{u32 id, u64 size}` (12 B、writer `fw:0x74a6a0` と同形)、`id == 0` なら header をもう 1 つ読む。各 record は `min(size, N)` バイトを 0 埋め済み buffer へコピー (短い record 可)。処理後は必ず「record 先頭 + size」へ seek するので、**未知 id や過大な size は他の record に影響しない**。文字列は version ≤ 8 が ANSI、≥ 9 が UTF-8 (`fw:0x875d1f cmp ecx,9`)。

| id | 読込 | reader の扱い | 欠落時の既定 | 生成 DB |
|---|---|---|---|---|
| 1 | 0x14 B | MIDI in/out port (+0/+4)、+0x10 (0 → 2) → plugin option | port −1/−1 (`fw:0x8744b0`) | 出さない |
| 2 | 0x19 B | u32@9 = flags (下記)、u32@13 → plugin +0x24 | u32@9 = 0x7900 (`fw:0x8744d0`) | 常に出す (0x407908 \| 0x400 \| 0x100000) |
| 30 | 0x10 B | **読むだけで以後どこにも使わない** | — | 出さない |
| 31 / 32 | n×12 B | 入力 / 出力 routing。`LoadPlugin_Finish` が `min(plugin の port 数, n)` 件だけ反映 | 0 件 = plugin 既定 | 出さない |
| 50 | 0x10 B → u32 | plugclass | **0 (= VST2 fx)** | 常に出す |
| 51 | 4 B | VST2 uniqueID | 0 | class 0/4 |
| 52 | 0x10 B | VST3 CID | 全 0 | class 7/8 |
| 53 | size | plugin state。`size > 0` の時だけ plugin へ渡す | state なし | 出さない |
| 54 / 55 / 56 | 文字列 | name / path (`/` → `\` に置換、`fw:0x8760bd`) / vendor | 空 | 非空の時 |
| 57 | 4 B | `effGetVstVersion` (§3-②) | **1** | 出さない |
| 58 | 文字列 | CLAP id | 空 | class 11/12 |

**record 2 の flags (u32@9)** — 解析で読み取れた bit のみ: `0x400000` = 個別 option bit を適用しない (plugin の既定 option のまま。FL の DB writer は常に立てる)、`0x400` = 64bit のみ保存、`0x100000` = bitness bit が有効 (単一アーキ)。`bitnessMismatch = (flags & 0x100000) && ((flags & 0x400) != host64)` — 64bit FL に `0x507d08` (実機 OTT.fst) / `0x407908` を渡すと不一致 false。他の bit が制御する option 名は binary からは特定していない (外部情報 PyFLP の `_VSTFlags` と bit 位置は整合するが、本解析の根拠ではない)。

## 3. 確定事項 ①②③

### ① record 1/30/31/32 は Wrapper が補うか — **補う (任意)** [確]

reader が読む id の表は上のとおり (`h10_check.py` が dispatch tree を asm から導出し **14 id・各サイズ/種別の全一致**を fw_a / fw_b の両方で確認)。1/31/32 が無い場合は既定のまま、30 は元々未使用、53/57 が無い場合は plugin 既定 state・VST version 1。→ **DB 生成器が 2/50/51|52|58/54/55/56 だけを出す現行仕様で reader は欠落を起こさない**。

### ② VST2 hint の供給元 (id 57 候補) — **供給元は存在しない。id 57 = VST version** [確]

| 根拠 | 実測 |
|---|---|
| id 57 の書出し (`fw:0x871867`) | `TVSTPlugin` の instance の時だけ `+0x9c4` を record 0x39 (4 B) として書く (class 0/4 の分岐内) |
| `+0x9c4` の源 (ctor `fw:0x7aabfb`〜`0x7aac02`) | `dispatcher(effect, 0x3a, 0, 0)` = **effGetVstVersion (opcode 58)** の戻りを格納。`< 2` なら VST 1.x 扱いの分岐あり |
| id 57 の読込 | `local_d4` (既定 1)。唯一の使用は bitness 不一致分岐の `+0x8a0` 格納 → plugin の `vtable+0x1b0` (state 適用) の引数 (`fw:0x86f29c`) |
| hint (`TVSTPlugin.Create` 第 6 引数) | ctor `fw:0x7a9db0` への参照は **直接 call 1 件 (`fw:0x87c9ad`) のみ** (call / lea / 8 B ポインタを .text・.data 全走査、.pdata の RUNTIME_FUNCTION を除く)。そこで `mov qword ptr [rsp+0x28], 0` = hint 定数 0。`FindMain(hint = 0)` は 26 綴り表へ落ちる (既存 evidence: `tools/hostbridge/evidence/fw_findmain_getproc.c`) |
| export 事前検査 (`fw:0x7a9030`) | `main` または `vstpluginmain` (小文字化比較) を export していれば通過 (hint は常に空) |

→ **DB に hint を持たせる必要はなく、持たせる先 (record も `.nfo` キーも) が無い。** `tools/hostbridge/nfo/REPORT.md` §5「hint を DB に持たせる必要が出た場合」・§6-3 は解消。Kilohearts の stub 消去 (alias) で標準名 export に揃える既存方針 (HOSTBRIDGE §2) が必須条件になる。fw_b (`block23676`) でも同じ 1 call・定数 0 を PE バイトで確認。

### ③ 212 の u16@16 フラグ — **0x10 = generator [確]、0x80 = DB 経路では立たない [確]**

| 根拠 | 実測 |
|---|---|
| 書込 (`fle:0xaac1e0`) | 52 B 領域、`+0x10` flags に `(writer ctx +0x88 ≠ 0) → \|= 0x80`、`(entry+0x24 ≠ 0 = generator) → \|= 0x10`、`+8` = kind table (kind 2,3 → 2) |
| 読込側の意味 (`fle:0xf54900`) | 212 (event 0xd4, 長さ 0x34) を peek し、`flags & 0x10 == 0` → type 0x32 (effect)、≠ 0 → 0x31 (generator)。FLhd format 0x30 の .fst の種別判定 = ブラウザ/スロット適合の判定 |
| 0x80 の源 | `fle:0xaac300` の第 4 引数が ctx+0x88。呼出元は `fle:0xaba880` の **1 箇所のみ**で `xor r9,r9` (= 0)。→ DB 生成経路で 0x80 は立たない。event 28 の値も同じ引数で `table[0] = 1` |
| project 側 (`fle:0xf3c870`) | flags = `ctx+0x34 & 0x30d` に `0x10 / 0x20 / 0x40 / 0x80` を OR。0x80 は「native kind == 2 かつ plugin 能力 bit 0x8000 かつ非 export mode」の時のみ。読込側 (`fle:0xf46490`) の 0x80 は同条件の plugin だけに効き、Wrapper 配下の VST には load 経路上の影響なし |

→ 生成器の `buildWrapperHeader` (`u32@8 = 2`、generator のとき `u16@16 = 0x10`、他 0) は FL の DB 経路と一致。**0x80 を出す必要はない**。shipped 実例の 0x80 は project writer 経路 (native plugin) 由来と説明できる。

## 4. 「生成 .fst で VST2/VST3 を起動できるか」の段階別判定

| 段 | 内容 | 判定 |
|---|---|---|
| A. chunk の受理 (`fw:0x870da0` → `0x875af0`) | version 8 は 5–12 内。生成 5 entry + 実機 OTT.fst の chunk は全て既知 id のみ・末尾まで消費。reader 模型 test 10/10 | **確 (静的 + 模型)** |
| B. plugin ファイルの特定 | Wrapper は `fw:0x871fe0` で FL host (`param_1+0xbc` の dispatcher, message 7) に `"<path>\|class=C\|name=N\|vstid=M\|guid={…}\|id=…"` を送り、応答 `"<path>\|class=\|magic=\|guid="` を得る。応答が空で class −1 なら失敗。FL 側は `fle:0x915750` (locate: `.Plugins.ini` / `Installed\*.NFO`) と `fle:0x915220` (応答整形) | 書式は **確**。FL 側 handler が msg 7 のどこに繋がるか (`0x915750` の呼出元 `fle:0x12b9e70` / `0x13173a0`) と DB 受理は **未実行** (#267) |
| C. module の生成 | `fw:0x86e1a0` が class から factory を引き (`fw:0x87c980` → TVSTPlugin ctor, hint = 0)、PE 事前検査 → `LoadLibrary` → `main` → `effOpen` … (`tools/hostbridge/HOSTBRIDGE.md` §1) | 既存解析の範囲。wasm 側は仮想 FS の PE スタブが前提 |

失敗時の観測可能な挙動 (書式が崩れた場合の症状): record 50 欠落 → **拒否でなく class 0 (VST2 fx) として検索** (VST3 chunk が誤配線)、version > 12 → 拒否、record 55 の `/` は `\` に正規化、ANSI (version 8) の非 ASCII 名はコードページ依存。

## 5. 文書・生成器への含意

| 対象 | 内容 |
|---|---|
| `nfo/FORMAT.md` §8 | 先頭 u32 8 = **format version** (許容 5–12、Wrapper 自身の writer = 12、DB の FL 11.5.5 writer = 8)。record 1/30/31/32/53/57 の欠落時既定、57 の意味を追記 (本 PR で更新) |
| `nfo/FORMAT.md` §9・`nfo/REPORT.md` §6-2/3 | 未確認から解消へ (本 PR で更新、本文は複製せず本書へリンク) |
| `tools/flp` `parseWrapperData` | `kind (8 = VST2, 10 = VST3)` は誤り (VST3 の実機 OTT.fst も 8)。`id 50` を必須とする点も Wrapper と異なる (Wrapper は欠落を class 0 とする)。修正済み (#110: `version` / `plugclass` に改名、`parseWrapperChunk` で gate と record walk を Wrapper に合わせた。検証は `tools/flp/test/wrapper_real.test.ts`) |
| 生成器 (`nfo/src/fst.ts`) | ASCII の出力は**変更なし** (version 8・ANSI は FL 11.5.5 writer と同一)。非 ASCII の扱いは #549 で追加 (§9) |

## 6. 検証

検証起点 commit・実測は下表 (コミット済み HEAD の clean worktree で実行)。

検証起点 commit: **`cf2ddd4`** (コード・evidence・文書が確定した commit。以降の commit は本表の数値追記のみ)。`$RUNNER_TEMP` 配下の detached worktree (`git worktree add --detach … cf2ddd4`、`work/` なし = venv 新規作成から) で実行、4 コア runner、fl-win64 展開済み (`FL_WIN64_DIR`)。

| 実行 | 結果 | 所要 (wall) | load average (1/5/15 分) 開始 → 終了 |
|---|---|---|---|
| `bash h10_e2e.sh` 1 回目 (venv 新規作成込み) | exit 0 | 50.13 s | 0.02 0.48 0.75 → 0.58 0.56 0.76 |
| 同 2 回目 | exit 0 | 49.96 s | 0.58 0.56 0.76 → 0.82 0.63 0.77 |
| 同 3 回目 | exit 0 | 50.12 s | 0.82 0.63 0.77 → 0.92 0.69 0.79 |
| 範囲 (n = 3) | exit 0 × 3 | **49.96–50.13 s** | 並列数 1 (他 run なし) |

| 検査 | 実測 |
|---|---|
| PE バイト検査 `h10_check.py` (fw_a + fw_b) | **62 PASS / 0 FAIL** (31 × 2 build) |
| FLEngine PE バイト検査 `fle_check.py` | **15 PASS / 0 FAIL** |
| evidence 文面検査 `evidence_check.py` | **19 PASS / 0 FAIL** |
| ネガティブコントロール | **10 / 10 検出** |
| typecheck (`tsc -p h10/tsconfig.json`) | エラー 0 |
| reader 模型 test (`node --test test/*.test.ts`) | tests 10 / pass 10 / fail 0 / skipped 0 |
| 既存 `nfo_e2e.sh` (`SKIP_H4=1`、本 PR の文書変更後) | exit 0 (回帰なし。`SKIP_H4=1` は Chrome 段 `h4_e2e.sh` を除外) |

別アルゴリズムによる突合: `h10_check.py` (capstone で dispatch tree を asm から抽象実行) と `evidence_check.py` (Ghidra decompile 文面の正規表現) は同じ主張を独立に検査する。record 57 の「唯一の使用は bitness 不一致分岐」は前者が PE バイト、後者が decompile から確認。


数え方: 「checks」= 各 `*.py` が出す `PASS`/`FAIL` 行数 (h10_check は build ごとに 31 件 × 2 build = 62、fle_check 15、evidence_check 19)。「neg」= `--break <key>` で期待表の 1 要素を壊し、検査が FAIL を検出した数 (検出 = exit 0)。reader 模型 test = `node --test test/*.test.ts` の `tests`。

ネガティブコントロール (全て「壊すと検出」を確認):

| 対象 | 壊した内容 | 検出された FAIL |
|---|---|---|
| `h10_check --break rec57size` | record 57 のサイズを 4 → 8 | 1 件 (`record 57 = fixed/4`) |
| `h10_check --break ver` | version gate の上限 12 → 13 | 1 件 |
| `h10_check --break ctor6` | hint 引数 0 → 1 | 1 件 |
| `h10_check --break rec51` | reader から record 51 を除外 | 2 件 |
| `fle_check --break flag80 / caller / type31` | 0x80 の源 / 呼出元数 / 種別値 | 各 1 件 |
| `evidence_check --break d4use / callers / ext` | record 57 の使用箇所 / ctor 呼出元 / 拡張子表 | 1 / 1 / 4 件 |
| reader 模型 test (NEGATIVE 5 件) | version 13・−1・4 / record 50 欠落 / 未知 id・不揃いな 31 / ANSI↔UTF-8・path の `/` / 切詰め | 想定どおりの status・class・文字列 |

**範囲内**: 上記の静的検査、reader 模型と生成 DB 5 entry・実機 OTT.fst の整合。**範囲外**: Wrapper・FLEngine の実行 (lift 済み boot 前)、`block23676` の Ghidra decompile、KH 45 entry (`product_index.json` 非同梱)、AU/CLAP 経路、FL 側 msg 7 handler の特定。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL 側 msg 7 handler の特定 (`fle:0x915750` の呼出元 `0x12b9e70` / `0x13173a0`、後者 (71,339 B) は decompile が timeout (120 s)) と、Wrapper 問い合わせ書式 (§4-B) が生成 DB を引けるかの実行検証 | 「起動できる」の最終確認 (段 B) | (a) #267 [HB-H4d] にコメント |
| `tools/flp` の `kind` 呼称・id 50 必須・id 57/58 の扱い | 実データ解析で誤ラベル | (a) #110 [L-7] にコメント |
| `block23676` (Wrapper 別ビルド) の Ghidra 解析と差分の意味 | 本解析は PE バイト検査のみ | (a) #94 [HB-H4] にコメント |
| version 8 は ANSI: 非 ASCII の plugin 名/パスは `CP_ACP` 依存 | **#549 で解決 (§9)**: version 8 は ASCII 限定を生成器で強制、非 ASCII は version 9–12 (UTF-8) を opt-in | 解決済 (残件は §9 末尾) |
| record 2 の個別 option bit の名前 (binary 由来の特定) | option を生成器から指定したい場合のみ | (c) 親 #99 への提案 (現状は 0x400000 で既定任せ) |

## 8. 次タスク提案

| # | チケット | 要点 |
|---|---|---|
| 1 | #267 [HB-H4d] | boot 貫通後、生成 DB を FL 実物 reader と Wrapper の msg 7 経路で引かせる (本書 §4-B の書式を入力に使える) |
| 2 | [HB-H4] #94 | Wrapper lift 時に factory (`fw:0x87c980`) と export 事前検査の PE スタブ要件を本書 §3-② で確定済みとして扱う |

## 9. 非 ASCII の名前/パス: version 8 (ANSI = CP_ACP) と shimx の整合 (#549 / [HB-H14])

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (文字コード方針の確定。lift・IR pass は使っていない)。

**結論: (a) を既定にする。version 8 の chunk は ASCII のみ (生成器が非 ASCII を例外で拒否)、非 ASCII が要る時だけ version 9–12 (UTF-8) を明示 opt-in (`chunkVersion` / `gen.ts --chunk-version`)。** 理由: version 8 の文字列は Wrapper が `CP_ACP` で読むため、生成時に reader 側の ACP を知る手段が無い (下表: shimx 既定 1252 では CP932 のバイト列が文字化けする)。version 9–12 は `CP_ACP` に依存しない。

| 項目 | 実測 (コミット済み HEAD) |
|---|---|
| shimx の `CP_ACP` 既定 | **1252** (`tools/shimx/src/str.c` の `g_acp = 1252`)。実 `str.c` を emcc ビルドした probe (`analysis/shimx_acp_probe.c`) の `GetACP()` = 1252。`shimx_set_acp(932)` 後のみ 932 (`GetACP()` = 932)。`shimx_set_acp` の**ランタイム呼出元は無い** (shimx 外の ts/mjs/js/c/h に実行時の呼出なし)。clean worktree (`065e825`、本 REPORT 自身を除く) の `git grep -n shimx_set_acp` は **14 件 / 11 ファイル**: shimx 側 9 件 = `shimx.h:1141` (宣言)・`str.c:2,13` (コメントと定義)・`exports.txt:568`・`README.md:35`・`inventory.md:76`・`REPORT_SHX-T8.md:34`・`test/test_shord.inc:140,150`、h10 側 5 件 (本 PR 追加) = `analysis/shimx_acp_probe.c:3,13`・`analysis/neg_nonascii.sh:53`・`src/wrapper_reader.ts:75`・`test/nonascii.test.ts:51`。実際に**呼ぶ**のは `tools/shimx/test/test_shord.inc` のユニットテスト (140: 932、150: 1252) と、計測専用の `analysis/shimx_acp_probe.c:13` (本 PR 追加) だけで、ランタイム経路では呼ばれない → wasm ランタイムは現状 1252 固定 |
| 対応 codepage | 1252 / 437・850 (近似) / 28591 / 20127 / 65001 / **932** (SHX-T8、`REPORT_SHX-T8.md` §15.3)。936・949・950 等は `ERROR_INVALID_PARAMETER` |
| shimx 実出力 ↔ reader 模型 | 6 ベクタ (日本語パス・日本語名・カタカナ・半角カナ・`表` の trail byte = 0x5C・`Café`) × ACP 2 通り (1252・932) = **12 件で shimx `MultiByteToWideChar(CP_ACP)` の UTF-16 と `wrapper_reader.ts` の復号が全件一致、不一致 0**。入力バイト列は Python 標準 codec (`cp932`/`cp1252`、shimx の表と独立実装) 由来 |
| version 8 + CP932 バイト | ACP 932 で原文に復元、**shimx 既定 1252 では復元しない** (例 `93fa967b` → `“ú–{` 相当。ネガコン) |
| version 9–12 + UTF-8 | version 9・10・11・12 の各々で ACP 1252・932 の双方 `name`/`path`/`vendor` が原文一致。同じ UTF-8 バイトを version 8 に書き換えると復元しない (ネガコン) |
| 生成器 | version 8 (既定) で `record 54/55/56/58` に非 ASCII → `throws` (どの record かを例外文に含む)。`version` は 8–12 のみ (範囲外 `throws`)。ASCII 入力の出力は従来と同一 (既存 test 全 PASS、`nfo_e2e.sh` 回帰なし) |

**定義**: ベクタ = `test/nonascii.test.ts` の `V`。「一致」= probe の UTF-16LE 文字列と模型 `TextDecoder` の復号が `===`。模型の `windows-1252`/`shift_jis` は WHATWG 実装 (shimx の表と独立)。

**検証・ネガコン**: `bash h10_e2e.sh` が probe を emcc でビルドして `test/nonascii.test.ts` (7 件) を走らせ、さらに `analysis/neg_nonascii.sh` が**複製に 1 箇所ずつ変異を入れて FAIL を確認** (対照: 無変異複製が PASS) — 生成器の ASCII ガード除去 / version 範囲の開放 / UTF-8 を latin1 で出力 / reader の v9 UTF-8 判定の無効化 / reader の ACP 無視 / shimx 既定 ACP を 932 に / `shimx_set_acp` を無効化、の **7 / 7 検出**。検出されないと e2e は非 0 で終わる。

**実測 (検証起点 commit `9197a1c`、`$RUNNER_TEMP` の detached clean worktree、4 コア runner、fl-win64 + toolchain-emsdk 展開済み、並列数 1)**: `bash h10_e2e.sh` n = 3 → exit 0 × 3、wall **77.40–77.55 s** (77.40 / 77.55 / 77.54)、load average (1/5/15 分) 開始 0.46 0.34 0.16 → 終了 1.21 0.81 0.40。内訳は各回: PE 検査 62 PASS / 0 FAIL、FLEngine 15 / 0、evidence 19 / 0 (§6 と同値)、reader 模型 + 非 ASCII test **tests 17 / pass 17 / fail 0 / skipped 0** (§6 の 10 件 + 本件 7 件)、`neg_nonascii.sh` 7/7 検出 + 対照 PASS。`nfo` 側: typecheck エラー 0、`node --test test/*.test.ts` tests 40 / pass 36 / fail 0 / skipped 4 (skipped = 実機素材 `HAVE_FL` 無しの既存 4 件)、`SKIP_H4=1 bash nfo_e2e.sh` exit 0 (生成 5 entry・12 files・readerAccepted 5、回帰なし)。範囲外: FL 実機/FLEngine 上での version 9–12 chunk 受理 (上表の未解決 1 行目)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL 自身の reader (`fle:0xf46490`) が version 9–12 の chunk を受理するか (Wrapper は 5–12 を受理 [確])。FL は 213 を不透明な塊として Wrapper へ渡すと推定だが**未確認** | version 9–12 の opt-in を実機 FL で使う前に必要。既定 (version 8・ASCII) には影響なし | (a) #267 [HB-H4d] にコメント (boot 貫通後に実行検証) |
| wasm ランタイムが `shimx_set_acp` を呼ぶ箇所が無い (ACP = 1252 固定)。非 ASCII の `.nfo`/`.Plugins.ini` は UTF-8 BOM (`valuefile.ts`) で別系統 | 非 ASCII の plugin を載せる時は version 9–12 が必須。ユーザ名等が日本語の**実機パス**を DB に入れる要件が出た場合の仮想 FS 側の扱いは別論点 | (c) 親 #99 への提案 (非 ASCII パスは現 spec 範囲外と明記) |
| Wrapper の他の ANSI 文字列 (plugin 名の UI 表示等、chunk 外) の `CP_ACP` 利用 | 本件は chunk の 4 record のみ | (c) 親 #99 への提案 |
