'use client';

/**
 * The life of one browser call with the appointment agent, over WebRTC.
 *
 * Shared by the staff surface (web-call.tsx) and the page a patient opens from
 * an emailed call link (app/call/[token]/page.tsx). They differ in how a call
 * is begun and bound — a signed-in session or the link — and in how they look;
 * the order of operations below is the same for both and must stay that way.
 *
 * Must be used inside an ElevenLabs ConversationProvider.
 */

import { useConversation } from '@elevenlabs/react';
import { useCallback, useRef, useState } from 'react';

import type { WebCallStarted } from '@/services/api';

export type UseWebCallOptions = {
  /**
   * Creates or claims the call log and mints the token. The server builds the
   * dynamic variables and this passes them through untouched — anything
   * settable from here is spoken to a patient. See
   * docs/ai-call-safety-policy.md.
   */
  begin: () => Promise<WebCallStarted>;
  /** Reports the conversation id back, so the post-call webhook can find the call. */
  bind: (callLogId: string, conversationId: string) => Promise<void>;
  onEnded?: (callLogId: string) => void;
};

export function useWebCall({ begin, bind, onEnded }: UseWebCallOptions) {
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
      bind(id, conversationId).catch((e: Error) => setError(e.message));
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

      const session = await begin();
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
  }, [begin, conversation]);

  const end = useCallback(() => conversation.endSession(), [conversation]);

  return {
    start,
    end,
    starting,
    error,
    status: conversation.status,
    connected: conversation.status === 'connected',
    isSpeaking: conversation.isSpeaking,
  };
}
