'use client';

/**
 * Hand a waiting call to the patient: copy its link, or email it to them.
 *
 * Copying is the fallback that always works — when the email went to spam,
 * when the server has no mail account, or when it is quicker to paste the
 * link into a chat. If the clipboard is unavailable the link is shown instead.
 */

import { Copy, Mail } from 'lucide-react';
import { useState } from 'react';

import { emailCallLink, getCallLink } from '@/services/api';

type Notice = { kind: 'ok' | 'error'; text: string; url?: string };

export function CallLinkActions({
  callLogId,
  onEmailed,
}: {
  callLogId: string;
  onEmailed?: () => void;
}) {
  const [busy, setBusy] = useState<'copy' | 'email' | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const copyLink = async () => {
    setBusy('copy');
    setNotice(null);
    try {
      const { url } = await getCallLink(callLogId);
      try {
        await navigator.clipboard.writeText(url);
        setNotice({ kind: 'ok', text: 'Link copied. It works once and expires in a day.' });
      } catch {
        setNotice({ kind: 'ok', text: 'Copy this link:', url });
      }
    } catch (e) {
      setNotice({ kind: 'error', text: e instanceof Error ? e.message : 'Could not create the link.' });
    } finally {
      setBusy(null);
    }
  };

  const emailLink = async () => {
    setBusy('email');
    setNotice(null);
    try {
      await emailCallLink(callLogId);
      setNotice({ kind: 'ok', text: 'Emailed to the patient.' });
      onEmailed?.();
    } catch (e) {
      setNotice({ kind: 'error', text: e instanceof Error ? e.message : 'Could not email the link.' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={copyLink}
          disabled={busy !== null}
          className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          <Copy className="size-4" aria-hidden />
          {busy === 'copy' ? 'Creating link…' : 'Copy link'}
        </button>
        <button
          type="button"
          onClick={emailLink}
          disabled={busy !== null}
          className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          <Mail className="size-4" aria-hidden />
          {busy === 'email' ? 'Sending…' : 'Email patient'}
        </button>
      </div>
      {notice && (
        <p
          className={`text-sm ${notice.kind === 'error' ? 'text-destructive' : 'text-muted-foreground'}`}
          role={notice.kind === 'error' ? 'alert' : 'status'}
        >
          {notice.text}
          {notice.url && <span className="mt-1 block break-all font-mono text-xs select-all">{notice.url}</span>}
        </p>
      )}
    </div>
  );
}
