#!/usr/bin/env python3
"""最小ブートセット推定: FLEngine_x64.dll の文字列証拠 + ツリー構造規則で全ファイルを階層化する。

tier:
  T0   起動必須 (エンジン初期化/スキン/設定/システム fst をエンジンが起動時に開く: 文字列リテラルで直接裏取り)
  T0p  起動時に高確率 (ディレクトリ列挙 or 既定テンプレート読込から導出; 実機トレース無しゆえ推定)
  T1   初回操作で必要 (ブラウザ/プラグイン生成/ヘルプ/言語切替 等)
  T2   遅延可 (サンプル/デモ/プリセット本体/プラグイン固有データ)
  X    VFS 配信対象外: lift(wasm 化) / rebuild(upstream 再ビルド) / skip(非実行)
         ※ lift/rebuild は manifest に stub (size のみ) として載せる。skip は載せない。

出力: bootset/bootset.json (規則+証拠+集計), bootset/BOOTSET.md, work/tiers.json (path→tier; packager 入力)
実機の FL を動かして open() を採る手段が無い (wine 無し/ライセンス) ため『推定』。実トレースは下流チケット (§REPORT)。
"""
import os, re, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); WORK = os.path.join(ROOT, 'work')

W = [json.loads(l) for l in open(os.path.join(WORK, 'inv_win.jsonl'))]
ST = json.load(open(os.path.join(WORK, 'engine_strings.json')))
WIN_STR = set(ST['win']['utf16']) | set(ST['win']['ascii'])
WIN_STR_L = {s.lower() for s in WIN_STR}


def has(lit):
    l = lit.lower()
    if l in WIN_STR_L:
        return True
    # 部分一致 (Delphi 文字列は前後に連結されることがある)
    return any(l in s for s in WIN_STR_L if len(s) < 400)


# (tier, glob(path は / 区切り・大小無視), 証拠リテラル[], 理由)
RULES = [
    ('T0p', 'Artwork/Skins/Default/StartSnd.wv', ['StartSnd.wv'], '起動音 (flags&8 の条件付き; ST-T14 §4 #4)'),
    ('T1', 'Artwork/Skins/Default/BigFruit.png', ['BigFruit.png'], '操作時のみ (ST-T14 §4 #5)'),
    ('T1', 'Artwork/Skins/Default/ClipHanger.png', ['ClipHanger.png'], '操作時のみ (ST-T14 §4 #5)'),
    ('T1', 'Artwork/Skins/Default/PickerChan.png', ['PickerChan.png'], '操作時のみ (ST-T14 §4 #5)'),
    ('T1', 'Artwork/Skins/Default/ScopeGradient.bmp', ['ScopeGradient.bmp'], '操作時のみ (ST-T14 §4 #5)'),
    ('T1', 'Artwork/Skins/Default/RenderSnd.wv', ['RenderSnd.wv'], '操作時のみ (ST-T14 §4 #5)'),
    ('T0', 'Artwork/Skins/Default/*', ['Artwork\\Skins\\', 'Title.png'], '既定スキン (起動画面/UI 素材)'),
    ('T0', 'Artwork/Wallpapers/Default.txt', ['Default.txt', 'Wallpapers'], '起動中のフォーム生成で読む既定壁紙定義 (ST-T14 §4 #2)'),
    ('T0', 'Artwork/Themes/thmDefault.png', ['thmDefault.png'], '既定テーマ画像'),
    ('T0', 'Artwork/Themes/tweak_default.png', ['tweak_default.png'], '既定テーマ調整画像'),
    ('T0', 'Artwork/Fonts/Fruity microfont.ttf', ['Artwork\\Fonts', '.ttf'], 'マイクロフォント'),
    ('T0', 'Shared/Artwork/Fonts/PT_Sans-Web-Regular.ttf', ['PT_Sans-Web-Regular.ttf'], 'UI 既定フォント (リテラル名参照)'),
    ('T0p', 'Shared/Artwork/Fonts/*', ['Artwork\\Fonts'], 'フォントディレクトリ列挙 (QuickFontCache が登録): 他フォント'),
    ('T0', 'System/Config/*.txt', ['System\\Config\\', 'MP3Genres.txt', 'NamePresets_Channel.txt', 'NamePresets_Pattern.txt'], '設定/命名プリセット'),
    ('T0', 'System/Config/Chords.map', ['System\\Config\\'], '設定 (コード map)'),
    ('T0', 'System/Config/Master/*', ['System\\Config\\Master'], 'マスタ設定'),
    ('T0', 'System/Config/Mapping/*', ['System\\Config\\Mapping\\'], 'コントローラ mapping'),
    ('T0', 'System/Config/Typing to piano/*', ['System\\Config\\Typing to piano'], 'キー→ピアノ'),
    ('T0', 'System/Config/Toolbar presets/*', ['System\\Config\\Toolbar presets\\'], 'ツールバープリセット'),
    ('T0', 'System/Config/Touch keyboard/*', ['System\\Config\\Touch keyboard\\'], 'タッチ鍵盤'),
    ('T0', 'System/Config/Note color presets/*', ['System\\Config\\Note color presets\\'], 'ノート色'),
    ('T0', 'System/Config/Note name presets/*', ['System\\Config\\Note name presets\\'], 'ノート名'),
    ('T0', 'System/Config/Browser/*', ['System\\Config\\Browser'], 'ブラウザタブ構成 (.tabconfig)'),
    ('T0p', 'System/Config/Audio scripts/*', ['System\\Config\\Audio scripts'], 'スクリプト列挙'),
    ('T0p', 'System/Config/Piano roll scripts/*', ['System\\Config\\Piano roll scripts'], 'スクリプト列挙'),
    ('T0p', 'System/Config/FL Studio Remote Scripts/*', ['System\\Config\\FL Studio Remote Scripts'], 'リモートスクリプト列挙'),
    ('T1', 'System/Config/Thumbnails/*', ['System\\Config\\Thumbnails\\', 'edition-signature.png'], 'ブラウザ/エディション サムネイル'),
    ('T0', 'System/Plugin Formats/*', ['System\\Plugin Formats\\', 'formats.txt'], 'プラグイン形式定義'),
    ('T1', 'System/Texts/*', ['System\\Texts\\', 'BoxEdition.txt', 'NotReggedTxt.txt', 'DemoTxt.txt'], 'エディション/案内文・About/ライセンス文 (ダイアログ経路のみ; 直下 .txt は ST-T14 §4 #6 で T0p→T1)'),
    ('T0p', 'System/Internet/*', ['System\\Internet\\', 'error-offline.html'], 'ニュース/オフライン案内 (外部通信は対象外, 既定ページのみ)'),
    ('T2', 'System/Languages/*.moe', ['System\\Languages\\', '.moe'], '言語 .moe (既定 en では開かない; ST-T14 §4 #3)'),
    ('T1', 'System/Languages/*', ['System\\Languages\\', 'Languages\\'], '言語補助 (.svg 等)'),
    ('T1', 'System/Hardware specific/*', ['System\\Hardware specific\\'], 'MIDI コントローラ定義 (デバイス接続時)'),
    ('T0', 'Data/System/*.fst', ['Data\\System\\', 'AudioTrack.fst', 'SamplerTrack.fst', 'MIDITrack.fst', 'AutoTrack.fst', 'DirectWaveTrack.fst'], 'チャンネル既定 state (.fst)'),
    ('T0', 'Data/System/Empty.flp', ['Data\\System\\Empty.flp', 'Empty.flp'], '空プロジェクト'),
    ('T0', 'Data/System/Metronome*.wav', ['Metronome.wav', 'Metronome2.wav'], 'メトロノーム音'),
    ('T0', 'Data/System/*.ico', ['Data\\System\\'], 'アイコン'),
    ('T0p', 'Data/System/Riff machine/*', ['Data\\System\\'], 'Riff machine 既定'),
    ('T0p', 'Data/System/Default/*', ['Data\\System\\Default\\Installed plugins\\', 'Data\\System\\Default\\'], '既定インストール済みプラグイン定義'),
    ('T1', 'Data/System/Plugin databases/*', ['Data\\Patches\\Plugin database', 'Presets\\Plugin database\\'], 'プラグインデータベース (ブラウザ初回展開)'),
    ('T2', 'Data/System/FL Mobile/*', ['Data\\System\\FL Mobile Rack'], 'FL Studio Mobile ラック内容 (プラグイン生成時)'),
    ('T2', 'Data/System/Render tests/*', [], 'レンダーテスト (内部)'),
    ('T0p', 'Data/Templates/Minimal/Basic with limiter/*', ['Minimal\\Basic with limiter\\Basic with limiter.flp', 'Data\\Templates\\'], '既定テンプレート (起動時にロードされる推定)'),
    ('T1', 'Data/Templates/*', ['Data\\Templates\\'], 'テンプレート一覧 (New from template)'),
    ('T0p', 'Data/Patches/Packs/Legacy/Drums/Dance/Basic 808 *.wav', ['Data\\Patches\\Packs'], '既定テンプレート参照サンプル (FLP 文字列から導出)'),
    ('T0p', 'Plugins/Fruity/*/*/Plugin.nfo', ['Plugin.nfo', '.nfo', 'Plugins\\Fruity\\'], 'プラグインスキャン用メタ'),
    ('T0p', 'Plugins/Fruity/*/*.nfo', ['.nfo', 'Plugins\\Fruity\\'], 'プラグインスキャン用メタ'),
    ('T1', 'Help/index_offline.html', ['index_offline.html'], 'オフラインヘルプ入口'),
    ('T0p', 'Help/*.scr', ['HelpPlugins.scr', 'HelpAliases.scr'], 'ヘルプ別名表 (LoadSettings の Initialize the help file で起動時に読む; ST-T14 §4 #1)'),
    ('T1', 'WhatsNew.rtf', ['WhatsNew.htm'], '更新情報'),
    ('T1', 'Shared/Python/*', ['InitSharedPython'], 'Python 3.12 標準ライブラリ (スクリプト実行時)'),
]


_RX = {}


def _rx(g):
    # '*' は '/' を跨がない。末尾 '/*' は部分木全体 ('/**') を意味する。
    if g not in _RX:
        gg = g[:-2] + '/**' if g.endswith('/*') else g
        r = ''
        i = 0
        while i < len(gg):
            if gg.startswith('**', i):
                r += '.*'
                i += 2
            elif gg[i] == '*':
                r += '[^/]*'
                i += 1
            else:
                r += re.escape(gg[i])
                i += 1
        _RX[g] = re.compile('^' + r + '$', re.I)
    return _RX[g]


def match(rule_glob, p):
    return bool(_rx(rule_glob).match(p))


def tier_of(e):
    if e['cat'] == 'exec':
        return 'X-' + e['cls']
    p = e['p']
    for tier, g, ev, why in RULES:
        if match(g, p):
            return tier
    return 'T2'


def main():
    tiers = {}
    S = collections.defaultdict(lambda: [0, 0])
    # 物理ブロック (disk) 単位の最小 tier (重複配置で最も早い tier を採用)
    order = {'T0': 0, 'T0p': 1, 'T1': 2, 'T2': 3}
    for e in W:
        t = tier_of(e)
        tiers[e['p']] = t
        S[t][0] += 1
        S[t][1] += e['size']
    # 規則毎の証拠チェック + 該当統計
    rules_out = []
    for tier, g, ev, why in RULES:
        hit = [e for e in W if e['cat'] != 'exec' and match(g, e['p']) and tiers[e['p']] == tier]
        evid = {lit: has(lit) for lit in ev}
        rules_out.append(dict(tier=tier, glob=g, why=why, files=len(hit), bytes=sum(e['size'] for e in hit),
                              evidence=evid, evidence_found=sum(evid.values()), evidence_total=len(evid)))
    # FLP 既定テンプレート導出 (参照パスの実在確認)
    flp = None
    for e in W:
        if e['p'] == 'Data/Templates/Minimal/Basic with limiter/Basic with limiter.flp':
            b = open(e['disk'], 'rb').read()
            refs = [m.group().decode('utf-16-le') for m in re.finditer(rb'(?:[\x20-\x7e]\x00){6,}', b)]
            refs = [r for r in refs if r.startswith('%FLStudioFactoryData%')]
            have = {x['p'].lower() for x in W}
            flp = dict(file=e['p'], refs=refs, exist=[r.replace('%FLStudioFactoryData%\\', '').replace('\\', '/').lower() in have for r in refs])
    out = dict(
        tiers={k: dict(files=v[0], bytes=v[1]) for k, v in sorted(S.items())},
        rules=rules_out, template_refs=flp,
        note='T0/T0p/T1 は静的解析による推定。T0=文字列リテラルで直接裏取り / T0p=ディレクトリ列挙・既定テンプレートからの導出。',
    )
    json.dump(out, open(os.path.join(HERE, 'bootset.json'), 'w'), indent=1, ensure_ascii=False)
    json.dump(tiers, open(os.path.join(WORK, 'tiers.json'), 'w'), ensure_ascii=False)
    # unique content ベースの集計 (重複配置は 1 回数える)
    uniq = {}
    for e in W:
        t = tiers[e['p']]
        k = e['sha']
        if k not in uniq or order.get(t, 9) < order.get(uniq[k][0], 9):
            uniq[k] = (t, e['size'])
    U = collections.defaultdict(lambda: [0, 0])
    for t, sz in uniq.values():
        U[t][0] += 1
        U[t][1] += sz
    md = ['# 自動生成: `python3 tools/assets/bootset/classify_bootset.py` (`bootset/bootset.json`・`work/tiers.json` と同時生成)', '',
          '> **人手編集禁止** (生成元の `classify_bootset.py` を直す)。推定 tier の記載ここが正本。',
          '> 起動 tier の解釈・配信順への反映は `tools/assets/MANIFEST.md`、実施記録は `tools/assets/REPORT.md`。',
          '> tier の確度は「推定」(実機トレース未取得。根拠は FLEngine 文字列 + ツリー構造規則)。', '',
          '# BOOTSET — 起動時ファイル階層 (推定)', '', '| tier | files | bytes | MB | unique-content files | unique-content MB |', '|---|---:|---:|---:|---:|---:|']
    for t in ['T0', 'T0p', 'T1', 'T2', 'X-lift', 'X-rebuild', 'X-skip']:
        if t in S:
            md.append('| %s | %d | %d | %.2f | %d | %.2f |' % (t, S[t][0], S[t][1], S[t][1] / 1e6, U[t][0], U[t][1] / 1e6))
    md += ['', '## 規則と証拠 (FLEngine_x64.dll の UTF-16/ASCII 文字列に存在するか)', '', '| tier | glob | files | KB | 証拠 found/total | 理由 |', '|---|---|---:|---:|---|---|']
    for r in rules_out:
        md.append('| %s | `%s` | %d | %.1f | %d/%d | %s |' % (r['tier'], r['glob'], r['files'], r['bytes'] / 1024, r['evidence_found'], r['evidence_total'], r['why']))
    if flp:
        md += ['', '## 既定テンプレート参照 (%s)' % flp['file']] + ['- `%s` 実在=%s' % (r, x) for r, x in zip(flp['refs'], flp['exist'])]
    open(os.path.join(HERE, 'BOOTSET.md'), 'w').write('\n'.join(md) + '\n')
    print('\n'.join(md[:14]))


main()
