// Vitest / JSDOM test setup & runtime compatibility polyfills
import workerThreads from 'node:worker_threads';

// Node.js < 21 compatibility shim: undici / JSDOM web standard cache/webidl relies on markAsUncloneable
if (workerThreads && typeof (workerThreads as any).markAsUncloneable !== 'function') {
  (workerThreads as any).markAsUncloneable = (obj: unknown) => obj;
}
