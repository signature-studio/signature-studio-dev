// FLP event dictionary (independently written; ids/sizes validated against the Demo/Template/Render-test/FST/FSC corpus and the
// FLEngine_x64.dll writer call sites -- see REPORT.md). `src` records provenance of the label:
//   upstream = id is also modelled by PyFLP 2.2.1 (see id_sets.ts)   legacy = long-documented FL SDK-era id
//   observed = label not in the upstream/legacy docs; conf 'high' = loader effect (target field, value transform, range check) read from FLEngine FlpLoad 0xf46490;
//              conf 'med' = same, but the role of the target field is inferred; conf 'low' = not examined in FlpLoad
import { UPSTREAM_IDS, ENGINE_WRITTEN_IDS } from './id_sets.ts';

export type ValType = 'u8' | 'i8' | 'bool' | 'u16' | 'i16' | 'u32' | 'i32' | 'color' | 'wstr' | 'astr' | 'blob' | 'rec';
export type Scope =
  | 'project'
  | 'channel'
  | 'plugin'
  | 'pattern'
  | 'arrangement'
  | 'playlist'
  | 'mixer'
  | 'insert'
  | 'slot'
  | 'timemarker'
  | 'track'
  | 'group'
  | 'any';
export type Conf = 'high' | 'med' | 'low';

export interface EventDef {
  id: number;
  name: string;
  type: ValType;
  scope: Scope;
  src: 'upstream' | 'legacy' | 'observed';
  conf: Conf;
  note?: string;
  /** fixed record stride for 'rec' payloads */
  recSize?: number;
}

const defs: EventDef[] = [];
function d(id: number, name: string, type: ValType, scope: Scope, src: EventDef['src'], conf: Conf, note?: string, recSize?: number): void {
  defs.push({ id, name, type, scope, src, conf, note, recSize });
}

// ---- BYTE (0..63) ----
d(0, 'ChannelEnabled', 'bool', 'channel', 'upstream', 'high');
d(1, 'NoteOn', 'u8', 'channel', 'legacy', 'low', 'legacy preview note (FST only)');
d(2, 'ChanVolByte', 'u8', 'channel', 'upstream', 'med', 'legacy; superseded by ChannelLevels(219)');
d(3, 'ChanPanByte', 'u8', 'channel', 'upstream', 'med');
d(4, 'MidiChannel', 'u8', 'channel', 'legacy', 'low');
d(9, 'LoopActive', 'bool', 'project', 'upstream', 'high', 'song/pattern mode');
d(10, 'ShowInfo', 'bool', 'project', 'upstream', 'high');
d(11, 'Swing', 'u8', 'project', 'upstream', 'med');
d(12, 'MainVolByte', 'u8', 'project', 'upstream', 'low', 'legacy');
d(13, 'FitToSteps', 'u8', 'channel', 'upstream', 'low', 'legacy');
d(14, 'Pitchable', 'bool', 'channel', 'legacy', 'low');
d(15, 'Zipped', 'bool', 'channel', 'upstream', 'med');
d(16, 'DelayFlags', 'u8', 'channel', 'legacy', 'low');
d(17, 'TimeSigNum', 'u8', 'project', 'upstream', 'high');
d(18, 'TimeSigBeat', 'u8', 'project', 'upstream', 'high');
d(19, 'ChanLoopPointsFlag', 'bool', 'channel', 'observed', 'med', '0xf47a03: sets channel->[0x330]+0x14d=1 whenever present (value ignored)');
d(20, 'PingPongLoop', 'bool', 'channel', 'upstream', 'med', 'channel loop type');
d(21, 'ChannelType', 'u8', 'channel', 'upstream', 'high', 'upstream enum: 0 sampler, 2 native, 3 layer, 4 instrument, 5 automation (corpus value histogram in REPORT.md)');
d(22, 'RoutedTo', 'i8', 'channel', 'upstream', 'high', 'mixer insert index; -1 = none');
d(23, 'PanLaw', 'u8', 'project', 'upstream', 'med');
d(24, 'Unk24', 'u8', 'channel', 'observed', 'low', 'FST channel presets only');
d(25, 'PatternAux25', 'u8', 'pattern', 'observed', 'med', '0xf47ccd: pattern[cur].+0x1c = value (u32 slot)');
d(26, 'PatternLooped', 'bool', 'pattern', 'upstream', 'med');
d(27, 'InsertFlagsLegacy', 'u8', 'insert', 'observed', 'high', '0xf47d98: bitmask -> insert[cur] b0:+0x390 b1:+0x391 b2:+0x13f5 b3:setter(0x12c17d0) b4(inverted):+0x380');
d(28, 'Licensed', 'bool', 'project', 'upstream', 'high');
d(29, 'Apdc', 'bool', 'mixer', 'upstream', 'med', 'automatic plugin delay compensation');
d(30, 'PlayTruncatedNotes', 'bool', 'project', 'upstream', 'med');
d(31, 'MixerPreludeFlag31', 'u8', 'mixer', 'observed', 'med', '0xf47fc9: global bool = value>0');
d(32, 'ChannelLocked', 'bool', 'channel', 'upstream', 'med');
d(33, 'TimeMarkerNum', 'u8', 'timemarker', 'upstream', 'high');
d(34, 'TimeMarkerDenom', 'u8', 'timemarker', 'upstream', 'high');
d(35, 'ProjectFlag35', 'u8', 'project', 'observed', 'med', '0xf4799c: value==1 -> global bool=1; then calls global fn 0x13657d0 (role not examined)');
d(36, 'ArrangementFlag36', 'u8', 'arrangement', 'observed', 'med', '0xf479de: current arrangement object +0x10 = byte');
d(37, 'LegacyMarker37', 'u8', 'project', 'observed', 'high', 'default arm: the loader ignores it (no case; written by the engine, value 1)');
d(38, 'MixerPreludeFlags38', 'u8', 'mixer', 'observed', 'high', '0xf47ff0: bit0 -> global.+0x938 setter, bit1 -> global.+0x930 setter');
d(39, 'MixerPreludeFlag39', 'u8', 'mixer', 'observed', 'med', '0xf47ef4: global bool = value>0');
d(40, 'MixerPreludeFlag40', 'u8', 'mixer', 'observed', 'med', '0xf47f1b: global.+0x10.+0x18 = value>0, then notifies via vtable+0x200');
d(41, 'PluginFlag41', 'u8', 'plugin', 'observed', 'high', '0xf492bd: if a plugin is open: plugin.+0xf9 = (value!=0)');
d(42, 'InsertFlag42', 'u8', 'insert', 'observed', 'med', '0xf49f83: insert[cur].+0x0 = (value!=0)');
d(43, 'TrackFlag43', 'u8', 'track', 'observed', 'high', '0xf4e7a3: track[cur].+0x70 = (value!=0); when 0 also resets track.+0x2c to a global default');
d(44, 'ProjectFlag44', 'u8', 'project', 'observed', 'med', '0xf4808e: calls global setter 0xe34030(value!=0, 1)');
d(45, 'TimeMarkerFlag45', 'u8', 'timemarker', 'observed', 'high', '0xf49d5c: latched, applied to the current time marker .+0x28 (bool) when id 205 is processed (0xf4abf7)');
d(46, 'TimeMarkerByte46', 'u8', 'timemarker', 'observed', 'high', '0xf49d3b: latched, applied to the current time marker .+0x30 (byte) when id 205 is processed (0xf4abf7)');
d(47, 'ProjectFlag47', 'u8', 'project', 'observed', 'med', '0xf4e9b2: (skipped when two global guard bools are set) global.+0x10 vtable+8(value>0)');
d(48, 'ChannelFlag48', 'u8', 'channel', 'observed', 'high', '0xf48d5c: channel.+0x224 = (value!=0)');
d(49, 'InsertMode49', 'u8', 'insert', 'observed', 'high', '0xf497f1: insert[cur].+0x1472 = value for value in {0,1,2}; other values ignored');
d(50, 'ChannelByte50', 'u8', 'channel', 'observed', 'high', '0xf48fb9: channel.+0x1fc = byte');
d(51, 'ChannelFlags51', 'u8', 'channel', 'observed', 'high', '0xf4c8f8: bit0 -> channel.+0x738, bit1 -> +0x79d, bit2 -> +0x79c');
d(52, 'PatternFlag52', 'u8', 'pattern', 'observed', 'high', '0xf4eb6f: pattern[cur].+0xa4 = (value!=0); last pattern property (with 171/252/253)');
d(54, 'Unk54', 'u8', 'any', 'observed', 'low', 'FST only');
d(56, 'Unk56', 'u8', 'any', 'observed', 'low', 'FST only');

// ---- WORD (64..127) ----
d(64, 'NewChannel', 'u16', 'channel', 'upstream', 'high', 'opens a channel; value = channel iid');
d(65, 'NewPattern', 'u16', 'pattern', 'upstream', 'high', 'opens a pattern (1-based); FSC: score');
d(66, 'TempoCoarse', 'u16', 'project', 'upstream', 'med', 'legacy BPM (pre-3.4)');
d(67, 'CurrentPattern', 'u16', 'project', 'upstream', 'high');
d(69, 'ChanFreqTilt', 'u16', 'channel', 'upstream', 'med');
d(70, 'ChanFxFlags', 'u16', 'channel', 'upstream', 'med');
d(71, 'ChanCutoff', 'u16', 'channel', 'upstream', 'high');
d(72, 'ChanVolWord', 'u16', 'channel', 'upstream', 'med');
d(73, 'ChanPanWord', 'u16', 'channel', 'upstream', 'med');
d(74, 'ChanPreamp', 'u16', 'channel', 'upstream', 'med');
d(75, 'ChanFadeOut', 'u16', 'channel', 'upstream', 'med');
d(76, 'ChanFadeIn', 'u16', 'channel', 'upstream', 'med');
d(78, 'Unk78', 'u16', 'any', 'observed', 'low');
d(80, 'MainPitch', 'i16', 'project', 'upstream', 'high', 'cents');
d(83, 'ChanResonance', 'u16', 'channel', 'upstream', 'med');
d(85, 'ChanStereoDelay', 'u16', 'channel', 'upstream', 'med');
d(86, 'ChanPogo', 'u16', 'channel', 'upstream', 'med');
d(89, 'ChanTimeShift', 'u16', 'channel', 'upstream', 'med');
d(91, 'ChanPatternDot91', 'u16', 'channel', 'observed', 'med', '0xf48d87: channel.+0x7ac list gets (pattern idx, key=value&0xff, kind=9, amount=value>>8)');
d(92, 'ChanPatternDot92', 'u16', 'channel', 'observed', 'med', '0xf48de4: as 91 with kind=7; for files older than 2.1.0 the amount is rescaled x*48/255');
d(93, 'TempoFine', 'u16', 'project', 'upstream', 'med', 'legacy fine tempo');
d(94, 'LayerChildren', 'u16', 'channel', 'upstream', 'med');
d(95, 'InsertIcon', 'i16', 'insert', 'upstream', 'med');
d(97, 'ChanSwing', 'u16', 'channel', 'upstream', 'med');
d(98, 'SlotIndex', 'u16', 'slot', 'upstream', 'high', 'opens an effect slot of the current insert (0..9)');
d(99, 'NewArrangement', 'u16', 'arrangement', 'upstream', 'high');
d(100, 'CurrentArrangement', 'u16', 'mixer', 'upstream', 'high');
d(101, 'TimeMarkerMask101', 'u16', 'timemarker', 'observed', 'high', '0xf49d9c: 12-bit mask -> 12 bool bytes latched, applied to time marker .+0x1c..+0x27 (bit0 -> byte 11)');
d(103, 'MixerInsertCount', 'u16', 'mixer', 'observed', 'high', '0xf4ea07: must be 3..502 else the load fails (state 7); then sets the insert count (0x127cea0). Equals the number of id 236 in 30/30 corpus files');
d(104, 'ChanRoutedToWord', 'u16', 'channel', 'observed', 'high', '0xf47bae: same arm as 22 RoutedTo (channel.+0x258 = insert index, range 0..501); FL >= 24.2.99 uses it instead of 22 (1130 channels use 104, 0 of them also have 22)');
d(111, 'Unk111', 'u16', 'any', 'observed', 'low', 'FST only');
d(114, 'Unk114', 'u16', 'any', 'observed', 'low', 'FST only');

// ---- DWORD (128..191) ----
d(128, 'PluginColor', 'color', 'plugin', 'upstream', 'high');
d(131, 'ChanRingMod', 'u32', 'channel', 'upstream', 'med');
d(132, 'ChanCutGroup', 'u32', 'channel', 'upstream', 'med');
d(133, 'WindowHeight', 'u32', 'project', 'upstream', 'med');
d(135, 'ChanRootNote', 'u32', 'channel', 'upstream', 'med');
d(138, 'ChanDelayMod', 'u32', 'channel', 'upstream', 'med');
d(139, 'ChanReverb', 'u32', 'channel', 'upstream', 'med');
d(140, 'ChanStretchTime', 'u32', 'channel', 'upstream', 'low', 'float32 in upstream');
d(142, 'ChanFineTune', 'i32', 'channel', 'upstream', 'med');
d(143, 'ChanSamplerFlags', 'u32', 'channel', 'upstream', 'med');
d(144, 'ChanLayerFlags', 'u32', 'channel', 'upstream', 'med');
d(145, 'ChanGroupNum', 'i32', 'channel', 'upstream', 'med');
d(146, 'CurGroupId', 'i32', 'project', 'upstream', 'med');
d(147, 'InsertOutput', 'i32', 'insert', 'upstream', 'high');
d(148, 'NewTimeMarker', 'u32', 'timemarker', 'upstream', 'high', 'position (+type in high bits); opens a time marker');
d(149, 'InsertColor', 'color', 'insert', 'upstream', 'high');
d(150, 'PatternColor', 'color', 'pattern', 'upstream', 'high');
d(152, 'SongLoopPos', 'u32', 'arrangement', 'upstream', 'med');
d(153, 'AuSampleRate', 'u32', 'channel', 'upstream', 'med');
d(154, 'InsertInput', 'i32', 'insert', 'upstream', 'med');
d(155, 'PluginIcon', 'u32', 'plugin', 'upstream', 'high');
d(156, 'Tempo', 'u32', 'project', 'upstream', 'high', 'BPM*1000');
d(157, 'PatternDword157', 'u32', 'pattern', 'observed', 'med', '0xf4a05b: pattern[cur].+0x10 = u32');
d(158, 'PatternDword158', 'u32', 'pattern', 'observed', 'med', '0xf4a08e: pattern[cur].+0x18 = u32');
d(159, 'FlBuild', 'u32', 'project', 'upstream', 'high');
d(160, 'PatternChannelIid', 'u32', 'pattern', 'upstream', 'med');
d(161, 'PatternDword161', 'i32', 'pattern', 'upstream', 'low');
d(162, 'PatternDword162', 'u32', 'pattern', 'upstream', 'low');
d(164, 'PatternLength', 'u32', 'pattern', 'upstream', 'high');
d(165, 'InsertEnum165', 'u32', 'insert', 'observed', 'high', '0xf49ba9: insert[cur].+0x2f = value for 0..5, anything else -> 3');
d(166, 'InsertEnum166', 'u32', 'insert', 'observed', 'high', '0xf49c7c: insert[cur].+0x30 = value for 0..3, anything else -> 3');
d(167, 'ProjectEnum167', 'u32', 'project', 'observed', 'high', '0xf4a8ea: sets a global flag; value 0..2 -> global.+0x10 vtable+0(value), otherwise vtable+0(0)');
d(168, 'TimeMarkerDword168', 'u32', 'timemarker', 'observed', 'high', '0xf49d7d: latched (default 0xFFFFFFFF), applied to time marker .+0x2c when id 205 is processed');
d(169, 'ProjectLayoutFlags', 'u32', 'project', 'observed', 'high', '0xf4a183: latched into the load context; decides the playlist record stride in 0xf558e0 (absent/bit1 clear -> 60B, bit1 set & bit3 clear -> 80B, bit3 set -> engine-native stride)');
d(170, 'ChannelDword170', 'u32', 'channel', 'observed', 'med', '0xf4c8d2: channel.+0x714 = u32');
d(171, 'PatternDword171', 'u32', 'pattern', 'observed', 'med', '0xf4ebaa: pattern[cur].+0xa8 = u32');

// ---- TEXT (192..207) / DATA (208..255) ----
d(192, 'ChannelNameLegacy', 'wstr', 'channel', 'upstream', 'med');
d(193, 'PatternName', 'wstr', 'pattern', 'upstream', 'high');
d(194, 'ProjectTitle', 'wstr', 'project', 'upstream', 'high');
d(195, 'ProjectComments', 'wstr', 'project', 'upstream', 'high');
d(196, 'SamplePath', 'wstr', 'channel', 'upstream', 'high', 'may start with %FLStudioFactoryData%');
d(197, 'ProjectUrl', 'wstr', 'project', 'upstream', 'high');
d(198, 'CommentsRtf', 'astr', 'project', 'upstream', 'med', 'legacy RTF');
d(199, 'FlVersion', 'astr', 'project', 'upstream', 'high', 'ASCII "major.minor.patch.build"');
d(200, 'Licensee', 'blob', 'project', 'upstream', 'med', 'XOR-scrambled (FLEngine 0xa9ece0), 36B in all samples');
d(201, 'PluginInternalName', 'wstr', 'plugin', 'upstream', 'high');
d(202, 'ProjectDataPath', 'wstr', 'project', 'upstream', 'high');
d(203, 'PluginName', 'wstr', 'plugin', 'upstream', 'high');
d(204, 'InsertName', 'wstr', 'insert', 'upstream', 'high');
d(205, 'TimeMarkerName', 'wstr', 'timemarker', 'upstream', 'high');
d(206, 'ProjectGenre', 'wstr', 'project', 'upstream', 'high');
d(207, 'ProjectArtists', 'wstr', 'project', 'upstream', 'high');
d(208, 'Data208', 'blob', 'any', 'observed', 'low', 'single sample (251B)');
d(209, 'ChannelDelay', 'blob', 'channel', 'upstream', 'high', '20B = 5*u32');
d(210, 'ChanObjData210', 'blob', 'channel', 'observed', 'med', '0xf4b04a: payload copied (clamped to the target size) into the buffer of channel->+0x358; before 3.2.91 also flips .+0x48 = 0x80-x');
d(212, 'PluginWrapper', 'blob', 'plugin', 'upstream', 'high', '52B; flags u16@16, page u8@20, w/h u32@44/48');
d(213, 'PluginData', 'blob', 'plugin', 'upstream', 'high', 'native state or VST/CLAP chunk list');
d(215, 'ChannelParameters', 'blob', 'channel', 'upstream', 'high');
d(216, 'ProjectRecords216', 'blob', 'project', 'observed', 'med', '0xf4d011: kind-0 record list of a global object (0xf558e0); 12B records before 20.99.1, engine-native stride after (corpus: multiples of 12B)');
d(217, 'PlaylistSelection', 'blob', 'project', 'upstream', 'med', '8B');
d(218, 'EnvelopeLfo', 'blob', 'channel', 'upstream', 'high', '68B (56B older); 5 per channel');
d(219, 'ChannelLevels', 'blob', 'channel', 'upstream', 'high', '24B (12B older)');
d(220, 'ChanData220', 'blob', 'channel', 'observed', 'med', '0xf4d375: copied into channel.+0x178 (8B for files <= 2.5.0, else the payload length); for files < 3.2.2 field +0x17c is rescaled');
d(221, 'ChannelPolyphony', 'blob', 'channel', 'upstream', 'high', '9B');
d(223, 'PatternControllers', 'rec', 'pattern', 'upstream', 'high', '12B records', 12);
d(224, 'PatternNotes', 'rec', 'pattern', 'upstream', 'high', '24B records', 24);
d(225, 'MixerParams', 'rec', 'mixer', 'upstream', 'high', '12B records', 12);
d(226, 'MidiController', 'blob', 'project', 'upstream', 'high', '20B');
d(227, 'RemoteController', 'blob', 'project', 'upstream', 'high', '20B');
d(228, 'ChannelTracking', 'blob', 'channel', 'upstream', 'high', '16B; 2 per channel');
d(229, 'ChannelLevelAdjusts', 'blob', 'channel', 'upstream', 'high', '20B');
d(230, 'ControllerFormula230', 'wstr', 'any', 'observed', 'med', '0xf4da57: UTF-16 text parsed by 0xf81f70 into the object held in the load context slot set by 226/227 (current controller)');
d(231, 'DisplayGroupName', 'wstr', 'group', 'upstream', 'high', 'always UTF-16');
d(233, 'PlaylistItems', 'rec', 'playlist', 'upstream', 'high', '32B records', 32);
d(234, 'ChannelAutomation', 'blob', 'channel', 'upstream', 'high');
d(235, 'InsertRouting', 'blob', 'insert', 'upstream', 'high', 'one byte per target insert');
d(236, 'InsertFlags', 'blob', 'insert', 'upstream', 'high', '12B (8B / 5B variants)');
d(237, 'ProjectTimestamp', 'blob', 'project', 'upstream', 'high', '16B = 2*f64 (Delphi TDateTime created, days spent)');
d(238, 'TrackData', 'blob', 'track', 'upstream', 'high', '66-70B in FL21+');
d(239, 'TrackName', 'wstr', 'track', 'upstream', 'high', 'always UTF-16');
d(240, 'GlobalStringListItem240', 'wstr', 'mixer', 'observed', 'med', '0xf4e860: appends the text to a global dynamic string array (corpus: insert group names)');
d(241, 'ArrangementName', 'wstr', 'arrangement', 'upstream', 'high', 'always UTF-16');
d(242, 'ArrangementState242', 'blob', 'arrangement', 'observed', 'med', '0xf4e621: 28B required; u32@0 = arrangement index (must be < count); stores @4 -> arr.+0x21c5c, f64@0xc*scale -> +0x21c64, @0x14 -> +0x21c6c, i32@0x18*scale -> next field');
d(243, 'GlobalIntPair243', 'blob', 'project', 'observed', 'med', '0xf4e954: 8B required; two u32 -> two global ints');
d(251, 'ChanSubObjectState251', 'blob', 'channel', 'observed', 'med', '0xf4dc8f: payload wrapped as a stream and loaded into the object at channel.+0x784 (0x1006ec0)');
d(252, 'PatternText252', 'wstr', 'pattern', 'observed', 'high', '0xf4ebe0: pattern[cur].+0xac = text');
d(253, 'PatternText253', 'wstr', 'pattern', 'observed', 'med', '0xf4ec26: comma list text parsed by 0x12d2290 into pattern[cur].+0xb4');

// Extended ids (0xAC escape, FL 25.2+). Only ids observed in the corpus or written by FLEngine.
d(0x100, 'ProjectFlagExt100', 'u8', 'project', 'observed', 'high', '0xf4ec6c (ext id 0x100): global.+0x10 vtable+0x10(value!=0); written after 0xC0000100');
d(0xc0000100, 'ExtText100', 'wstr', 'project', 'observed', 'low', 'written after ProjectUrl when the engine has a value (not in corpus)');
d(0xc0000101, 'FlStudioVersionText', 'wstr', 'project', 'observed', 'med', '"FL Studio <ver>.<build>"; first event after Licensed(28)');
d(0xc0000102, 'ExtText102', 'wstr', 'channel', 'observed', 'low', 'written by FLEngine after channel flags (not in corpus)');

export const EVENT_DEFS: ReadonlyMap<number, EventDef> = new Map(defs.map((x) => [x.id, x]));

export function defOf(id: number): EventDef | undefined {
  return EVENT_DEFS.get(id);
}

export function eventName(id: number): string {
  const e = EVENT_DEFS.get(id);
  if (e) return e.name;
  if (id > 255) return `Ext_0x${id.toString(16)}`;
  return `Unk${id}`;
}

export function isUpstreamKnown(id: number): boolean {
  return UPSTREAM_IDS.has(id);
}
export function isEngineWritten(id: number): boolean {
  return ENGINE_WRITTEN_IDS.has(id);
}

/** documentation status used for the unknown-event census */
export function docStatus(id: number): 'named-upstream' | 'named-observed' | 'undocumented' {
  const e = EVENT_DEFS.get(id);
  if (UPSTREAM_IDS.has(id) && e && e.src !== 'observed') return 'named-upstream';
  if (e && e.conf !== 'low') return 'named-observed';
  return 'undocumented';
}
