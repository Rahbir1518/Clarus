import Link from "next/link";
import { ArrowRight } from "lucide-react";

const links = [
  { label: "How triggers work", href: "/features" },
  { label: "Call automation", href: "/features" },
  { label: "Booking integration", href: "/features" },
];

export function HowItWorks() {
  return (
    <section className="bg-sage-50 py-28 md:py-36">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid gap-12 md:grid-cols-[160px_1fr_1fr] md:gap-8">
          {/* Label */}
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Our Approach
          </p>

          {/* Main content */}
          <div>
            <h2 className="font-serif text-4xl leading-tight tracking-tight md:text-5xl">
              We automate the workflow between lab results and patient action.
            </h2>
            <p className="mt-6 max-w-lg text-base leading-relaxed text-muted-foreground">
              When a blood report arrives, Clarus fires a trigger, calls the
              patient with a personalized script, and books a follow-up — all
              within 60 seconds, without your staff doing a thing.
            </p>
          </div>

          {/* Links */}
          <div className="space-y-0">
            {links.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="group flex items-center justify-between border-b border-foreground/10 py-5 text-sm font-medium text-foreground transition-colors hover:text-primary"
              >
                {link.label}
                <ArrowRight className="h-4 w-4 opacity-0 transition-all group-hover:opacity-100 group-hover:translate-x-1" />
              </Link>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
