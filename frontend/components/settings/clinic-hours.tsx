'use client';

/**
 * Opening hours and appointment length, as the practice sets them.
 *
 * Kept until the doctor changes them. The agent reads both on every call: it
 * offers only free times inside these hours, and tells a patient who asks for
 * a closed day or an after-hours time why that will not work.
 *
 * Several ranges per day are allowed (a lunch break is two ranges), because
 * the backend stores them that way — an editor that showed only the first
 * would quietly delete the rest on the next save.
 */

import { useEffect, useState } from 'react';
import { Clock, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  getPracticeSettings,
  updatePracticeSettings,
  type ClinicHours,
  type TimeRange,
  type Weekday,
} from '@/services/api';

const DAYS: { key: Weekday; label: string }[] = [
  { key: 'sat', label: 'Saturday' },
  { key: 'sun', label: 'Sunday' },
  { key: 'mon', label: 'Monday' },
  { key: 'tue', label: 'Tuesday' },
  { key: 'wed', label: 'Wednesday' },
  { key: 'thu', label: 'Thursday' },
  { key: 'fri', label: 'Friday' },
];

// What a day gets when it is switched open. A starting point to edit, not a
// rule — nothing is saved until the doctor presses Save.
const NEW_RANGE: TimeRange = { start: '09:00', end: '17:00' };

const LENGTHS = [10, 15, 20, 30, 45, 60, 90];

function emptyWeek(): ClinicHours {
  return { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] };
}

export function ClinicHoursCard() {
  const [hours, setHours] = useState<ClinicHours>(emptyWeek);
  const [minutes, setMinutes] = useState(30);
  const [timezone, setTimezone] = useState('');
  const [neverSet, setNeverSet] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getPracticeSettings()
      .then((s) => {
        setHours({ ...emptyWeek(), ...(s.clinic_hours ?? {}) });
        setMinutes(s.appointment_minutes);
        setTimezone(s.timezone);
        setNeverSet(s.clinic_hours === null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const update = (day: Weekday, ranges: TimeRange[]) => {
    setSaved(false);
    setHours((h) => ({ ...h, [day]: ranges }));
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const s = await updatePracticeSettings(hours, minutes);
      setHours({ ...emptyWeek(), ...(s.clinic_hours ?? {}) });
      setMinutes(s.appointment_minutes);
      setNeverSet(false);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const lengths = LENGTHS.includes(minutes) ? LENGTHS : [...LENGTHS, minutes].sort((a, b) => a - b);

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="border-b border-border px-5 py-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Clock className="size-4" /> Clinic hours
        </h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          When the AI agent may book patients. It offers only free times inside these hours.
          {timezone && <> Times are in {timezone}.</>}
        </p>
      </div>

      <div className="space-y-4 p-5">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            {neverSet && (
              <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
                No hours saved yet. Until you save them, the agent will not offer any
                appointment times and will tell patients the practice will call back.
              </p>
            )}

            <div className="divide-y divide-border">
              {DAYS.map(({ key, label }) => {
                const ranges = hours[key];
                const open = ranges.length > 0;
                return (
                  <div key={key} className="flex flex-wrap items-start gap-3 py-2.5">
                    <label className="flex w-32 items-center gap-2 pt-1.5 text-sm">
                      <input
                        type="checkbox"
                        checked={open}
                        onChange={(e) => update(key, e.target.checked ? [{ ...NEW_RANGE }] : [])}
                      />
                      {label}
                    </label>

                    {!open ? (
                      <span className="pt-1.5 text-sm text-muted-foreground">Closed</span>
                    ) : (
                      <div className="flex flex-col gap-2">
                        {ranges.map((range, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <input
                              type="time"
                              value={range.start}
                              aria-label={`${label} opens`}
                              onChange={(e) =>
                                update(key, ranges.map((r, j) => (j === i ? { ...r, start: e.target.value } : r)))
                              }
                              className="rounded-md border bg-background px-2 py-1 text-sm"
                            />
                            <span className="text-sm text-muted-foreground">to</span>
                            <input
                              type="time"
                              value={range.end}
                              aria-label={`${label} closes`}
                              onChange={(e) =>
                                update(key, ranges.map((r, j) => (j === i ? { ...r, end: e.target.value } : r)))
                              }
                              className="rounded-md border bg-background px-2 py-1 text-sm"
                            />
                            {ranges.length > 1 && (
                              <button
                                type="button"
                                aria-label="Remove this range"
                                onClick={() => update(key, ranges.filter((_, j) => j !== i))}
                                className="text-muted-foreground hover:text-destructive"
                              >
                                <Trash2 className="size-4" />
                              </button>
                            )}
                          </div>
                        ))}
                        {ranges.length < 4 && (
                          <button
                            type="button"
                            onClick={() => update(key, [...ranges, { start: '14:00', end: '17:00' }])}
                            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                          >
                            <Plus className="size-3" /> Add another range (e.g. after a break)
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <label className="flex items-center gap-3 text-sm">
              Appointment length
              <select
                value={minutes}
                onChange={(e) => {
                  setSaved(false);
                  setMinutes(Number(e.target.value));
                }}
                className="rounded-md border bg-background px-2 py-1 text-sm"
              >
                {lengths.map((m) => (
                  <option key={m} value={m}>
                    {m} minutes
                  </option>
                ))}
              </select>
            </label>

            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <div className="flex items-center gap-3">
              <Button onClick={save} disabled={saving}>
                {saving ? 'Saving…' : 'Save clinic hours'}
              </Button>
              {saved && <span className="text-sm text-muted-foreground">Saved.</span>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
