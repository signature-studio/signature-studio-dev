// wvfs — 書込可能 VFS (RT-5 / CAB-123)。/c/home・/c/tmp を OPFS バッキングのジャーナル FS で実装する。
// 仕様の正本は wvfs/REPORT.md。既存 LazyVfs (../vfs) とは独立 (mount 点でのみ共存)。
export { Wvfs, WvfsError, Journal } from './wvfs.ts';
export type { WvfsStat, WvfsOptions, WvfsBackend, WvfsErrCode } from './wvfs.ts';
export { OpfsBackend } from './backend-opfs.ts';
export { NodeBackend } from './backend-node.ts';
export { createWvfsFs } from './emscripten-wvfs.ts';
export type { WvfsFsOptions } from './emscripten-wvfs.ts';
export { createPathRouter, storeDir, HOME_MOUNT, TMP_MOUNT, WVFS_ROOT } from './pathlink.ts';
export type { PathRouter, Route, WvfsMountName } from './pathlink.ts';
