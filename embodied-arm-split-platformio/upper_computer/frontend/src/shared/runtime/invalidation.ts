export type InvalidationTopic =
  | 'system'
  | 'task.current'
  | 'task.templates'
  | 'task.history'
  | 'vision.targets'
  | 'vision.calibration'
  | 'vision.versions'
  | 'hardware'
  | 'logs'
  | 'audit'
  | 'readiness'
  | 'diagnostics';

type Listener = (topic: InvalidationTopic) => void;

const listeners = new Set<Listener>();

export function subscribeInvalidation(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function invalidateResources(topics: InvalidationTopic[]): void {
  topics.forEach((topic) => listeners.forEach((listener) => listener(topic)));
}
