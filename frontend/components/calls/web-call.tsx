'use client';

/**
 * Talk to the appointment agent from the browser, over WebRTC.
 *
 * This is the same agent, the same dynamic variables and the same post-call
 * webhook the phone path uses — only the transport differs. It exists because
 * Bangladesh has no Twilio numbers and international VoIP termination into BD
 * is slow to arrange, so the system is proved end to end with no carrier in
 * the loop while a local IPTSP trunk is negotiated.
 *
 * Nothing here is throwaway. When the trunk lands, this component stays as the
 * in-app calling surface and the phone leg is added beside it. The call itself
 * lives in useWebCall, which the patient's call-link page shares.
 */

import { ConversationProvider } from '@elevenlabs/react';

import { useWebCall, type UseWebCallOptions } from '@/components/calls/use-web-call';
import { bindCall } from '@/services/api';

type Props = Omit<UseWebCallOptions, 'bind'> & {
  /** The start button's label. */
  startLabel?: string;
};

function WebCallInner({ begin, startLabel = 'Start call', onEnded }: Props) {
  const call = useWebCall({ begin, bind: bindCall, onEnded });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={call.start}
          disabled={call.connected || call.starting}
          className="rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
        >
          {call.starting ? 'Connecting…' : startLabel}
        </button>
        <button
          type="button"
          onClick={call.end}
          disabled={!call.connected}
          className="rounded-md border px-4 py-2 disabled:opacity-50"
        >
          End call
        </button>
      </div>

      <p className="text-sm text-muted-foreground" aria-live="polite">
        {call.connected ? (call.isSpeaking ? 'Agent speaking…' : 'Listening…') : call.status}
      </p>

      {call.error && (
        <p className="text-sm text-destructive" role="alert">
          {call.error}
        </p>
      )}
    </div>
  );
}

/**
 * useConversation must run inside a ConversationProvider, so the export wraps
 * it. Callers get one component and cannot forget the provider.
 */
export function WebCall(props: Props) {
  return (
    <ConversationProvider>
      <WebCallInner {...props} />
    </ConversationProvider>
  );
}
