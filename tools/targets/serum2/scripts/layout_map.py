#!/usr/bin/env python3
"""Address-locality 'TU map': label functions by RTTI vtable owner family, propagate labels to sandwiched neighbours.
Coarse estimate of code bytes per family (DSP osc/filter/fx/mod/midi, GUI, SDK, libs). usage: layout_map.py"""
import pickle, json, re, bisect, collections
g = pickle.load(open('work/win64_closure_graph.pkl', 'rb'))
funcs, vtables, IMG = g['funcs'], g['vtables'], g['IMG']
cen = {int(a, 16) - IMG: (sz, f) for a, sz, f in json.load(open('work/win64_census.json'))['funcs']}
starts = [b for b, e in funcs]; n = len(funcs)
fidx = lambda rva: bisect.bisect_right(starts, rva) - 1
RULES = [
 ('dsp.filter', r'^XferFilter|^FilterTypeParameter$'),
 ('dsp.fx', r'^Xfer(Bode|Chorus|Comp|Conv|Delay|DimE|Dist|EQ|Flanger|Hyper\w*|Phaser|Reverb\S*|FX\w*)$|^XferReverb'),
 ('dsp.osc', r'^(Oscillator|WarpOscillator|(WT|MultiSample|Sample|Granular|Spectral|Noise|Sub)Osc(State)?|OscState)$'),
 ('dsp.conv/fft', r'^(ZL\w+|PFFFTConvolver)$'),
 ('dsp.mod/env/lfo', r'^(LFO|LFOState|Macro|MacroModSource|ModMatrix|ModSlot|ModLine|SkEnv|EnvState|XferModSource|XferModule|XferRandom|XferUtils|XferFader|ChaosGraph)$'),
 ('dsp.midi/arp/clip', r'^(Arp|AlgoArp|PatternArp|ArpContext|ClipPlayer|MidiClip|MidiProcessor|PitchQuantizer|InputNote)$'),
 ('dsp.core/voice', r'^(SerumDSP|Voice|NoteExpressionVoice|XferLiveVoiceUser)$'),
 ('lib.sfz/muparser', r'^(libsfz::|mu::)'),
 ('gui.vstgui', r'^VSTGUI::'),
 ('gui.serum', r'(Controller|Display|TemplateParams|MenuData|View|Button|DropTarget|Knob|Slider|Switch|Panel|Editor|Dialog|Label|Scroll|Overview|Graph|Lane|Keyboard|Meter|Theme|Parameter)$|^Xfer(VST3Editor|OptionMenu|ParamDisplay|Control\w*|Knob|Scroll\w*|Text\w*|Radio\w*|Rocker\w*|Vertical\w*|Horizontal\w*|OnOff\w*|Kick\w*|AnimKnob|SubController|UI\w*)|^Serum(Editor|Controller|SubController|ModuleSubController|UIDescription|GUITemplateParams|Scroll\w*)|PresetManager|PresetBrowser|UndoManager|WTEditor|WaveformThumb'),
 ('sdk.steinberg', r'^Steinberg::'),
 ('lib.std/json/crt', r'^(std::|nlohmann|type_info|IUnknown|I[A-Z]\w*$)'),
]
RX = [(k, re.compile(p)) for k, p in RULES]
def fam(name):
    for k, rx in RX:
        if rx.search(name): return k
    return None
lab = [None] * n
votes = collections.defaultdict(collections.Counter)
for v, (nm, o, ms) in vtables.items():
    f = fam(nm)
    for m in ms:
        i = fidx(m)
        if i >= 0 and funcs[i][0] == m and f: votes[i][f] += 1
for i, c in votes.items():
    lab[i] = c.most_common(1)[0][0]
# sandwich propagation (nearest labelled both sides within window and same label)
lab2 = list(lab)
last = None
prev_idx = [None] * n
p = None
for i in range(n):
    prev_idx[i] = p
    if lab[i]: p = i
nxt = [None] * n; q = None
for i in range(n - 1, -1, -1):
    nxt[i] = q
    if lab[i]: q = i
for i in range(n):
    if lab[i]: continue
    a, b = prev_idx[i], nxt[i]
    if a is not None and b is not None and lab[a] == lab[b]:
        lab2[i] = lab[a] + '*'
tot = collections.defaultdict(lambda: [0, 0, 0, 0])  # funcs, bytes, fp ops, packed
for i in range(n):
    L = lab2[i] or 'unlabelled'
    sz = funcs[i][1] - funcs[i][0]
    f = cen.get(funcs[i][0], (0, {}))[1]
    t = tot[L.rstrip('*')]
    t[0] += 1; t[1] += sz; t[2] += f.get('sse_scalar_fp', 0); t[3] += f.get('sse_packed_fp', 0)
allb = sum(t[1] for t in tot.values())
print(f"{'family':<20}{'funcs':>8}{'bytes':>11}{'%text':>7}{'scalarFP':>10}{'packedFP':>10}")
for k, t in sorted(tot.items(), key=lambda x: -x[1][1]):
    print(f"{k:<20}{t[0]:>8}{t[1]:>11}{100*t[1]/allb:>6.1f}%{t[2]:>10}{t[3]:>10}")
json.dump({k: v for k, v in tot.items()}, open('work/win64_layout_map.json', 'w'), indent=1)
# address range of the dsp families
for fam_ in ['dsp.filter', 'dsp.fx', 'dsp.osc', 'dsp.core/voice', 'dsp.mod/env/lfo', 'dsp.midi/arp/clip', 'dsp.conv/fft']:
    idx = [i for i in range(n) if lab2[i] and lab2[i].rstrip('*') == fam_]
    if idx:
        print(fam_, hex(funcs[idx[0]][0] + IMG), '..', hex(funcs[idx[-1]][1] + IMG))
