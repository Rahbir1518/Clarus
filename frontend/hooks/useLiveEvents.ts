'use client';

import { useEffect, useRef } from 'react';
import { useAuth } from '@clerk/nextjs';

import { subscribeToEvents, type ClarusEvent } from '@/services/events';

/**
 * Run `handler` whenever the backend reports a change for the signed-in
 * doctor.
 *
 * The handler is held in a ref rather than listed as a dependency. A caller
 * naturally passes an inline arrow function, and depending on it would tear
 * down and re-open the stream on every render — reconnecting several times a
 * second while looking like it works.
 *
 * Gated on `isSignedIn` so the stream is never opened without a token, which
 * would otherwise be a 401 answered by the reconnect backoff.
 */
export function useLiveEvents(handler: (event: ClarusEvent) => void): void {
  const { isSignedIn } = useAuth();
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    if (!isSignedIn) return;
    return subscribeToEvents((event) => handlerRef.current(event));
  }, [isSignedIn]);
}
