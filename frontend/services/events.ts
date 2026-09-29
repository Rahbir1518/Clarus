// Live change notifications from the backend.
//
// The server sends a name and a row id, never the row — so receiving an event
// means "re-fetch", not "here is the new state". That is what keeps the data
// path unchanged: every read still goes through the ordinary API, where it is
// tenant-scoped and auditable. See backend/app/events/broker.py.
//
// Not EventSource. It cannot set an Authorization header, and the usual
// workaround — the token in a query string — writes a credential into access
// logs, proxy logs and browser history. A streaming `fetch` can send the
// header, at the cost of parsing the SSE framing here, which is a dozen lines.

import { API_URL, authorizedFetch } from './api';

export type ClarusEvent = {
  /** The SSE event type, e.g. "call_log.updated". */
  name: string;
  /** The row that changed. */
  id: string;
};

// The server closes each stream after ten minutes so the next one re-verifies
// a fresh Clerk token, and that close is a normal end rather than a failure —
// hence a short first retry. The backoff is for the other case: a backend that
// is down should not be hammered by every open tab.
const INITIAL_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;

/**
 * Subscribe to the signed-in doctor's own events. Returns an unsubscribe
 * function; call it on unmount or the stream outlives the component.
 */
export function subscribeToEvents(onEvent: (event: ClarusEvent) => void): () => void {
  let closed = false;
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let retryDelay = INITIAL_RETRY_MS;

  async function connect(): Promise<void> {
    if (closed) return;

    controller = new AbortController();
    try {
      const response = await authorizedFetch(`${API_URL}/api/events`, {
        signal: controller.signal,
        headers: { Accept: 'text/event-stream' },
      });

      if (!response.ok || !response.body) {
        throw new Error(`Event stream failed (${response.status})`);
      }

      // Reset only after a connection actually succeeded. Resetting on attempt
      // would turn the backoff into a fixed 1s poll against a dead backend.
      retryDelay = INITIAL_RETRY_MS;
      await readFrames(response.body, onEvent);
    } catch (error) {
      // An abort is us calling unsubscribe, not a failure.
      if (closed || (error as Error)?.name === 'AbortError') return;
    }

    if (closed) return;
    timer = setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, MAX_RETRY_MS);
  }

  void connect();

  return () => {
    closed = true;
    controller?.abort();
    if (timer) clearTimeout(timer);
  };
}

async function readFrames(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: ClarusEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    // The server ended the stream — its lifetime cap, or a restart. Either
    // way the caller reconnects.
    if (done) return;

    // stream: true so a multi-byte character split across two chunks is held
    // rather than decoded into a replacement character.
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseFrame(frame);
      if (parsed) onEvent(parsed);
      boundary = buffer.indexOf('\n\n');
    }
  }
}

function parseFrame(frame: string): ClarusEvent | null {
  let name = 'message';
  let data = '';

  for (const line of frame.split('\n')) {
    // Comment frames. The server sends these as heartbeats, to stop proxies
    // treating an idle stream as a dead one.
    if (line.startsWith(':')) continue;
    if (line.startsWith('event:')) name = line.slice(6).trim();
    else if (line.startsWith('data:')) data += line.slice(5).trim();
  }

  // Bookkeeping, not a change: the server is about to close so the next
  // connection can carry a fresh token. Reconnecting is handled by the stream
  // ending; surfacing it would trigger a pointless re-fetch.
  if (name === 'reconnect' || !data) return null;

  try {
    const payload = JSON.parse(data) as { id?: string };
    return payload.id ? { name, id: payload.id } : null;
  } catch {
    return null;
  }
}
