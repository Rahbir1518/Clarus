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
 * in-app calling surface and the phone leg is added beside it.
 */

import { useConversation, ConversationProvider } from '@elevenlabs/react';
import { useCallback, useRef, useState } from 'react';

import { bindCall, startWebCall, type CallReasonCode } from '@/services/api';

type Props = {
  patientId: string;
  /**
   * Which of the permitted reasons the patient is given for the call — a code,
   * not a sentence. The words themselves live on the server and are not settable
   * from here, because anything settable from here is spoken to a patient. See
   * AI_CALL_SAFETY_POLICY.md.
   *
   * The callback number a voicemail asks the patient to ring is configuration
   * (PRACTICE_CALLBACK_NUMBER), for the same reason.
   */
  reasonCode?: CallReasonCode;
  onEnded?: (callLogId: string) => void;
};

function WebCallInner({ patientId, reasonCode, onEnded }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  // A ref, not state: onConnect fires from the SDK outside React's render
  // cycle, and reading a stale closure over `callLogId` there would bind the
  // conversation to the previous call — or to nothing at all.
  const callLogId = useRef<string | null>(null);

  const conversation = useConversation({
    onConnect: ({ conversationId }) => {
      const id = callLogId.current;
      if (!id) return;
      // Bind on connect rather than on hang-up. The post-call webhook can
      // arrive within seconds of the conversation ending, and it silently
      // drops any outcome whose conversation_id resolves to no call log.
      bindCall(id, conversationId).catch((e: Error) => setError(e.message));
    },
    onDisconnect: () => {
      if (callLogId.current) onEnded?.(callLogId.current);
    },
    onError: (message: string) => setError(message),
  });

  const start = useCallback(async () => {
    setError(null);
    setStarting(true);
    try {
      // Ask before minting anything. Browsers only grant the microphone from a
      // user gesture, and a denied prompt should not leave a started call log
      // and a spent token behind.
      await navigator.mediaDevices.getUserMedia({ audio: true });

      const session = await startWebCall(patientId, { reasonCode });
      callLogId.current = session.call_log_id;

      conversation.startSession({
        conversationToken: session.token,
        connectionType: 'webrtc',
        // Passed through exactly as the server built them. A key missing here
        // is not an error at the API — it reaches the patient as the literal
        // spoken text "{{patient_name}}".
        dynamicVariables: session.dynamic_variables,
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(
        message.includes('Permission') || message.includes('denied')
          ? 'Microphone access is required to place the call.'
          : message,
      );
      callLogId.current = null;
    } finally {
      setStarting(false);
    }
  }, [patientId, reasonCode, conversation]);

  const connected = conversation.status === 'connected';

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={start}
          disabled={connected || starting}
          className="rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
        >
          {starting ? 'Connecting…' : 'Start call'}
        </button>
        <button
          type="button"
          onClick={() => conversation.endSession()}
          disabled={!connected}
          className="rounded-md border px-4 py-2 disabled:opacity-50"
        >
          End call
        </button>
      </div>

      <p className="text-sm text-muted-foreground" aria-live="polite">
        {connected
          ? conversation.isSpeaking
            ? 'Agent speaking…'
            : 'Listening…'
          : conversation.status}
      </p>

      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
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
