"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";

import { setAuthTokenGetter } from "@/services/api";

/**
 * Hands Clerk's `getToken` to the API layer.
 *
 * `services/api.ts` is a plain module and cannot call a React hook, but every
 * request it makes needs a session token. This component is the one place the
 * two meet: it renders nothing, mounts once at the root, and keeps the
 * registration in step with Clerk's session.
 *
 * The token itself is never stored here — only the function that fetches a
 * fresh one — so nothing holds a credential past its ~60 second lifetime.
 */
export default function ClerkTokenBridge() {
  const { getToken } = useAuth();

  useEffect(() => {
    setAuthTokenGetter(() => getToken());
    // Unregister on unmount so a torn-down tree cannot leave a stale getter
    // behind pointing at a signed-out session.
    return () => setAuthTokenGetter(null);
  }, [getToken]);

  return null;
}
