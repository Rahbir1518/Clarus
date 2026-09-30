'use client';

/**
 * The names the AI agent says on every call.
 *
 * The account holder is the doctor; the practice is the clinic they call
 * from. The agent opens with "…an automated call from <practice> on behalf of
 * <doctor>", so both are what a patient hears first. Until they are set, the
 * agent falls back to the deployment's PRACTICE_NAME (which is the software's
 * name, "Clarus") and to the patient's recorded physician.
 */

import { useUser } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import { Building2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { getPracticeSettings, updatePracticeProfile } from '@/services/api';

export function PracticeProfileCard() {
  const { user } = useUser();
  const [doctorName, setDoctorName] = useState('');
  const [practiceName, setPracticeName] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPracticeSettings()
      .then((s) => {
        setDoctorName(s.doctor_name ?? '');
        setPracticeName(s.practice_name ?? '');
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // A suggestion only, from the signed-in account; nothing is saved until Save.
  const suggestedDoctor = user?.fullName ? `Dr. ${user.fullName}` : 'Dr. …';

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const s = await updatePracticeProfile(doctorName, practiceName);
      setDoctorName(s.doctor_name ?? '');
      setPracticeName(s.practice_name ?? '');
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const shownDoctor = doctorName.trim() || '[doctor]';
  const shownPractice = practiceName.trim() || '[practice]';

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="border-b border-border px-5 py-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Building2 className="size-4" /> Practice profile
        </h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          The names the AI agent says when it calls a patient.
        </p>
      </div>

      <div className="space-y-4 p-5">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-xs font-medium">
                Doctor&apos;s name, as spoken
                <input
                  value={doctorName}
                  maxLength={80}
                  placeholder={suggestedDoctor}
                  onChange={(e) => {
                    setSaved(false);
                    setDoctorName(e.target.value);
                  }}
                  className="rounded-md border bg-background px-2 py-1.5 text-sm font-normal"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium">
                Practice / clinic name
                <input
                  value={practiceName}
                  maxLength={100}
                  placeholder="e.g. Green Life Clinic"
                  onChange={(e) => {
                    setSaved(false);
                    setPracticeName(e.target.value);
                  }}
                  className="rounded-md border bg-background px-2 py-1.5 text-sm font-normal"
                />
              </label>
            </div>

            <div className="rounded-md bg-muted/50 p-3 text-sm">
              <p className="text-xs font-medium text-muted-foreground">The agent opens with</p>
              <p className="mt-1">
                হ্যালো, এটি {shownDoctor}-এর পক্ষ থেকে {shownPractice}-এর একটি স্বয়ংক্রিয় কল।
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                &ldquo;Hello, this is an automated call from {shownPractice} on behalf of {shownDoctor}.&rdquo;
              </p>
            </div>

            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <div className="flex items-center gap-3">
              <Button onClick={save} disabled={saving || !doctorName.trim() || !practiceName.trim()}>
                {saving ? 'Saving…' : 'Save profile'}
              </Button>
              {saved && <span className="text-sm text-muted-foreground">Saved.</span>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
