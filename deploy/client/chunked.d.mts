export declare class AccessExpiredError extends Error {
  url: string;
}
export declare class ChunkIntegrityError extends Error {}

export type ChunkedOptions = {
  concurrency?: number;
  verify?: boolean;
  retries?: number;
  baseDelay?: number;
  signal?: AbortSignal;
  fetch?: typeof fetch;
  onProgress?: (p: { loaded: number; total: number; part: number; parts: number }) => void;
};

export declare function descriptorUrlFor(assetUrl: string): string;
export declare function chunkedResponse(descriptorUrl: string, opts?: ChunkedOptions): Promise<Response>;
export declare function compileChunkedWasm(descriptorUrl: string, opts?: ChunkedOptions): Promise<WebAssembly.Module>;
