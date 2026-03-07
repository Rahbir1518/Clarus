export function FeaturesSection() {
  return (
    <section className="py-20 md:py-28">
      <div className="mx-auto max-w-7xl space-y-6 px-6">
        {/* Card 1: Smart Triggers — text left, visual right */}
        <div className="grid overflow-hidden rounded-2xl border border-border md:grid-cols-2">
          <div className="flex flex-col justify-center p-10 md:p-14">
            <h3 className="font-serif text-3xl tracking-tight md:text-4xl">
              Smart Triggers
            </h3>
            <p className="mt-4 max-w-md text-base leading-relaxed text-muted-foreground">
              Configure event-driven automations tied to lab reports. Set
              conditions — all results, abnormal only, or custom filters —
              scoped per doctor or clinic-wide.
            </p>
          </div>
          <div className="flex items-center justify-center bg-[#F8F6F4] p-10 md:p-14">
            {/* Abstract trigger config visual */}
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

        {/* Card 2: Automated Calls — visual left, text right */}
        <div className="grid overflow-hidden rounded-2xl border border-border md:grid-cols-2">
          <div className="flex items-center justify-center bg-[#F8F6F4] p-10 md:p-14">
            {/* Abstract waveform / call log visual */}
            <div className="w-full max-w-xs">
              <div className="flex items-end gap-[3px]">
                {[20, 35, 15, 45, 30, 55, 25, 50, 18, 40, 28, 48, 22, 38, 32, 52, 20, 42, 26, 36].map(
                  (h, i) => (
                    <div
                      key={i}
                      className="w-2 rounded-sm bg-foreground/10 transition-colors"
                      style={{ height: `${h}px` }}
                    />
                  )
                )}
              </div>
              <div className="mt-3 flex items-end gap-[3px]">
                {[10, 18, 8, 22, 14, 26, 12, 24, 9, 20, 13, 23, 11, 19, 16, 25, 10, 21, 13, 18].map(
                  (h, i) => (
                    <div
                      key={i}
                      className="w-2 rounded-sm bg-foreground/6"
                      style={{ height: `${h}px` }}
                    />
                  )
                )}
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
              Automated Calls
            </h3>
            <p className="mt-4 max-w-md text-base leading-relaxed text-muted-foreground">
              Outbound voice calls with TTS scripts personalized to each doctor.
              Patients understand what&apos;s needed and can act on the spot.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-muted-foreground">
              <li className="flex items-start gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                Personalized scripts per doctor and clinic
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                Configurable retry logic with 30-min intervals
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                Press 1 to book, press 2 for options, press 9 to opt out
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
