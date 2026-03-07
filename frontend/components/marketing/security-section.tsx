export function SecuritySection() {
  return (
    <section className="border-y border-border py-12">
      <div className="mx-auto max-w-7xl px-6">
        <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
          <p className="text-sm text-muted-foreground">
            HIPAA &amp; PIPEDA compliant &nbsp;·&nbsp; TLS 1.2+ in transit
            &nbsp;·&nbsp; AES-256 at rest &nbsp;·&nbsp; SOC 2 in progress
          </p>
          <p className="text-xs text-muted-foreground/60">
            All patient data encrypted. All access logged for compliance review.
          </p>
        </div>
      </div>
    </section>
  );
}
