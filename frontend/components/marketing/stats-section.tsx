const supportingStats = [
  {
    value: "30%",
    label: "Fewer no-shows",
  },
  {
    value: "40%",
    label: "Less admin workload",
  },
  {
    value: "99.9%",
    label: "Uptime during clinic hours",
  },
];

export function StatsSection() {
  return (
    <section className="py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid items-center gap-12 md:grid-cols-2">
          {/* Hero stat */}
          <div>
            <p className="font-mono text-7xl font-bold tracking-tighter text-primary md:text-8xl">
              &lt; 5 min
            </p>
            <h2 className="mt-4 font-serif text-3xl tracking-tight md:text-4xl">
              From trigger fired to patient contacted
            </h2>
            <p className="mt-3 max-w-md text-muted-foreground">
              The industry average is 2–4 hours. Most clinics using Clarus see
              first contact in under two minutes.
            </p>
          </div>

          {/* Supporting stats */}
          <div className="space-y-5">
            {supportingStats.map((stat) => (
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
  );
}
