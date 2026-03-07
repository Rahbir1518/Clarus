export function FeaturesSection() {
  return (
    <section className="py-20 md:py-28">
      <div className="mx-auto max-w-7xl space-y-6 px-6">
        {/* Card 1: Smart Triggers — text left, visual right */}
        <div className="mx-auto max-w-5xl grid overflow-hidden rounded-2xl border border-border md:grid-cols-2">
          <div className="flex flex-col justify-center p-8 md:p-10">
            <h3 className="font-serif text-3xl tracking-tight md:text-4xl">
              Smart Triggers
            </h3>
            <p className="mt-4 max-w-md text-base leading-relaxed text-muted-foreground">
              Configure event-driven automations tied to lab reports. Set
              conditions — all results, abnormal only, or custom filters —
              scoped per doctor or clinic-wide.
            </p>
          </div>
          <div className="flex items-center justify-end">
            <div className="w-[70%] overflow-hidden rounded-lg border border-border">
              <video
                className="w-[calc(100%+59px)] max-w-none -ml-[24px] -mt-[5px] -mb-[10px]"
                autoPlay
                loop
                muted
                playsInline
              >
                <source src="/assets/workflow_demo.mp4" type="video/mp4" />
              </video>
            </div>
          </div>
        </div>

        {/* Card 2: Automated Calls — visual left, text right */}
        <div className="mx-auto max-w-5xl grid overflow-hidden rounded-2xl border border-border md:grid-cols-2">
          <div className="flex items-center justify-start p-8 md:p-10">
            {/* Abstract waveform / call log visual */}
            <div className="w-full max-w-xs">
              <div className="flex items-end gap-[3px]">
                {[20, 35, 15, 45, 30, 55, 25, 50, 18, 40, 28, 48, 22, 38, 32, 52, 20, 42, 26, 36].map(
                  (h, i) => (
                    <div
                      key={i}
                      className="w-2 rounded-sm bg-sage transition-colors"
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
                      className="w-2 rounded-sm bg-sage-200"
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
          <div className="flex flex-col justify-center p-8 md:p-10">
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
