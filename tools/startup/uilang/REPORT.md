# REPORT — ST-T19 (#591): GetUserPreferredUILanguages の返値実測 + lang-svg の参照元 + Windows 標準フォントの要求一覧

検証起点: 親 `main` = `0865903`。素材 = `fl-win64` (FL Studio 26.1.7.5653、`FLEngine_x64.dll` = `extracted/block00031_PE.bin`)。
既知類型 (`docs/DEFECTS.md`) との関係: **該当なし** (lift/IR pass は扱わない。FLEngine の静的解析 + shimx の API 実測)。
親: #39 (ST-T14、`tools/startup/loadpaths/REPORT.md` §6 の未解決 3 件に対応)。

## 0. 結論

1. **shimx の返値を実測し、FL が使う呼び方 (flags=8・2 段階) でも `en-US` を返す。** 既定ロケールの `GetUserPreferredUILanguages` は `"en-US\0\0"` (num=1・cch=7)。
   FL は `zh` のときだけ `Program language` を自動書込みする (§1)。shimx は `zh-CN` を返さないので **既定では書込みは起きず、言語は `en` 固定**。
   実測中に **shimx のバグを 1 件発見・修正**: `shimx_set_locale` で表に無い LCID (例 `0x0804`) を指定すると `GetUserPreferredUILanguages` が NULL 参照で wasm trap。表に `zh-CN (0x0804)` を追加し、未知 LCID は `en-US` に落とすようにした (`tools/shimx/src/locale.c`)。
2. **`lang-svg` の参照元を関数単位で特定した。** `.svg` を参照する関数は `0xdceea0` だけ。これは **`TToolbarForm.FlagBtnPaint`** (メインツールバーの言語旗ボタンの描画) の本体 (§2)。読むのは選択中の 1 言語の `<lang>.svg` だけ。
3. **標準フォントの要求を一覧化した** (§3)。FL 自身が `C:\Windows\Fonts\segoeui.ttf` 等の**存在確認**をして、無ければ Artwork 同梱の OpenSans 等に落とす実装になっている (起動時のフォント表 0x668d30)。ここは VFS に Windows フォントが無くても**FL 側で解決する**。
   GDI の face 名で直接要求している箇所 (Tahoma / Arial / MS Sans Serif / Segoe UI / Calibri / Microsoft Sans Serif / Lucida Console) は別で、代替マッピングが必要 (#186 の入力になる表を §3.3 に置く)。
4. 全受入条件に対応する成果物を置いた。ただし「実 boot での動的確認」は boot が `CreateFruityInstance` に未到達のため未達で、静的根拠 + shimx 実測まで (§5)。

## 1. GetUserPreferredUILanguages (受入条件 1)

### 1.1 FL の呼び方と分岐 (`verify_uilang.py` が DLL のバイト列で照合: A・B・C)

- `GetUserPreferredUILanguages` は `FLEngine_x64.dll` の**遅延 import** (`.didata`、スロット 0x1976380 → thunk 0x4237a0)。呼出元関数は **0x9df190 のみ**、その呼出元は **0x9deaa0** (言語初期化) と **0x1265c30** (起動ログ) の 2 つだけ。
- 0x9df190: `flags = 8` (`MUI_LANGUAGE_NAME`) で **2 回**呼ぶ (1 回目 `buf=NULL` でサイズ → `GetMem(cch*2)` → 2 回目で取得)。戻りの先頭の NUL 終端文字列だけを使い、引数 `dl=1` なら最初の `-` の手前までに縮める (`zh-CN` → `zh`)。
- 0x9deaa0 の分岐:

```
ov = 引数 rdx (呼出元 0x13754b0 が渡す [0x15e43a8] の文字列。実体は未特定。既定は空と推定)
if ov == 'zh' (0x9deca8 を WideChar 毎 -50 して得る 'zh'。0x9deb30 の test eax / jne 0x9deb5d):
    ホストの 2 フィールド (+0x18 / +0x20) を設定して 0x9debab へ (下の 3 行を丸ごと飛ばす。意味は未追跡)
else:
    r = 0x9dece0(…, 0)                             ← レジストリ Software\Image-Line\Shared\Language の 'Program Language' (既定 空)
    if r が空 (0x9deb68 cmp / jne 0x9debab):
        os = 0x9df190(縮める)                      ← GetUserPreferredUILanguages
        if os == 'zh' (0x9deb85 の 0x414e70 比較。0x9deb8c jne 0x9debab で不一致なら保存を飛ばす):
            0x9df010('zh', …)                      ← Program language / Regional note names / Accidental Mode の 3 値を書く
lang = 0x9dece0(…, 1)                              ← 'Program Language' (既定 'en' = 0x9dedb4)
→ 0x9de620(lang) で <lang>.moe を探索 → 在れば適用、無ければ 0x9de810 のフォールバック (組込み英語)
```

- 先頭の `ov == 'zh'` 分岐は、上書き値が `zh` のとき OS 言語の自動検出と書込みを飛ばす。**`[0x15e43a8]` が空 (既定の推定) なら不一致で通常経路**。実体を確かめていないので、本結論は「上書き値が `zh` 以外のとき」に限る (§5 の未解決)。

- 0x9df010 が書くのは `Software\Image-Line\Shared\Language` 配下の **`Program language` / `Regional note names` / `Accidental Mode`** の 3 値 (C7 で関数内リテラルから確認)。
- 0x1265c30 は起動ログ `"<OS> display language: %s"` 用で、縮めずに (`dl=0`) 呼ぶ。分岐には影響しない。

### 1.2 shimx の返値 (実測。`probe.c` が上記の呼び方をそのまま再現)

`tools/startup/uilang/probe.c` を shimx 全 .c と同じ emcc フラグ (ST) でビルドし node で実行。`r1`/`r2` = 1・2 回目の戻り、`num` = 言語数、`cch` = 必要/書込み文字数 (multi-sz の末尾 NUL 2 個を含む)。

| 設定 | 戻り (`full`) | FL の縮約 (`lang`) | Program language の自動書込み | 備考 |
|---|---|---|---|---|
| 既定 (`shimx_set_locale` 未呼出) | `en-US` | `en` | **なし** | r1=r2=1, num=1, cch=7, 末尾 NUL 2 個 |
| LCID 0x0409 (en-US) | `en-US` | `en` | なし | 同上 |
| 0x0411 (ja-JP) | `ja-JP` | `ja` | なし | `ja` は OS 言語での自動選択の対象外 → 言語は `en` のまま |
| 0x0407 / 0x040c / 0x0c0a (de/fr/es) | `de-DE` / `fr-FR` / `es-ES` | `de` / `fr` / `es` | なし | 同上 |
| **0x0804 (zh-CN)** | `zh-CN` | **`zh`** | **あり** | → `zh.moe` (847827 byte 復号後) を起動時に全量読込 |
| 0x0412 (ko) / 0x042a (vi) / 0x1234 (表に無い) | `en-US` | `en` | なし | shimx が持たない LCID は `en-US` |

- **含意**: wasm ランタイムが既定で `shimx_set_locale` を呼ばない限り、`Program language` は書かれず `en` (組込み英語) 固定。ブラウザの言語に追従させる場合 (`navigator.language` → LCID)、**`zh` を渡したときだけ起動時に `zh.moe` を読み、レジストリが書き換わる**。`ja`/`de`/`fr`/`es` を渡しても言語は変わらない (自動採用は `zh` のみ)。
- ja/ko/de/fr/es/vi を使うには `Program Language` を seed する必要がある (`tools/startup/vreg` の `build_seed.py` `OVERRIDES`。#39 §6 の既起票項目)。
- shimx 側の追加: `locale.c` に `zh-CN` を追加、`loc_cur()` で未知 LCID を `en-US` に落とす。`tools/shimx/test/test_link.c` に 3 アサーション追加 (zh-CN → `zh-CN`・cch=7 / 未知 LCID → `en-US` / 復元後 `en-US`)。

## 2. lang-svg の参照元 (受入条件 2。`verify_uilang.py` D)

| 項目 | 内容 |
|---|---|
| `.svg` リテラルを参照する関数 | **0xdceea0 のみ** (`.pdata` 関数 57816 件を走査) |
| 0xdceea0 の正体 | `TToolbarForm.FlagBtnPaint` の本体。0xdceea0 への直接 call は 0 件。`0xdcf270` (同名メソッドのエントリ) が `lea` で 0xdceea0 のアドレスを取り、`0x5262d0` (遅延実行登録) に渡す |
| 名前の根拠 | `0xdcf270` を指す `.reloc` DIR64 ポインタが 1 件 (0xdc7cb0) あり、その直後の ShortString が `FlagBtnPaint` (Delphi published method 表)。同じクラス表に `ToolbarLanguagesMenu` / `FlagBtnPanel` / `FlagBtn` / `FlagBtnBeforePopup (0xdcf500 → 0xdcf510)` |
| 処理 | `<lang> + ".svg"` (0xdcf238) を検索区分 **0x40f (Languages)** で探し (0x7585c0)、在れば SVG として読んで旗ボタンの大きさに描画 (0x66dcf0 で読込、0x6cd6e0 / 0x6bb2f0 / 0x6c0820 で描画)。無ければ `<lang>` の文字列をボタンのキャプションにする |
| `<lang>` の決め方 | `[0x15e43a8]` (上書き値。実体は未特定) が非空ならそれ、空なら 0x9dece0 = `Program Language` (既定 `en`) |
| 読む実ファイル | **選択中 1 言語の 1 ファイル** (既定 `en.svg`)。8 ファイル 4025 byte のうち起動で全部読む理由は無い |
| 呼出点の位置づけ | 旗ボタンの `Paint` (メッセージループ経由)。初回描画が起動中に走るかは静的には断定できない → `phase` を `unresolved` → **`boot-conditional`** に更新 (`tools/startup/loadpaths/loadpaths.json`) |

別経路 (0x9df680 → 0x9df270) の列挙 (`Languages` 区分の `*.moe`/`*.mo` を並べる言語メニュー用) は `.svg` を読まない。旗の SVG は `FlagBtnPaint` だけ。

## 3. Windows 標準フォント (受入条件 3。`verify_uilang.py` E)

### 3.1 FL 自身が存在確認して代替するもの (0x668d30 = フォント表初期化、呼出元 0x66d050 = 起動)

0x668d30 は `SHGetFolderPathW(CSIDL_FONTS = 0x14)` (0x81bca0、失敗時 0x81bb20 のフォールバック) でフォント dir を取り、`<dir>\<name>.ttf` の存在を 0x819110 (`SetThreadErrorMode` 付き `GetFileAttributesW`) で確認する。**無いと `OpenSans-*` 等 Artwork 側に落ちる**。

0x668d30 内のリテラル出現順 (`fonts.json` の `select_sequence_0x668d30`。`FileExists` 直後の `jne` の飛び先も機械抽出済み) を、`P_*` ごとの並びとして読むと次のとおり。**`P_*` ラベルとの対応は出現位置の近さからの読みで、各ブロックの意味までは追っていない**。

| ブロック (出現順) | 存在確認する Windows 側ファイル | 続くリテラル (VA) |
|---|---|---|
| P_SmallBold / P_Small / P_Normal / P_NormalBold / P_TitleBar 付近の各ブロック | `segoeui.ttf` (0x6690df ほか。`GetFileAttributesW` 2 回) | `OpenSans-Regular` (0x6693e4 / 0x669909 / 0x66a475 / 0x66ac05 / 0x66b345) |
| P_Tiny / P_Tiny2 | `segoeui` (0x669c9d) → **`tahoma` (0x669ea4)** | `OpenSans` は続かない (この枝の落ち先は `tahoma`。それも無い場合は未追跡) |
| P_NormalLight | `segoeuisl.ttf` (0x66a653 / 0x66a69f) | `OpenSans` は続かない (落ち先は未追跡) |
| P_DigitWheel | — | `OpenSans-CondLight` (0x66b76c) |
| P_Monospaced | `consola` (0x66ba22) → `lucon` (0x66bbc9) | **Artwork に等幅フォントは無い** (§3.3) |
| P_ILGlyphs / P_WebSymbols / P_DescriptionLarge | — | `ILGlyphsEx.ilfont` / `WebSymbols-Regular.otf` / `PT_Sans-Web-Regular.ttf` (Artwork 固定) |

- `verify_uilang.py` が保証するのは「0x668d30 がこれらのリテラルを参照すること」と、`segoeui.ttf` 不在の枝 (0x6691ff `je 0x6693b8`) が `OpenSans-Regular` (0x6693e4) に至ることまで (E1・E6・E7)。表中の他の対応は目視の読み。

- **VFS 方針**: `C:\Windows\Fonts\*.ttf` は pathreg 既定表で `/c/Windows/...` に落ちる (`tools/shimx/pathreg/REPORT.md` の `C:\Windows\notepad.exe` → `/c/Windows/notepad.exe` の例からの推定。Fonts 配下の個別確認はしていない)。VFS に置かなければ `GetFileAttributesW` は不在を返し、`segoeui.ttf` の枝は FL が自分で OpenSans-Regular に落とす → **この枝はマッピング不要** (実 boot での確認は §5)。**Windows フォント実体を置かない** (#186 の PM 判断と整合)。

### 3.2 GDI の face 名で直接要求しているもの (関数単位。`fonts.json` に全リテラル参照)

| face 名 | 参照関数 (VA) | 備考 |
|---|---|---|
| Tahoma / MS Sans Serif / Arial / Segoe UI (+ `segoeui`) | 0x667830 (`P_*` の `TFont` 既定設定。呼出元 0x667c10) | Segoe UI 側に `segoeui` の名前も |
| Segoe UI / Calibri (+ `segoeui`) | 0x818560 (呼出元 0x81d340) | |
| Tahoma / MS Shell Dlg 2 | 0x5d1ac0 (呼出元 0x5d2680) | |
| Microsoft Sans Serif | 0x7a2dc0 (呼出元 0x7a41d0。お気に入り UI) | |
| Lucida Console | 0x8b3a10 (呼出元 0x56b400) | |
| Arial | 0x7ab330 / 0x7af220 / 0xa47920 / 0xbb75c0 / 0xd402d0 / 0xdfe7b0 / 0x1075770 / 0x114fb70 / 0x1196c00 | 計 10 関数 + 0x667830 |
| `segoeui` のみ | 0x76c410 | |

### 3.3 代替マッピング案 (提案。`docs/LEGAL.md` §3.1 の本文ありのフォントのみ。#186 の PM 判断 (OSS 代替) の範囲内。未検証)

| 要求 | 代替案 (VFS 内 = 同梱済み) | ライセンス (LEGAL §3.1) | 注意 |
|---|---|---|---|
| Segoe UI / Tahoma / Arial / Calibri / Microsoft Sans Serif / MS Sans Serif / MS Shell Dlg 2 | `OpenSans-Regular.ttf` (FL 自身が segoeui.ttf 不在時に選ぶ。Tahoma 等の GDI 名にも流用する案) | **Open Sans の本文は LEGAL §3.1 の一覧に無い** (Open Sans **Condensed** の Apache-2.0 のみ) → 同梱前に確認 | 幅が Tahoma より広い。幅計算の差は #186 で測る |
| Lucida Console / Consolas (P_Monospaced) | VFS 内に等幅フォントは**無い** | — | OFL/Apache の等幅 (例 Cousine・DejaVu Sans Mono) を別途調達する判断が要る (PM) |
| 細字 (segoeuisl) | `OpenSans-Light.ttf` (VFS 内に在る) | 上に同じ | 0x668d30 の落ち先は未追跡 |

## 4. 検証 (実測)

`bash tools/startup/uilang/e2e.sh` (前提: `FL_WIN64_DIR`、`/opt/emsdk`)。コミット済み HEAD をクリーン worktree に展開して実行した結果は §4.1。

| 項目 | 内容 |
|---|---|
| `verify_uilang.py` | 49 件の照合 (A: 遅延 import スロット・thunk・呼出元 / B: flags=8・2 回呼出・呼出元 2 関数 / C: 呼出順 read→os→save→read・'zh' 符号化・保存を飛ばす分岐・書込む 3 値 / D: `.svg` 参照関数・直接 call 0・lea・published 表の名前 / E: フォント表の分岐・SHGetFolderPath の CSIDL_FONTS・存在確認・落ち先) |
| ネガコン (DLL のバイトを壊す) | zh の符号化 1 byte 反転 → C4 / `jne` を `je` に反転 → C5 / `mov ecx, 8` を 4 に → B2 / published 表ポインタ 1 byte → D5 / spec の呼出元期待値 → A3。**5/5 が期待した ID で FAIL** |
| probe (shimx 実測) | 10 ケースが期待表と一致 (`zh-CN` だけが `fl_writes_program_language=1`)。期待表 1 件反転で検査器が検出 (NC 1/1) |
| 既存回帰 | `bash tools/shimx/test.sh --quick` (shimx 687 公開関数 × MT/ST × M4 互換 × fail-fast) 全 PASS (修正前 16.09 秒・修正後 16.19 秒、exit 0)。`bash tools/startup/loadpaths/e2e.sh` PASS (readers 34・fail 0) |

### 4.1 クリーン HEAD での再現

(下記「検証結果」に実測を追記する。)

## 5. 検証範囲 / 範囲外 / 未解決

**検証範囲**: DLL の静的構造 (関数境界・RIP 相対の文字列参照・直接 call・遅延 import・`.reloc`・published method 表) と、shimx API の返値 (node 上の wasm 実行)。
**範囲外**: FL の実行。boot が `CreateFruityInstance` に未到達 (`tools/flelift/boot/REPORT.md` §0) のため、実際に呼ばれる/呼ばれない・ファイル不在時の挙動は動的に確認していない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[0x15e43a8]` (言語の上書き値) の実体 (起動引数由来か) と既定値。`zh` のときの 0x9deaa0 先頭分岐の意味 (+0x18/+0x20 の設定)。`FlagBtnPaint` の初回描画が起動中か | §1 の「既定は en 固定」は上書き値が `zh` 以外という前提。`lang-svg` の phase も絞れない | #105 (boot 到達後の `assettrace`) |
| 0x668d30 の `segoeuisl.ttf` / `tahoma` / `consola` / `lucon` 不在時の最終的な落ち先、`P_*` ごとの対応の確定 | P_Tiny / P_NormalLight / P_Monospaced の表示 | #186 (GDI テキスト実描画。本 REPORT §3 を入力にする) |
| Open Sans 本体のライセンス本文が LEGAL §3.1 に無い | OpenSans を代替の本命にする前提 | LGL 系 (#86 THIRD_PARTY_NOTICES に合流) へ PM が起票 |
| 等幅フォントの調達 (VFS に無い) | P_Monospaced | PM 判断 (#186 の同梱方針に追記) |
| ブラウザ言語 → LCID の渡し方 (`zh` のときだけ起動時に `zh.moe` を読む) | zh ブラウザの初回起動が重くなる (847827 byte) | `tools/runtime` 側の子チケットを PM が起票 (本 REPORT §1.2 を入力) |
| `loadpaths` の tier (`lang-moe`=T2 推奨) との整合 | `zh` 環境だけ起動で読む | #105 の実トレースで答え合わせ |

DEFECTS.md 追記案: なし (新しい silent miscompile 類型は見つけていない。shimx の NULL 参照は lift 欠陥ではなく shimx の表引き漏れ)。

## 6. 次タスク提案

1. boot が `CreateFruityInstance` を抜けた時点で `assettrace` に本 REPORT の A〜E (呼出順・ファイル不在時の落ち先) を答え合わせさせる (#105)。
2. #186 に §3.2 / §3.3 を入力として渡し、`CreateFontW` の face 名 → OSS フォントの写像を実装する。
3. ランタイムの `shimx_set_locale` 呼出方針 (既定は呼ばない = `en` 固定) を `tools/runtime` に明記する。
