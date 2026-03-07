import Link from "next/link";
import { ArrowRight } from "lucide-react";

const userStories = [
  {
    id: "US-01",
    persona: "Doctor",
    story:
      "Create a trigger that fires when a blood report is received, so the patient is automatically contacted.",
  },
  {
    id: "US-02",
    persona: "Doctor",
    story:
      "Configure which report types activate the trigger — all results, abnormal only, or custom filters.",
  },
  {
    id: "US-03",
    persona: "Admin",
    story:
      "View a log of all automated calls made, so I can track outreach and follow up manually if needed.",
  },
  {
    id: "US-04",
    persona: "Admin",
    story:
      "Pause or deactivate a trigger at any time to manage the system during unusual circumstances.",
  },
  {
    id: "US-05",
    persona: "Patient",
    story:
      "Receive a call explaining that my blood report is ready and that my doctor recommends a follow-up.",
  },
  {
    id: "US-06",
    persona: "Patient",
    story:
      "Book an appointment directly on the call, so I don't need to call back separately.",
  },
];

const integrations = [
  {
    system: "EMR / Lab System",
    type: "Webhook or HL7 FHIR",
    detail: "Trigger on DiagnosticReport resource creation",
  },
  {
    system: "Telephony Provider",
    type: "REST API (Twilio)",
    detail: "Outbound call and IVR DTMF handling",
  },
  {
    system: "Clinic Calendar",
    type: "REST API",
    detail: "Read available slots, write confirmed bookings",
  },
  {
    system: "Notification Service",
    type: "Internal",
    detail: "Flag unreachable patients to staff dashboard",
  },
];

export default function FeaturesPage() {
  return (
    <>
      {/* Hero */}
      <section className="py-28 md:py-40">
        <div className="mx-auto max-w-7xl px-6">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Product
          </p>
          <h1 className="mt-6 max-w-4xl font-serif text-5xl leading-tight tracking-tight md:text-7xl">
            Everything you need to{" "}
            <span className="text-sage-400">automate</span> clinical follow-ups.
          </h1>
          <div className="mt-10 h-px w-full max-w-md bg-border" />
          <p className="mt-8 max-w-lg text-base leading-relaxed text-muted-foreground">
            Blood report received. Patient called. Appointment booked. All
            within 60 seconds — without your staff doing a thing.
          </p>
        </div>
      </section>

      {/* Core Feature: Trigger Configuration */}
      <section className="py-20 md:py-28">
        <div className="mx-auto max-w-7xl space-y-6 px-6">
          <div className="grid overflow-hidden rounded-2xl border border-border md:grid-cols-2">
            <div className="flex flex-col justify-center p-10 md:p-14">
              <h3 className="font-serif text-3xl tracking-tight md:text-4xl">
                Trigger <span className="text-primary">Configuration</span>
              </h3>
              <p className="mt-4 max-w-md text-base leading-relaxed text-muted-foreground">
                Create, edit, enable, disable, and delete triggers through an
                intuitive web interface. Each trigger includes a name, event
                type, optional filter conditions, and a linked action.
              </p>
              <ul className="mt-6 space-y-3 text-sm text-muted-foreground">
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Support for blood/lab report received events
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Optional filter: fire only on abnormal or flagged results
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Scoped per doctor&apos;s patient list or clinic-wide
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Per-patient or all-patients activation
                </li>
              </ul>
            </div>
            <div className="flex items-center justify-center bg-sage-50 p-10 md:p-14">
              <div className="w-full max-w-xs space-y-3">
                <div className="flex items-center gap-3">
                  <div className="h-3 w-3 rounded-full bg-primary/30" />
                  <div className="h-2.5 w-32 rounded bg-foreground/8" />
                </div>
                <div className="rounded-lg border border-foreground/5 bg-white p-4">
                  <div className="space-y-2.5">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-green-400/60" />
                      <div className="h-2 w-24 rounded bg-foreground/10" />
                    </div>
                    <div className="ml-4 space-y-2 border-l-2 border-primary/15 pl-3">
                      <div className="h-2 w-36 rounded bg-foreground/6" />
                      <div className="h-2 w-28 rounded bg-foreground/6" />
                      <div className="h-2 w-32 rounded bg-foreground/6" />
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <div className="h-2.5 w-16 rounded bg-foreground/6" />
                  <div className="h-2.5 w-20 rounded bg-foreground/6" />
                </div>
              </div>
            </div>
          </div>

          {/* Automated Calls */}
          <div className="grid overflow-hidden rounded-2xl border border-border md:grid-cols-2">
            <div className="flex items-center justify-center bg-sage-50 p-10 md:p-14">
              <div className="w-full max-w-xs">
                <div className="flex items-end gap-[3px]">
                  {[
                    20, 35, 15, 45, 30, 55, 25, 50, 18, 40, 28, 48, 22, 38,
                    32, 52, 20, 42, 26, 36,
                  ].map((h, i) => (
                    <div
                      key={i}
                      className="w-2 rounded-sm bg-foreground/10"
                      style={{ height: `${h}px` }}
                    />
                  ))}
                </div>
                <div className="mt-3 flex items-end gap-[3px]">
                  {[
                    10, 18, 8, 22, 14, 26, 12, 24, 9, 20, 13, 23, 11, 19, 16,
                    25, 10, 21, 13, 18,
                  ].map((h, i) => (
                    <div
                      key={i}
                      className="w-2 rounded-sm bg-foreground/6"
                      style={{ height: `${h}px` }}
                    />
                  ))}
                </div>
                <div className="mt-4 flex gap-6 text-[10px] text-muted-foreground/50">
                  <span>Duration</span>
                  <span>Outcome</span>
                  <span>Retries</span>
                </div>
              </div>
            </div>
            <div className="flex flex-col justify-center p-10 md:p-14">
              <h3 className="font-serif text-3xl tracking-tight md:text-4xl">
                Automated <span className="text-primary">Voice Calls</span>
              </h3>
              <p className="mt-4 max-w-md text-base leading-relaxed text-muted-foreground">
                Outbound voice calls with TTS scripts personalized per doctor.
                Patients hear what&apos;s needed and can act immediately — no
                callbacks required.
              </p>
              <ul className="mt-6 space-y-3 text-sm text-muted-foreground">
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Press 1 to confirm appointment, press 2 for other times
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Configurable retry logic — up to 2 retries at 30-min intervals
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Unreachable patients flagged and staff notified
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Press 9 to opt out of future automated calls
                </li>
              </ul>
            </div>
          </div>

          {/* Appointment Booking */}
          <div className="grid overflow-hidden rounded-2xl border border-border md:grid-cols-2">
            <div className="flex flex-col justify-center p-10 md:p-14">
              <h3 className="font-serif text-3xl tracking-tight md:text-4xl">
                Instant <span className="text-primary">Appointment</span> Booking
              </h3>
              <p className="mt-4 max-w-md text-base leading-relaxed text-muted-foreground">
                Patients book follow-ups directly during the automated call.
                Slots are queried in real time, held during the call, and
                confirmed within seconds.
              </p>
              <ul className="mt-6 space-y-3 text-sm text-muted-foreground">
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Real-time calendar availability lookup
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Slot held for 2 minutes during the call
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Booking reflected in clinic system within 30 seconds
                </li>
              </ul>
            </div>
            <div className="flex items-center justify-center bg-sage-50 p-10 md:p-14">
              <div className="w-full max-w-xs space-y-3">
                {[
                  { time: "9:00 AM", status: "Available" },
                  { time: "10:30 AM", status: "Available" },
                  { time: "2:15 PM", status: "Available" },
                ].map((slot) => (
                  <div
                    key={slot.time}
                    className="flex items-center justify-between rounded-lg border border-foreground/5 bg-white px-4 py-3"
                  >
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-green-400/60" />
                      <span className="text-xs font-medium text-foreground/70">
                        {slot.time}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground/50">
                      {slot.status}
                    </span>
                  </div>
                ))}
                <div className="h-2.5 w-24 rounded bg-foreground/6" />
              </div>
            </div>
          </div>

          {/* Audit Log */}
          <div className="grid overflow-hidden rounded-2xl border border-border md:grid-cols-2">
            <div className="flex items-center justify-center bg-sage-50 p-10 md:p-14">
              <div className="w-full max-w-xs space-y-2">
                {[1, 2, 3, 4, 5].map((row) => (
                  <div key={row} className="flex items-center gap-3">
                    <div className="h-2 w-16 rounded bg-foreground/8" />
                    <div className="h-2 w-20 rounded bg-foreground/5" />
                    <div className="h-2 w-12 rounded bg-foreground/5" />
                    <div className="ml-auto h-2 w-8 rounded bg-green-400/30" />
                  </div>
                ))}
                <div className="mt-3 flex gap-4 text-[10px] text-muted-foreground/50">
                  <span>Timestamp</span>
                  <span>Patient</span>
                  <span>Trigger</span>
                  <span className="ml-auto">Status</span>
                </div>
              </div>
            </div>
            <div className="flex flex-col justify-center p-10 md:p-14">
              <h3 className="font-serif text-3xl tracking-tight md:text-4xl">
                Audit Log & Reporting
              </h3>
              <p className="mt-4 max-w-md text-base leading-relaxed text-muted-foreground">
                Every trigger event is logged — timestamp, patient, trigger
                name, action taken, and call outcome. Filter by date, doctor,
                patient, or result. Export to CSV anytime.
              </p>
              <ul className="mt-6 space-y-3 text-sm text-muted-foreground">
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  Full event history with filtering
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  CSV export for compliance reviews
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                  All data access logged for audit trails
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* User Stories */}
      <section className="bg-sage-50 py-28 md:py-36">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid gap-12 md:grid-cols-[160px_1fr] md:gap-8">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
              User Stories
            </p>
            <div className="space-y-0">
              {userStories.map((us) => (
                <div
                  key={us.id}
                  className="flex items-start gap-4 border-b border-foreground/10 py-5"
                >
                  <span className="shrink-0 font-mono text-xs text-muted-foreground/50">
                    {us.id}
                  </span>
                  <div>
                    <span className="mr-2 inline-block rounded-full bg-foreground/5 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                      {us.persona}
                    </span>
                    <p className="mt-1 text-sm text-foreground">{us.story}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Integrations */}
      <section className="py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Integrations
          </p>
          <h2 className="mt-6 font-serif text-4xl tracking-tight md:text-5xl">
            Connects to your <span className="text-sage-400">existing stack.</span>
          </h2>
          <div className="mt-14 grid gap-6 md:grid-cols-2">
            {integrations.map((int) => (
              <div
                key={int.system}
                className="rounded-2xl border border-border p-8"
              >
                <p className="text-sm font-medium text-foreground">
                  {int.system}
                </p>
                <p className="mt-1 text-xs text-muted-foreground/60">
                  {int.type}
                </p>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {int.detail}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Compliance bar */}
      <section className="border-y border-border py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
            <p className="text-sm text-muted-foreground">
              HIPAA &amp; PIPEDA compliant &nbsp;&middot;&nbsp; TLS 1.2+ in
              transit &nbsp;&middot;&nbsp; AES-256 at rest &nbsp;&middot;&nbsp;
              SOC 2 in progress
            </p>
            <p className="text-xs text-muted-foreground/60">
              All patient data encrypted. All access logged for compliance
              review.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-28 md:py-40">
        <div className="mx-auto max-w-7xl px-6">
          <h2 className="max-w-3xl font-serif text-5xl leading-tight tracking-tight md:text-7xl">
            See it <span className="text-sage-400">in action.</span>
          </h2>
          <div className="mt-10 h-px w-full max-w-md bg-border" />
          <div className="mt-8 flex gap-6">
            <Link
              href="/contact"
              className="group inline-flex items-center gap-2 text-sm font-medium text-foreground transition-colors hover:text-primary"
            >
              Request a demo
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <Link
              href="/pricing"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              View pricing
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
