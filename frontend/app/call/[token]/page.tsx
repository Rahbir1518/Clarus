'use client';

/**
 * The page an emailed call link opens. The patient taps once and talks to the
 * appointment agent in their browser: no account, no app.
 *
 * Public by design (see proxy.ts). The token in the URL is the only credential,
 * and the backend checks it on every request — this page decides nothing about
 * access. Nothing here names the patient or the reason for the call before
 * they answer; the agent confirms who it is speaking to first, as it does on
 * a phone call.
 */

import { ConversationProvider } from '@elevenlabs/react';
import { Loader2, Mic, Phone, PhoneOff } from 'lucide-react';
import { use, useCallback, useEffect, useState } from 'react';

import { useWebCall } from '@/components/calls/use-web-call';
import {
  answerCallLink,
  bindCallLink,
  CallLinkError,
  describeCallLink,
  type CallLinkInfo,
} from '@/services/api';

type Language = CallLinkInfo['language'];
type Unavailable = 'answered' | 'closed' | 'expired' | 'invalid' | 'error';

const COPY = {
  en: {
    loading: 'Opening your call…',
    calling: '{practice} is calling you',
    explain: 'Tap Answer to start the call. Your browser will ask to use your microphone. Please allow it.',
    answer: 'Answer',
    connecting: 'Connecting…',
    inCall: 'On a call with {practice}',
    speaking: 'Speaking…',
    listening: 'Listening…',
    end: 'End call',
    ended: 'The call has ended. Thank you, you can close this page.',
    micDenied:
      'Your microphone is blocked. Allow microphone access for this page in your browser settings, then tap Answer again.',
    failed: 'The call could not be started. Please try again.',
    answered: 'This call has already been answered.',
    closed: 'This call is no longer available.',
    expired: 'This link has expired. Please contact the practice if you still need to speak with them.',
    invalid: 'This link is not valid. Please check that you opened the full link from your email.',
    error: 'We could not open this call. Please check your connection and try again.',
  },
  bn: {
    loading: 'আপনার কল খোলা হচ্ছে…',
    calling: '{practice} আপনাকে কল করছে',
    explain:
      'কল শুরু করতে "কল ধরুন" চাপুন। আপনার ব্রাউজার মাইক্রোফোন ব্যবহারের অনুমতি চাইবে, অনুগ্রহ করে অনুমতি দিন।',
    answer: 'কল ধরুন',
    connecting: 'সংযোগ হচ্ছে…',
    inCall: '{practice}-এর সাথে কথা চলছে',
    speaking: 'কথা বলছে…',
    listening: 'শুনছে…',
    end: 'কল শেষ করুন',
    ended: 'কলটি শেষ হয়েছে। ধন্যবাদ, আপনি এখন এই পেজটি বন্ধ করতে পারেন।',
    micDenied:
      'আপনার মাইক্রোফোন বন্ধ আছে। ব্রাউজারের সেটিংসে এই পেজের জন্য মাইক্রোফোনের অনুমতি দিন, তারপর আবার "কল ধরুন" চাপুন।',
    failed: 'কলটি শুরু করা যায়নি। অনুগ্রহ করে আবার চেষ্টা করুন।',
    answered: 'এই কলটি ইতিমধ্যে ধরা হয়েছে।',
    closed: 'এই কলটি আর পাওয়া যাচ্ছে না।',
    expired: 'এই লিংকটির মেয়াদ শেষ হয়ে গেছে। এখনও কথা বলতে চাইলে অনুগ্রহ করে ক্লিনিকে যোগাযোগ করুন।',
    invalid: 'এই লিংকটি সঠিক নয়। ইমেইল থেকে পুরো লিংকটি খুলেছেন কিনা দেখে নিন।',
    error: 'কলটি খোলা যায়নি। আপনার ইন্টারনেট সংযোগ দেখে আবার চেষ্টা করুন।',
  },
} satisfies Record<Language, Record<string, string>>;

type Copy = (typeof COPY)[Language];

function withPractice(text: string, practice: string): string {
  return text.replace('{practice}', practice);
}

type LinkState =
  | { kind: 'loading' }
  | { kind: 'ready'; info: CallLinkInfo }
  // `language` is null when the link could not be read at all, so there is no
  // patient to take it from; the message is then shown in both.
  | { kind: 'unavailable'; reason: Unavailable; language: Language | null };

function unavailableReason(error: unknown): Unavailable {
  if (!(error instanceof CallLinkError)) return 'error';
  if (error.status === 410) return 'expired';
  if (error.status === 404) return 'invalid';
  return 'error';
}

export default function CallLinkPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [state, setState] = useState<LinkState>({ kind: 'loading' });

  useEffect(() => {
    describeCallLink(token)
      .then((info) =>
        setState(
          info.status === 'ready'
            ? { kind: 'ready', info }
            : { kind: 'unavailable', reason: info.status, language: info.language },
        ),
      )
      .catch((error: unknown) =>
        setState({ kind: 'unavailable', reason: unavailableReason(error), language: null }),
      );
  }, [token]);

  if (state.kind === 'loading') {
    return (
      <Shell>
        <Loader2 className="mx-auto size-8 animate-spin text-muted-foreground" aria-hidden />
        <p className="text-muted-foreground" aria-live="polite">
          {COPY.en.loading}
        </p>
      </Shell>
    );
  }

  if (state.kind === 'unavailable') {
    const languages: Language[] = state.language ? [state.language] : ['en', 'bn'];
    return (
      <Shell>
        {languages.map((language) => (
          <p key={language} lang={language} className="text-lg">
            {COPY[language][state.reason]}
          </p>
        ))}
      </Shell>
    );
  }

  return (
    <ConversationProvider>
      <AnswerCall token={token} info={state.info} />
    </ConversationProvider>
  );
}

function AnswerCall({ token, info }: { token: string; info: CallLinkInfo }) {
  const copy: Copy = COPY[info.language];
  const [ended, setEnded] = useState(false);

  const begin = useCallback(() => answerCallLink(token), [token]);
  const bind = useCallback(
    (_callLogId: string, conversationId: string) => bindCallLink(token, conversationId),
    [token],
  );
  const call = useWebCall({ begin, bind, onEnded: () => setEnded(true) });

  if (ended) {
    return (
      <Shell lang={info.language}>
        <p className="text-lg">{copy.ended}</p>
      </Shell>
    );
  }

  if (call.connected) {
    return (
      <Shell lang={info.language}>
        <p className="text-sm text-muted-foreground">{withPractice(copy.inCall, info.practice_name)}</p>
        <div className="relative mx-auto flex size-28 items-center justify-center">
          <span
            className={`absolute inset-0 rounded-full bg-primary/20 ${call.isSpeaking ? 'animate-ping' : ''}`}
            aria-hidden
          />
          <span className="relative flex size-24 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <Mic className="size-10" aria-hidden />
          </span>
        </div>
        <p className="text-lg font-medium" aria-live="polite">
          {call.isSpeaking ? copy.speaking : copy.listening}
        </p>
        <button
          type="button"
          onClick={call.end}
          className="mx-auto flex items-center gap-2 rounded-full bg-destructive px-6 py-3 font-medium text-white"
        >
          <PhoneOff className="size-5" aria-hidden />
          {copy.end}
        </button>
      </Shell>
    );
  }

  return (
    <Shell lang={info.language}>
      <h1 className="text-2xl font-semibold">{withPractice(copy.calling, info.practice_name)}</h1>
      <p className="text-muted-foreground">{copy.explain}</p>
      <button
        type="button"
        onClick={call.start}
        disabled={call.starting}
        className="mx-auto flex size-28 flex-col items-center justify-center gap-1 rounded-full bg-emerald-600 font-semibold text-white shadow-lg transition hover:bg-emerald-700 disabled:opacity-60"
      >
        {call.starting ? (
          <Loader2 className="size-8 animate-spin" aria-hidden />
        ) : (
          <Phone className="size-8" aria-hidden />
        )}
        <span className="text-sm">{call.starting ? copy.connecting : copy.answer}</span>
      </button>
      {call.error && (
        <p className="text-sm text-destructive" role="alert">
          {call.error.includes('Microphone') ? copy.micDenied : copy.failed}
        </p>
      )}
    </Shell>
  );
}

function Shell({ children, lang }: { children: React.ReactNode; lang?: Language }) {
  return (
    <main lang={lang} className="flex min-h-dvh items-center justify-center bg-background px-4 py-10">
      <div className="flex w-full max-w-sm flex-col gap-6 rounded-2xl border border-border bg-card p-8 text-center shadow-sm">
        {children}
      </div>
    </main>
  );
}
