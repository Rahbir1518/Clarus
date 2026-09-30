"use client";

/**
 * The practice's calendar, as a week.
 *
 * This is what the AI agent reads during a call: every appointment here is a
 * time it will not offer, and the shaded hours are the ones it will refuse.
 * Appointments come from two places — booked by the agent on a call, or added
 * by hand — and both occupy their slot the same way.
 *
 * Everything is drawn in the practice's timezone, not the browser's: a block at
 * 10:00 means ten o'clock at the clinic, wherever the person looking is. Dates
 * are handled as "YYYY-MM-DD" strings in that zone and never as local Date
 * objects, which would silently shift a day for anyone west of it.
 *
 * The week starts on Saturday, as the clinic's does (and as Settings lists it).
 * A sideways wheel or trackpad swipe (or Shift + wheel) anywhere on the
 * calendar, or a plain wheel over the week bar and day headers, moves between
 * weeks.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useUser } from "@clerk/nextjs";
import { Bot, ChevronLeft, ChevronRight, Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import { cn } from "@/lib/utils";
import {
  cancelAppointment,
  createAppointment,
  getPracticeSettings,
  listAppointments,
  listPatients,
  type Appointment,
  type ClinicHours,
  type Weekday,
} from "@/services/api";

type Patient = { id: string; name: string };

// Pixels per hour on the grid.
const HOUR_PX = 56;
// Sunday-first, matching Date.getUTCDay().
const WEEKDAY_KEYS: Weekday[] = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const WEEKDAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
// Saturday.
const WEEK_STARTS_ON = 6;
// Wheel travel needed to move one week, and the pause before the next move,
// so one trackpad swipe or wheel flick is one week rather than several.
const WHEEL_STEP = 60;
const WHEEL_COOLDOWN_MS = 400;

// ---------------------------------------------------------------------------
// Dates in the practice's zone
// ---------------------------------------------------------------------------

type ZonedParts = { date: string; minutes: number };

function zoned(instant: Date, timeZone: string): ZonedParts {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(instant)
      .map((p) => [p.type, p.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
  };
}

function addDays(date: string, days: number): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function weekday(date: string): number {
  return new Date(`${date}T00:00:00Z`).getUTCDay();
}

function weekStart(date: string): string {
  return addDays(date, -((weekday(date) - WEEK_STARTS_ON + 7) % 7));
}

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

function hhmm(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

function dayLabel(date: string, style: "short" | "long"): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: style,
    day: "numeric",
    month: style === "long" ? "long" : "short",
  });
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type Placed = Appointment & { date: string; start: number; end: number; lane: number; lanes: number };

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [timezone, setTimezone] = useState<string | null>(null);
  const [hours, setHours] = useState<ClinicHours | null>(null);
  const [slotMinutes, setSlotMinutes] = useState(30);
  const [week, setWeek] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  const [error, setError] = useState<string | null>(null);
  const [showCancelled, setShowCancelled] = useState(false);
  const [selected, setSelected] = useState<Appointment | null>(null);
  const [draft, setDraft] = useState<{ date: string; time: string } | null>(null);
  const { user } = useUser();
  const doctorId = user?.id;

  const loadPatients = useCallback(() => {
    listPatients(doctorId)
      .then((rows: Patient[]) => setPatients(Array.isArray(rows) ? rows : []))
      .catch(() => setPatients([]));
  }, [doctorId]);

  const refresh = useCallback(() => {
    listAppointments()
      .then((rows) => {
        setError(null);
        setAppointments(rows);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // Wait for Clerk: the API layer only has a session token once it has loaded,
  // and a request sent before then is refused — which is how agent-booked
  // appointments ended up showing "Unknown patient".
  useEffect(() => {
    if (!doctorId) return;
    refresh();
    loadPatients();
    getPracticeSettings()
      .then((s) => {
        setTimezone(s.timezone);
        setHours(s.clinic_hours);
        setSlotMinutes(s.appointment_minutes);
      })
      .catch(() => setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone));
    const tick = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(tick);
  }, [doctorId, refresh, loadPatients]);

  useLiveEvents((event) => {
    if (event.name === "appointment.updated" || event.name === "call_log.updated") refresh();
  });

  // A booking can name a patient added after this page loaded (a PDF import,
  // another tab). Fetch the list again rather than label them unknown.
  const missingPatient = appointments.some(
    (a) => a.patient_id && !patients.some((p) => p.id === a.patient_id),
  );
  const lastPatientReload = useRef("");
  useEffect(() => {
    if (!doctorId || !missingPatient) return;
    const key = appointments.map((a) => a.patient_id).join(",");
    if (lastPatientReload.current === key) return;
    lastPatientReload.current = key;
    loadPatients();
  }, [doctorId, missingPatient, appointments, loadPatients]);

  const today = timezone ? zoned(now, timezone).date : null;
  const shownWeek = week ?? (today ? weekStart(today) : null);
  const days = useMemo(
    () => (shownWeek ? Array.from({ length: 7 }, (_, i) => addDays(shownWeek, i)) : []),
    [shownWeek],
  );

  const patientName = (id: string | null) =>
    patients.find((p) => p.id === id)?.name ?? "Unknown patient";

  // This week's appointments, positioned, with side-by-side lanes for any that
  // overlap (only possible when cancelled ones are shown).
  const placed = useMemo(() => {
    if (!timezone) return [] as Placed[];
    const inWeek = new Set(days);
    const rows = appointments
      .filter((a) => showCancelled || a.status !== "cancelled")
      .map((a) => {
        const s = zoned(new Date(a.starts_at), timezone);
        const endAt = a.ends_at ? new Date(a.ends_at) : new Date(new Date(a.starts_at).getTime() + slotMinutes * 60_000);
        const e = zoned(endAt, timezone);
        // An appointment that crosses midnight is drawn to the end of its day.
        const end = e.date === s.date ? e.minutes : 24 * 60;
        return { ...a, date: s.date, start: s.minutes, end: Math.max(end, s.minutes + 10), lane: 0, lanes: 1 };
      })
      .filter((a) => inWeek.has(a.date))
      .sort((a, b) => a.date.localeCompare(b.date) || a.start - b.start);

    for (const day of days) {
      const today = rows.filter((r) => r.date === day);
      const laneEnds: number[] = [];
      for (const r of today) {
        const lane = laneEnds.findIndex((end) => end <= r.start);
        r.lane = lane === -1 ? laneEnds.length : lane;
        laneEnds[r.lane] = r.end;
      }
      for (const r of today) r.lanes = Math.max(1, laneEnds.length);
    }
    return rows;
  }, [appointments, days, timezone, showCancelled, slotMinutes]);

  // Grid range: clinic hours for the week plus anything booked outside them,
  // rounded out to whole hours, at least 08:00-18:00.
  const [gridStart, gridEnd] = useMemo(() => {
    let lo = 8 * 60;
    let hi = 18 * 60;
    for (const day of days) {
      for (const r of hours?.[WEEKDAY_KEYS[weekday(day)]] ?? []) {
        lo = Math.min(lo, toMinutes(r.start));
        hi = Math.max(hi, toMinutes(r.end));
      }
    }
    for (const a of placed) {
      lo = Math.min(lo, a.start);
      hi = Math.max(hi, a.end);
    }
    return [Math.floor(lo / 60) * 60, Math.min(24 * 60, Math.ceil(hi / 60) * 60)];
  }, [days, hours, placed]);

  const hourMarks = Array.from({ length: (gridEnd - gridStart) / 60 }, (_, i) => gridStart + i * 60);
  const y = (minutes: number) => ((minutes - gridStart) / 60) * HOUR_PX;
  const nowParts = timezone ? zoned(now, timezone) : null;

  const openRanges = (day: string) => hours?.[WEEKDAY_KEYS[weekday(day)]] ?? [];

  const clickSlot = (day: string, offsetY: number) => {
    // Snap to the practice's appointment length, from the grid's first hour.
    const raw = gridStart + (offsetY / HOUR_PX) * 60;
    const snapped = gridStart + Math.floor((raw - gridStart) / slotMinutes) * slotMinutes;
    setSelected(null);
    setDraft({ date: day, time: hhmm(snapped) });
  };

  // Wheel navigation between weeks. Attached by hand because React's onWheel is
  // passive and cannot stop the page from scrolling sideways as well.
  const calendarRef = useRef<HTMLDivElement>(null);
  const shownWeekRef = useRef(shownWeek);
  useEffect(() => {
    shownWeekRef.current = shownWeek;
  }, [shownWeek]);
  useEffect(() => {
    const el = calendarRef.current;
    if (!el) return;
    let travel = 0;
    let lastMove = 0;
    const onWheel = (e: WheelEvent) => {
      const target = e.target as HTMLElement | null;
      const overHeader = Boolean(target?.closest("[data-week-wheel]"));
      const sideways = Math.abs(e.deltaX) > Math.abs(e.deltaY);
      const dx = sideways ? e.deltaX : e.shiftKey || overHeader ? e.deltaY : 0;
      if (dx === 0) return;
      // A grid wider than the screen scrolls sideways first; weeks change once
      // it is at its edge.
      const scroller = el.querySelector<HTMLElement>("[data-calendar-scroll]");
      if (scroller && !overHeader) {
        const max = scroller.scrollWidth - scroller.clientWidth;
        if (max > 1 && ((dx < 0 && scroller.scrollLeft > 0) || (dx > 0 && scroller.scrollLeft < max - 1))) return;
      }
      e.preventDefault();
      const now = Date.now();
      if (now - lastMove < WHEEL_COOLDOWN_MS) return;
      travel += dx;
      if (Math.abs(travel) < WHEEL_STEP) return;
      const current = shownWeekRef.current;
      if (current) setWeek(addDays(current, travel > 0 ? 7 : -7));
      travel = 0;
      lastMove = now;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [timezone]);

  const weekTitle =
    days.length > 0 ? `${dayLabel(days[0], "short")} – ${dayLabel(days[6], "short")} ${days[6].slice(0, 4)}` : "";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Appointments</h1>
          <p className="text-sm text-muted-foreground">
            The AI agent only offers free times inside your clinic hours (Settings). Click an
            empty slot to add an appointment.
            {timezone && <> Times are in {timezone}.</>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="mr-2 flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={showCancelled}
              onChange={(e) => setShowCancelled(e.target.checked)}
            />
            Show cancelled
          </label>
          <Button
            onClick={() => {
              setSelected(null);
              setDraft({ date: today ?? "", time: "" });
            }}
          >
            <Plus className="size-4" /> New appointment
          </Button>
        </div>
      </div>

      <div ref={calendarRef} className="space-y-4">
      <div className="flex items-center gap-2" data-week-wheel title="Scroll here to change week">
        <Button variant="outline" size="sm" aria-label="Previous week" onClick={() => shownWeek && setWeek(addDays(shownWeek, -7))}>
          <ChevronLeft className="size-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={() => setWeek(null)}>
          Today
        </Button>
        <Button variant="outline" size="sm" aria-label="Next week" onClick={() => shownWeek && setWeek(addDays(shownWeek, 7))}>
          <ChevronRight className="size-4" />
        </Button>
        <span className="ml-2 text-sm font-medium">{weekTitle}</span>
        <span className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block size-3 rounded-sm bg-primary/80" /> Booked by AI agent
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block size-3 rounded-sm border border-border bg-secondary" /> Added by hand
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block size-3 rounded-sm bg-muted" /> Closed
          </span>
        </span>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/40 p-3 text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      {draft && (
        <AppointmentForm
          key={`${draft.date}-${draft.time}`}
          patients={patients}
          defaultMinutes={slotMinutes}
          initialDate={draft.date}
          initialTime={draft.time}
          onClose={() => setDraft(null)}
          onCreated={() => {
            refresh();
            setDraft(null);
          }}
        />
      )}

      {selected && (
        <AppointmentDetails
          key={selected.id}
          appointment={selected}
          patientName={patientName(selected.patient_id)}
          timezone={timezone ?? undefined}
          onClose={() => setSelected(null)}
          onCancelled={() => {
            refresh();
            setSelected(null);
          }}
        />
      )}

      {!timezone ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
          Loading calendar…
        </div>
      ) : (
        <div data-calendar-scroll className="overflow-x-auto rounded-xl border border-border bg-card">
          <div className="min-w-[760px]">
            {/* Day headers */}
            <div data-week-wheel className="grid grid-cols-[56px_repeat(7,1fr)] border-b border-border">
              <div />
              {days.map((day) => {
                const isToday = day === today;
                const closed = openRanges(day).length === 0;
                return (
                  <div key={day} className="border-l border-border px-2 py-2 text-center">
                    <p className={cn("text-xs text-muted-foreground", isToday && "font-semibold text-primary")}>
                      {WEEKDAY_SHORT[weekday(day)]}
                    </p>
                    <p
                      className={cn(
                        "mx-auto mt-0.5 flex size-7 items-center justify-center rounded-full text-sm",
                        isToday && "bg-primary text-primary-foreground",
                      )}
                    >
                      {Number(day.slice(8))}
                    </p>
                    {closed && <p className="text-[10px] text-muted-foreground">Closed</p>}
                  </div>
                );
              })}
            </div>

            {/* Grid */}
            <div className="grid grid-cols-[56px_repeat(7,1fr)]">
              <div className="relative" style={{ height: y(gridEnd) }}>
                {hourMarks.map((m) => (
                  <span
                    key={m}
                    className="absolute right-2 -translate-y-1/2 text-[10px] text-muted-foreground"
                    style={{ top: y(m) }}
                  >
                    {m === gridStart ? "" : hhmm(m)}
                  </span>
                ))}
              </div>

              {days.map((day) => (
                <div
                  key={day}
                  className="relative cursor-pointer border-l border-border bg-muted/60"
                  style={{ height: y(gridEnd) }}
                  onClick={(e) => clickSlot(day, e.clientY - e.currentTarget.getBoundingClientRect().top)}
                >
                  {/* Open hours */}
                  {openRanges(day).map((r) => (
                    <div
                      key={r.start}
                      className="absolute inset-x-0 bg-card"
                      style={{ top: y(toMinutes(r.start)), height: y(toMinutes(r.end)) - y(toMinutes(r.start)) }}
                    />
                  ))}

                  {/* Hour lines */}
                  {hourMarks.map((m) => (
                    <div key={m} className="pointer-events-none absolute inset-x-0 border-t border-border/60" style={{ top: y(m) }} />
                  ))}

                  {/* Now */}
                  {nowParts && nowParts.date === day && nowParts.minutes >= gridStart && nowParts.minutes <= gridEnd && (
                    <div className="pointer-events-none absolute inset-x-0 z-20 border-t-2 border-destructive" style={{ top: y(nowParts.minutes) }}>
                      <span className="absolute -left-1 -top-[5px] size-2 rounded-full bg-destructive" />
                    </div>
                  )}

                  {/* Appointments */}
                  {placed
                    .filter((a) => a.date === day)
                    .map((a) => {
                      const byAgent = Boolean(a.call_log_id);
                      const cancelled = a.status === "cancelled" || a.status === "no_show";
                      const height = y(a.end) - y(a.start);
                      return (
                        <button
                          key={a.id}
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDraft(null);
                            setSelected(a);
                          }}
                          className={cn(
                            "absolute z-10 overflow-hidden rounded-md border px-1.5 py-0.5 text-left text-[11px] leading-tight shadow-sm transition hover:brightness-95",
                            byAgent
                              ? "border-primary/40 bg-primary/80 text-primary-foreground"
                              : "border-border bg-secondary text-secondary-foreground",
                            cancelled && "line-through opacity-50",
                          )}
                          style={{
                            top: y(a.start) + 1,
                            height: Math.max(height - 2, 18),
                            left: `calc(${(a.lane / a.lanes) * 100}% + 2px)`,
                            width: `calc(${100 / a.lanes}% - 4px)`,
                          }}
                          title={`${hhmm(a.start)}–${hhmm(a.end)} ${patientName(a.patient_id)}${a.reason ? ` · ${a.reason}` : ""}`}
                        >
                          <span className="flex items-center gap-1 font-semibold">
                            {byAgent && <Bot className="size-3 shrink-0" />}
                            {hhmm(a.start)}
                          </span>
                          {height >= 34 && <span className="block truncate">{patientName(a.patient_id)}</span>}
                          {height >= 48 && a.reason && <span className="block truncate opacity-90">{a.reason}</span>}
                        </button>
                      );
                    })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Details
// ---------------------------------------------------------------------------

function AppointmentDetails({
  appointment,
  patientName,
  timezone,
  onClose,
  onCancelled,
}: {
  appointment: Appointment;
  patientName: string;
  timezone?: string;
  onClose: () => void;
  onCancelled: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const live = appointment.status !== "cancelled" && appointment.status !== "no_show";
  const fmt = (iso: string) =>
    new Date(iso).toLocaleString("en-GB", {
      timeZone: timezone,
      weekday: "long",
      day: "numeric",
      month: "long",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });

  const cancel = async () => {
    setBusy(true);
    setError(null);
    try {
      await cancelAppointment(appointment.id);
      onCancelled();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold">{patientName}</h3>
          <p className="text-sm">
            {fmt(appointment.starts_at)}
            {appointment.ends_at && <> – {new Date(appointment.ends_at).toLocaleTimeString("en-GB", { timeZone: timezone, hour: "2-digit", minute: "2-digit", hour12: false })}</>}
          </p>
          <p className="text-sm">
            <span className="font-medium">Reason for visit: </span>
            {appointment.reason || <span className="text-muted-foreground">Not recorded</span>}
          </p>
          <p className="text-xs text-muted-foreground">
            {appointment.call_log_id ? "Booked by the AI agent on a call" : "Added by hand"} ·{" "}
            <span className="capitalize">{appointment.status.replace("_", " ")}</span>
          </p>
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {live && (
            <Button variant="outline" size="sm" onClick={cancel} disabled={busy} className="text-destructive hover:text-destructive">
              {busy ? "Cancelling…" : "Cancel appointment"}
            </Button>
          )}
          <button type="button" aria-label="Close" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// New appointment
// ---------------------------------------------------------------------------

function AppointmentForm({
  patients,
  defaultMinutes,
  initialDate,
  initialTime,
  onClose,
  onCreated,
}: {
  patients: Patient[];
  defaultMinutes: number;
  initialDate: string;
  initialTime: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [patientId, setPatientId] = useState("");
  const [date, setDate] = useState(initialDate);
  const [time, setTime] = useState(initialTime);
  const [minutes, setMinutes] = useState<number | "">("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) {
      setError("Enter the reason for the visit.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createAppointment({
        patientId,
        date,
        time,
        durationMinutes: minutes === "" ? undefined : minutes,
        reason: reason.trim(),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">New appointment</h3>
        <button type="button" aria-label="Close" onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="size-4" />
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="flex flex-col gap-1 text-xs font-medium lg:col-span-2">
          Patient
          <select
            required
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            className="rounded-md border bg-background px-2 py-1.5 text-sm font-normal"
          >
            <option value="" disabled>
              {patients.length === 0 ? "No patients yet" : "Choose a patient"}
            </option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium">
          Date
          <input
            required
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-md border bg-background px-2 py-1.5 text-sm font-normal"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium">
          Start time (clinic time)
          <input
            required
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="rounded-md border bg-background px-2 py-1.5 text-sm font-normal"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium">
          Length (minutes)
          <input
            type="number"
            min={5}
            max={480}
            placeholder={String(defaultMinutes)}
            value={minutes}
            onChange={(e) => setMinutes(e.target.value === "" ? "" : Number(e.target.value))}
            className="rounded-md border bg-background px-2 py-1.5 text-sm font-normal"
          />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-xs font-medium">
        Reason for visit (for staff only)
        <input
          required
          maxLength={200}
          placeholder="e.g. Follow-up on blood test results"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="rounded-md border bg-background px-2 py-1.5 text-sm font-normal"
        />
      </label>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={saving}>
          {saving ? "Adding…" : "Add appointment"}
        </Button>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
