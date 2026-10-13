/**
 * flm_ctl_t (tools/audio/src/flmidi.h) のバイトオフセット表。単一の真実は C ヘッダ。
 * verifyMidiLayout が wasm の flm_layout_off() と照合し、不一致なら fail-fast (throw)。
 */
export const FLM_ABI = 1;
export const FLM_CTL_SIZE = 320;
export const FLM_REC = 16;
export const FLM_MAX_DEV = 16;
export const FLM_NAME_CHARS = 32;
export const FLM_DEV_ENTRY = 96;
export const FLM_MAX_SYSEX = 65536 - 2 * FLM_REC;

export const FLM_LAYOUT = {
  magic: 0, state: 8, in_ring_ptr: 12, in_ring_bytes: 16, out_ring_ptr: 20, out_ring_bytes: 24, dev_tbl_ptr: 28, max_dev: 32, ctrl_ready: 36,
  in_w: 64, in_dropped: 68, in_accepted: 72, main_errors: 76, out_r: 80, out_errors: 84, out_sent: 88,
  in_r: 128, out_w: 132, wake: 136, out_full: 140, sx_nobuf: 144, in_stale: 148, in_prestart: 152, cb_events: 156,
  tbl_seq: 192, n_in: 196, n_out: 200, scan_gen: 204,
  cmd_seq: 256, cmd_op: 260, cmd_arg: 264, ack_seq: 280, ack_status: 284, ack_res: 288,
} as const;
export type FlmField = keyof typeof FLM_LAYOUT;

export const FLM_K = { SHORT: 0, SYSEX: 1, STATE: 2 } as const;
export const FLM_CMD = { NONE: 0, SCAN: 1, OPEN_IN: 2, CLOSE_IN: 3, OPEN_OUT: 4, CLOSE_OUT: 5 } as const;
export const FLM_E = { DENIED: -4, OPEN: -3, NODEV: -2 } as const;

export function verifyMidiLayout(count: number, offOf: (i: number) => number, nameOf: (i: number) => string): void {
  const seen = new Set<string>();
  for (let i = 0; i < count; i++) {
    const name = nameOf(i);
    const off = offOf(i);
    const exp = (FLM_LAYOUT as Record<string, number>)[name];
    if (exp === undefined) throw new Error(`[midi-layout] wasm フィールド ${name} が TS 表に無い`);
    if (exp !== off) throw new Error(`[midi-layout] ${name}: wasm=${off} TS=${exp} (不一致)`);
    seen.add(name);
  }
  for (const k of Object.keys(FLM_LAYOUT)) if (!seen.has(k)) throw new Error(`[midi-layout] TS フィールド ${k} が wasm 側に無い`);
}
