"use client";

import { useState, useEffect, useCallback } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  FileText,
  Phone,
  Clock,
  CalendarCheck,
  ShieldCheck,
  ChevronRight,
  Users,
  TrendingDown,
  Zap,
  Activity,
  ArrowRight,
  AlertTriangle,
  Stethoscope,
  Bot,
  DollarSign,
} from "lucide-react";

const TOTAL_SLIDES = 5;

export default function PitchDeck() {
  const [current, setCurrent] = useState(0);
  const [direction, setDirection] = useState<"next" | "prev">("next");

  const goTo = useCallback(
    (n: number) => {
      if (n < 0 || n >= TOTAL_SLIDES || n === current) return;
      setDirection(n > current ? "next" : "prev");
      setCurrent(n);
    },
    [current],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === " ") {
        e.preventDefault();
        goTo(current + 1);
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        goTo(current - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, goTo]);

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-background">
      {/* Slide indicator dots */}
      <div className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 gap-2">
        {Array.from({ length: TOTAL_SLIDES }).map((_, i) => (
          <button
            key={i}
            onClick={() => goTo(i)}
            className={`h-2 rounded-full transition-all duration-300 ${
              i === current
                ? "w-8 bg-primary"
                : "w-2 bg-sage-400 hover:bg-sage-600"
            }`}
          />
        ))}
      </div>

      {/* Slide number */}
      <div className="fixed bottom-6 right-8 z-50 font-mono text-sm text-sage-400">
        {current + 1} / {TOTAL_SLIDES}
      </div>

      {/* ── Slide 1: Title ── */}
      <Slide index={0} current={current} direction={direction}>
        <div className="bg-grid flex h-full flex-col items-center justify-center px-8 text-center">
          <div className="mb-8 flex items-center gap-4">
            <Image
              src="/assets/Clarus.png"
              alt="Clarus"
              width={80}
              height={80}
              className="h-20 w-20"
            />
            <span className="font-serif text-8xl font-bold tracking-tight text-foreground">
              Clarus
            </span>
          </div>

          <div className="mb-8 h-1 w-32 rounded-full bg-primary" />

          <p className="mb-12 max-w-3xl font-serif text-3xl leading-relaxed tracking-tight text-muted-foreground">
            Automate patient follow-up before the first missed call.
          </p>

          <div className="rounded-2xl border border-primary/20 bg-primary/5 px-10 py-8 shadow-sm backdrop-blur-sm">
            <p className="text-lg text-muted-foreground">
              The average Canadian waits{" "}
              <span className="font-bold text-primary">2–4 hours</span> for a
              follow-up call after lab results.
            </p>
            <p className="mt-2 text-lg text-muted-foreground">
              With Clarus, it takes{" "}
              <span className="font-bold text-primary">
                less than 60 seconds
              </span>
              .
            </p>
          </div>

          <p className="mt-10 rounded-full border border-border bg-card/80 px-6 py-2 text-sm uppercase tracking-[0.2em] text-sage-500">
            Hack Canada 2026
          </p>
        </div>
      </Slide>

      {/* ── Slide 2: The Problem ── */}
      <Slide index={1} current={current} direction={direction}>
        <div className="flex h-full">
          {/* Left: content (~60%) */}
          <div className="flex w-[60%] flex-col justify-center px-16 py-12">
            <p className="mb-2 text-sm font-bold uppercase tracking-[0.25em] text-primary">
              The Problem
            </p>
            <h2 className="mb-2 font-serif text-7xl font-bold leading-[1.1] tracking-tight text-foreground">
              Clinics are drowning in manual follow-ups
            </h2>
            <div className="mb-10 h-1 w-24 rounded-full bg-primary" />

            <ul className="mb-12 space-y-5">
              <BulletPoint icon={<FileText className="h-5 w-5" />}>
                Staff manually review every lab result
              </BulletPoint>
              <BulletPoint icon={<Phone className="h-5 w-5" />}>
                Patients called one-by-one during peak hours
              </BulletPoint>
              <BulletPoint icon={<AlertTriangle className="h-5 w-5" />}>
                Missed follow-ups → worse outcomes &amp; longer wait times
              </BulletPoint>
              <BulletPoint icon={<Stethoscope className="h-5 w-5" />}>
                Physician shortages make admin time critical
              </BulletPoint>
            </ul>

            {/* Manual process flow */}
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card/60 px-6 py-4">
              <FlowStep label="Lab result" />
              <ChevronRight className="h-4 w-4 text-sage-400" />
              <FlowStep label="Staff reviews" />
              <ChevronRight className="h-4 w-4 text-sage-400" />
              <FlowStep label="Manual call" />
              <ChevronRight className="h-4 w-4 text-sage-400" />
              <FlowStep label="Hope they answer" />
              <ChevronRight className="h-4 w-4 text-sage-400" />
              <FlowStep label="Try to book" />
              <span className="ml-2 flex items-center gap-1.5 text-sm font-semibold text-primary">
                <Clock className="h-4 w-4" />
                2–4 hours
              </span>
            </div>
          </div>

          {/* Right: image (~40%) */}
          <div className="relative flex w-[40%] items-center justify-center p-8">
            <div className="relative h-[80%] w-full overflow-hidden rounded-2xl shadow-2xl">
              <img
                src="https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?w=800&q=80"
                alt="Hospital hallway"
                className="h-full w-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-l from-transparent to-background/20" />
            </div>
          </div>
        </div>
      </Slide>

      {/* ── Slide 3: The Solution ── */}
      <Slide index={2} current={current} direction={direction}>
        <div className="flex h-full">
          {/* Left: content (~60%) */}
          <div className="flex w-[60%] flex-col justify-center px-16 py-12">
            <p className="mb-2 text-sm font-bold uppercase tracking-[0.25em] text-primary">
              The Solution
            </p>
            <h2 className="mb-2 font-serif text-7xl font-bold leading-[1.1] tracking-tight text-foreground">
              Lab in. Patient called. Booked.
            </h2>
            <div className="mb-10 h-1 w-24 rounded-full bg-primary" />

            <ul className="mb-12 space-y-5">
              <BulletPoint icon={<Phone className="h-5 w-5" />}>
                Automated voice calls to patients within seconds
              </BulletPoint>
              <BulletPoint icon={<CalendarCheck className="h-5 w-5" />}>
                Real-time appointment booking on the call
              </BulletPoint>
              <BulletPoint icon={<Bot className="h-5 w-5" />}>
                Configurable triggers per doctor or clinic-wide
              </BulletPoint>
              <BulletPoint icon={<ShieldCheck className="h-5 w-5" />}>
                Full audit trail for every automated action
              </BulletPoint>
            </ul>

            {/* Automated pipeline */}
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 px-6 py-4">
              <PipelineStep
                icon={<FileText className="h-4 w-4" />}
                label="Lab report"
              />
              <ArrowRight className="h-4 w-4 text-primary" />
              <PipelineStep
                icon={<Zap className="h-4 w-4" />}
                label="Trigger fires"
              />
              <ArrowRight className="h-4 w-4 text-primary" />
              <PipelineStep
                icon={<Phone className="h-4 w-4" />}
                label="Patient called"
              />
              <ArrowRight className="h-4 w-4 text-primary" />
              <PipelineStep
                icon={<CalendarCheck className="h-4 w-4" />}
                label="Booked"
              />
              <ArrowRight className="h-4 w-4 text-primary" />
              <PipelineStep
                icon={<ShieldCheck className="h-4 w-4" />}
                label="Logged"
              />
              <span className="ml-2 flex items-center gap-1.5 text-sm font-bold text-primary">
                <Zap className="h-4 w-4" />
                &lt; 60s
              </span>
            </div>
          </div>

          {/* Right: image (~40%) */}
          <div className="relative flex w-[40%] items-center justify-center p-8">
            <div className="relative h-[80%] w-full overflow-hidden rounded-2xl shadow-2xl">
              <img
                src="https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=800&q=80"
                alt="Technology automation"
                className="h-full w-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-l from-transparent to-background/20" />
            </div>
          </div>
        </div>
      </Slide>

      {/* ── Slide 4: Impact ── */}
      <Slide index={3} current={current} direction={direction}>
        <div className="flex h-full flex-col items-center justify-center px-16">
          <p className="mb-2 text-sm font-bold uppercase tracking-[0.25em] text-primary">
            Impact
          </p>
          <h2 className="mb-2 text-center font-serif text-7xl font-bold tracking-tight text-foreground">
            Real results for real clinics
          </h2>
          <div className="mb-14 h-1 w-24 rounded-full bg-primary" />

          {/* Stat cards */}
          <div className="mb-12 grid grid-cols-4 gap-6">
            <StatCard
              value="< 60s"
              label="From report to patient contact"
              icon={<Clock className="h-6 w-6" />}
            />
            <StatCard
              value="30%"
              label="Fewer missed follow-ups"
              icon={<TrendingDown className="h-6 w-6" />}
            />
            <StatCard
              value="40%"
              label="Less admin workload"
              icon={<Users className="h-6 w-6" />}
            />
            <StatCard
              value="99.9%"
              label="Uptime during clinic hours"
              icon={<Activity className="h-6 w-6" />}
            />
          </div>

          {/* Bullet points */}
          <ul className="mb-10 space-y-4">
            <BulletPoint icon={<Zap className="h-5 w-5" />}>
              Reduces response time from hours to seconds
            </BulletPoint>
            <BulletPoint icon={<Users className="h-5 w-5" />}>
              Frees up 40% of admin staff time
            </BulletPoint>
            <BulletPoint icon={<DollarSign className="h-5 w-5" />}>
              Starts at $49/mo — no long contracts
            </BulletPoint>
          </ul>

        </div>
      </Slide>

      {/* ── Slide 5: Live Demo ── */}
      <Slide index={4} current={current} direction={direction}>
        <div className="bg-grid flex h-full flex-col items-center justify-center px-8 text-center">
          <Image
            src="/assets/Clarus.png"
            alt="Clarus"
            width={96}
            height={96}
            className="mb-10 h-24 w-24"
          />
          <h2 className="mb-4 font-serif text-7xl font-bold tracking-tight text-foreground">
            Let us show you.
          </h2>
          <div className="mb-10 h-1 w-24 rounded-full bg-primary" />
          <p className="mb-12 max-w-xl text-xl text-muted-foreground">
            Watch Clarus handle a patient follow-up from start to finish — fully
            automated.
          </p>

          <Link
            href="/"
            className="group inline-flex items-center gap-3 rounded-2xl bg-primary px-10 py-5 text-lg font-semibold text-primary-foreground shadow-lg transition-all duration-200 hover:scale-105 hover:shadow-xl"
          >
            Launch Live Demo
            <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-1" />
          </Link>

          <p className="mt-10 text-sm uppercase tracking-[0.2em] text-sage-500">
            Hack Canada 2026
          </p>
        </div>
      </Slide>
    </div>
  );
}

/* ── Sub-components ── */

function Slide({
  index,
  current,
  direction,
  children,
}: {
  index: number;
  current: number;
  direction: "next" | "prev";
  children: React.ReactNode;
}) {
  const isActive = index === current;
  const isPast = index < current;

  let translate = "translate-x-full";
  if (isActive) translate = "translate-x-0";
  else if (isPast) translate = "-translate-x-full";

  if (!isActive) {
    if (direction === "prev") {
      translate = isPast ? "-translate-x-full" : "translate-x-full";
    }
  }

  return (
    <div
      className={`absolute inset-0 transition-all duration-500 ease-in-out ${translate} ${
        isActive ? "opacity-100" : "opacity-0"
      }`}
    >
      {children}
    </div>
  );
}

function BulletPoint({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <li className="flex items-start gap-4">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        {icon}
      </span>
      <span className="text-lg leading-relaxed text-foreground">{children}</span>
    </li>
  );
}

function FlowStep({ label }: { label: string }) {
  return (
    <span className="rounded-lg bg-sage-100 px-3 py-1.5 text-sm font-medium text-foreground">
      {label}
    </span>
  );
}

function PipelineStep({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg bg-primary/10 px-3 py-1.5 text-sm font-medium text-primary">
      {icon}
      {label}
    </span>
  );
}

function StatCard({
  value,
  label,
  icon,
}: {
  value: string;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-border bg-card/80 p-8 text-center shadow-sm">
      <div className="mb-4 text-primary">{icon}</div>
      <p className="mb-2 font-serif text-4xl font-bold tracking-tight text-foreground">
        {value}
      </p>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}
