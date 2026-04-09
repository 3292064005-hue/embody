type ResyncListener = (reason: string) => void;

const listeners = new Set<ResyncListener>();

export function requestRuntimeResync(reason: string): void {
  listeners.forEach((listener) => listener(reason));
}

export function subscribeRuntimeResync(listener: ResyncListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
