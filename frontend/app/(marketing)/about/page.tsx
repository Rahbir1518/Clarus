import { ArrowRight } from "lucide-react";
import Link from "next/link";

const team = [
  {
    name: "Dr. Priya Nair",
    role: "General Practitioner",
    quote:
      "We used to spend two hours a day calling patients about lab results. With Clarus, those calls happen automatically.",
  },
  {
    name: "Sarah M.",
    role: "Clinic Administrator",
    quote:
      "Managing scheduling for three physicians meant constant phone calls. Clarus gave us our day back.",
  },
  {
    name: "James T.",
    role: "Patient",
    quote:
      "I used to find out about my test results days later. Now I get a call within minutes and can book right away.",
  },
];

const milestones = [
  { phase: "Discovery", detail: "PRD approved, architecture finalized" },
  { phase: "Core Engine", detail: "Trigger engine and event bus operational" },
  { phase: "Call Integration", detail: "Outbound call and IVR flow functional" },
  { phase: "Booking Integration", detail: "Calendar read/write with confirmation" },
  { phase: "Admin UI", detail: "Trigger configuration and audit log complete" },
  { phase: "QA & Testing", detail: "UAT, load testing" },
  { phase: "Beta Launch", detail: "Pilot with initial clinic partners" },
  { phase: "General Availability", detail: "Full public launch" },
];

export default function AboutPage() {
  return (
    <>
      {/* Hero */}
      <section className="py-28 md:py-40">
        <div className="mx-auto max-w-7xl px-6">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            About Clarus
          </p>
          <h1 className="mt-6 max-w-4xl font-serif text-5xl leading-tight tracking-tight md:text-7xl">
            We believe no patient should wait for a follow-up that{" "}
            <span className="text-sage-400">never comes.</span>
          </h1>
          <div className="mt-10 h-px w-full max-w-md bg-border" />
          <p className="mt-8 max-w-lg text-base leading-relaxed text-muted-foreground">
            Clarus is an intelligent clinical workflow automation platform that
            enables healthcare providers to configure event-driven triggers tied
            to patient records and medical data. When a predefined condition is
            met — such as a lab report being received — the system automatically
            initiates a downstream action, like placing an automated phone call
            to the patient.
          </p>
        </div>
      </section>

      {/* The Problem */}
      <section className="bg-sage-50 py-28 md:py-36">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid gap-12 md:grid-cols-[160px_1fr_1fr] md:gap-8">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
              The Problem
            </p>
            <div>
              <h2 className="font-serif text-4xl leading-tight tracking-tight md:text-5xl">
                Manual follow-ups are{" "}
              <span className="text-primary">slow</span>, inconsistent, and costly.
              </h2>
              <p className="mt-6 max-w-lg text-base leading-relaxed text-muted-foreground">
                Today, when a blood report arrives at a clinic, the follow-up
                workflow relies entirely on manual effort. Staff review incoming
                results, identify which patients need follow-ups, and call each
                patient individually — often during the busiest clinic hours.
              </p>
            </div>
            <div className="space-y-0">
              {[
                "Staff must manually review every incoming result",
                "Patients are identified one by one for follow-up",
                "Calls happen during peak hours, causing delays",
                "Missed follow-ups lead to no-shows and worse outcomes",
              ].map((item) => (
                <div
                  key={item}
                  className="flex items-center gap-3 border-b border-foreground/10 py-5 text-sm text-foreground"
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary/40" />
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* The Opportunity */}
      <section className="py-24 md:py-32">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid items-center gap-12 md:grid-cols-2">
            <div>
              <p className="font-mono text-7xl font-bold tracking-tighter text-primary md:text-8xl">
                &lt; 60s
              </p>
              <h2 className="mt-4 font-serif text-3xl tracking-tight md:text-4xl">
                From report received to patient contacted
              </h2>
              <p className="mt-3 max-w-md text-muted-foreground">
                Automate the notification-and-booking workflow so that the moment
                a qualifying report arrives, the patient is contacted — no manual
                intervention required.
              </p>
            </div>
            <div className="space-y-5">
              {[
                {
                  value: "2–4 hrs",
                  label: "Current industry average response time",
                },
                {
                  value: "30%",
                  label: "Target reduction in missed follow-ups",
                },
                {
                  value: "40%",
                  label: "Target reduction in admin scheduling calls",
                },
                {
                  value: "80%",
                  label: "Physician adoption goal within 30 days",
                },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="flex items-baseline justify-between border-b border-border pb-5 last:border-0"
                >
                  <p className="text-sm text-muted-foreground">{stat.label}</p>
                  <p className="font-mono text-3xl font-bold tracking-tight text-foreground md:text-4xl">
                    {stat.value}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Personas */}
      <section className="border-y border-border bg-white py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Who We Serve
          </p>
          <h2 className="mt-6 font-serif text-4xl tracking-tight md:text-5xl">
            Built for <span className="text-sage-400">every role</span> in the clinic.
          </h2>
          <div className="mt-14 grid gap-6 md:grid-cols-3">
            {team.map((person) => (
              <div
                key={person.name}
                className="rounded-2xl border border-border p-8"
              >
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-gradient-to-br from-sage/40 to-sage-100" />
                  <div>
                    <p className="text-sm font-semibold">{person.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {person.role}
                    </p>
                  </div>
                </div>
                <p className="mt-5 text-sm leading-relaxed text-muted-foreground">
                  &ldquo;{person.quote}&rdquo;
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Roadmap */}
      <section className="py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Our Roadmap
          </p>
          <h2 className="mt-6 font-serif text-4xl tracking-tight md:text-5xl">
            From idea to general availability.
          </h2>
          <div className="mt-14 space-y-0">
            {milestones.map((m, i) => (
              <div
                key={m.phase}
                className="flex items-baseline justify-between border-b border-border py-5"
              >
                <div className="flex items-baseline gap-4">
                  <span className="font-mono text-xs text-muted-foreground/50">
                    {String(i).padStart(2, "0")}
                  </span>
                  <p className="text-sm font-medium text-foreground">
                    {m.phase}
                  </p>
                </div>
                <p className="text-sm text-muted-foreground">{m.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-28 md:py-40">
        <div className="mx-auto max-w-7xl px-6">
          <h2 className="max-w-3xl font-serif text-5xl leading-tight tracking-tight md:text-7xl">
            Ready to <span className="text-sage-400">automate</span> your clinic?
          </h2>
          <div className="mt-10 h-px w-full max-w-md bg-border" />
          <div className="mt-8 flex gap-6">
            <Link
              href="/contact"
              className="group inline-flex items-center gap-2 text-sm font-medium text-foreground transition-colors hover:text-primary"
            >
              Get in touch
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
