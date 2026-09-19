/** A request from anywhere on the page (a hero card, a marquee chip, a
 * search result) asking the Explorer to show something. `nonce` makes an
 * identical repeat request still count as a new one. */
export type ExplorerRequest =
  | { kind: "chart"; id: string; nonce: number }
  | { kind: "compare"; ids: string[]; merge?: boolean; nonce: number }
  | { kind: "search"; text: string; nonce: number }
  | { kind: "details"; id: string; nonce: number };

type Distribute<T> = T extends unknown ? Omit<T, "nonce"> : never;
export type OpenExplorer = (request: Distribute<ExplorerRequest>) => void;
