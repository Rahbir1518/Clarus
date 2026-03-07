"use client";

import { Sphere3D } from "./sphere";

export function Hero() {
  return (
    <section className="relative min-h-screen overflow-hidden">
      {/* 3D Sphere */}
      <Sphere3D />

      <div className="relative mx-auto flex min-h-screen max-w-7xl flex-col justify-end px-6 pb-24 pt-32">
        {/* Headline */}
        <h1 className="max-w-4xl font-serif text-6xl leading-[1.05] tracking-tight md:text-8xl lg:text-[7rem]">
          Automate patient
          <br />
          follow-up{" "}
          <span className="text-primary/40">before</span>
          <br />
          <span className="text-primary/40">the first missed call.</span>
        </h1>

        {/* Separator */}
        <div className="mt-12 h-px w-full max-w-lg bg-border" />

        {/* Subtext */}
        <div className="mt-8">
          <p className="max-w-sm text-base leading-relaxed text-muted-foreground">
            We automate the workflow between lab results and patient action so
            your clinic never misses a follow-up.
          </p>
        </div>
      </div>
    </section>
  );
}
