export function SocialProof() {
  return (
    <section className="border-y border-border bg-white py-14">
      <div className="mx-auto max-w-3xl px-6 text-center">
        <blockquote>
          <p className="font-serif text-xl leading-relaxed tracking-tight text-foreground md:text-2xl">
            &ldquo;We used to spend two hours a day calling patients about lab
            results. With Clarus, those calls happen automatically — and our
            no-show rate dropped by a third in the first month.&rdquo;
          </p>
        </blockquote>
        <div className="mt-6 flex items-center justify-center gap-3">
          <div className="h-10 w-10 rounded-full bg-gradient-to-br from-primary/20 to-primary/5" />
          <div className="text-left">
            <p className="text-sm font-semibold">Dr. Priya Nair</p>
            <p className="text-xs text-muted-foreground">
              General Practitioner, Lakeview Family Clinic
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
