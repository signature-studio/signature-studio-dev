/**
 * webstudio_state.ts — `window.__webstudio` 起動契約 (tools/e2e/REPORT.md §FL 起動契約)。
 *
 *   window.__webstudio = { state: 'booting' | 'running' | 'error', frames: number, error?: string }
 *
 * - state は booting -> running -> (error) の一方向。error は終端で、以後 running へ戻らない。
 * - running は「GUI フレームが 1 枚以上転送された時」に reportFrame() が自動で遷移させる。
 * - e2e (`fl-boot`) はこの 3 値だけを見る。FL 本体・GuiHost 側はここの関数を呼ぶだけにする。
 */
export type WebstudioState = "booting" | "running" | "error";

/** 載せているゲストの種別。"test" は FL でない検証用 wasm (fl-boot は PASS させない: D5) */
export type WebstudioGuest = "fl" | "test";

export type WebstudioContract = {
  state: WebstudioState;
  frames: number;
  error?: string;
  guest?: WebstudioGuest;
};

export type WebstudioController = {
  readonly contract: WebstudioContract;
  /** GUI フレームを n 枚 (既定 1) 転送済みとして計上する。booting 中なら running へ遷移する */
  reportFrame(n?: number): void;
  /** frames の絶対値で報告する (GuiHost.frames をそのまま渡す用)。減少は無視する */
  setFrames(total: number): void;
  /** 載せているゲストの種別を記録する (起動時に 1 回) */
  setGuest(guest: WebstudioGuest): void;
  /** 終端状態 error へ遷移する。最初のエラーだけ保持する */
  fail(e: unknown): void;
};

export function createWebstudioController(): WebstudioController {
  const contract: WebstudioContract = { state: "booting", frames: 0 };
  const setFrames = (total: number): void => {
    if (contract.state === "error") return;
    if (!Number.isFinite(total) || total <= contract.frames) return;
    contract.frames = Math.floor(total);
    if (contract.frames > 0) contract.state = "running";
  };
  return {
    contract,
    reportFrame(n = 1) {
      setFrames(contract.frames + n);
    },
    setFrames,
    setGuest(guest) {
      contract.guest = guest;
    },
    fail(e) {
      if (contract.state === "error") return;
      contract.state = "error";
      contract.error = e instanceof Error ? e.message : String(e);
    },
  };
}

/** window に契約を公開する。ページ読込時に 1 回だけ呼ぶ (booting で開始) */
export function installWebstudioContract(
  target: { __webstudio?: WebstudioContract } & Partial<Pick<Window, "addEventListener">> = globalThis as never,
): WebstudioController {
  const ctl = createWebstudioController();
  target.__webstudio = ctl.contract;
  target.addEventListener?.("error", (ev) => ctl.fail((ev as ErrorEvent).error ?? (ev as ErrorEvent).message));
  target.addEventListener?.("unhandledrejection", (ev) => ctl.fail((ev as PromiseRejectionEvent).reason));
  return ctl;
}

declare global {
  interface Window {
    __webstudio?: WebstudioContract;
  }
}
