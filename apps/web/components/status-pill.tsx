import type { SourceState } from "@/lib/types";

export function StatusPill({ state }: { state: SourceState }) {
  return <span className={`status-pill status-pill--${state.toLowerCase()}`}>{state.replace("_", " ")}</span>;
}
