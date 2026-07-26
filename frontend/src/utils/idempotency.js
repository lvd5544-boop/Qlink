function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

function defaultUuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Keep one key for the same logical payload until the server confirms success.
 *
 * A visible retry after a confirmed model failure reuses the key; the backend
 * reactivates its released reservation. A retry after an uncertain network
 * outcome therefore cannot create a second successful reservation.
 */
export function createIdempotencyTracker(scope, uuidFactory = defaultUuid) {
  let active = null;
  const safeScope = String(scope || 'ai-operation')
    .replace(/[^a-z0-9._-]/gi, '-')
    .slice(0, 40);

  return {
    keyFor(payload) {
      const fingerprint = JSON.stringify(stableValue(payload));
      if (!active || active.fingerprint !== fingerprint) {
        active = {
          fingerprint,
          key: `${safeScope}:${uuidFactory()}`.slice(0, 128),
        };
      }
      return active.key;
    },
    complete(key) {
      if (active?.key === key) active = null;
    },
    reset() {
      active = null;
    },
  };
}
