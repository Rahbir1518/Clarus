"use client";

import { Suspense, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth0 } from "@auth0/auth0-react";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

/* ── Stripe Checkout placeholder URLs ───────────────────────────────────
   Replace these with real Stripe Payment Links once your Stripe account
   is set up (e.g. https://buy.stripe.com/live_xxx).                     */
const checkoutUrls: Record<string, string> = {
  starter: "https://buy.stripe.com/test_bJe14g4ga86rb7r1nW4ZG00",
  pro: "https://buy.stripe.com/test_bJeaEQeUO5Yj0sN6Ig4ZG01",
  clinic: "https://buy.stripe.com/test_6oUbIU9Au86r0sN5Ec4ZG02",
};

const tiers = [
  {
    key: "starter",
    name: "Starter",
    price: "$49",
    period: "/mo",
    description: "For small clinics getting started with automation.",
    includes: "50 calls included",
    overage: "$0.75 per additional call",
    features: [
      "1 physician account",
      "Trigger configuration UI",
      "Automated voice calls",
      "Basic audit log",
      "Email support",
    ],
    cta: "Get started",
    highlight: false,
  },
  {
    key: "pro",
    name: "Pro",
    price: "$149",
    period: "/mo",
    description: "For growing practices that need more volume.",
    includes: "200 calls included",
    overage: "$0.60 per additional call",
    features: [
      "Up to 5 physician accounts",
      "Advanced trigger filters",
      "Appointment booking integration",
      "Full audit log with CSV export",
      "Priority support",
      "Custom call scripts",
    ],
    cta: "Get started",
    highlight: true,
  },
  {
    key: "clinic",
    name: "Clinic",
    price: "$399",
    period: "/mo",
    description: "For multi-physician clinics with high patient volume.",
    includes: "600 calls included",
    overage: "$0.50 per additional call",
    features: [
      "Up to 15 physician accounts",
      "All Pro features",
      "Clinic-wide trigger management",
      "Patient preference management",
      "Dedicated onboarding",
      "Phone & email support",
    ],
    cta: "Get started",
    highlight: false,
  },
];

const faqs = [
  {
    q: "What counts as a call?",
    a: "Each outbound call attempt counts as one call, including retries. If a patient is unreachable after all retry attempts, each attempt is counted individually.",
  },
  {
    q: "Can I change plans anytime?",
    a: "Yes. Upgrade or downgrade at any time — changes take effect on your next billing cycle. No lock-in contracts.",
  },
  {
    q: "Is there an annual discount?",
    a: "Yes. Pay annually and get 2 months free on any plan. Contact us for annual billing setup.",
  },
  {
    q: "What about HIPAA compliance?",
    a: "All plans include encrypted data in transit and at rest. Enterprise plans include a signed BAA, dedicated compliance support, and full audit trail access.",
  },
  {
    q: "Do you offer a free trial?",
    a: "We offer a 14-day free trial on the Pro plan. No credit card required to start.",
  },
  {
    q: "What happens if I exceed my included calls?",
    a: "You're automatically billed for additional calls at your plan's per-call rate. No service interruption — your workflows keep running.",
  },
];

export default function PricingPage() {
  return (
    <Suspense fallback={null}>
      <PricingContent />
    </Suspense>
  );
}

function PricingContent() {
  const { isAuthenticated, loginWithRedirect } = useAuth0();
  const searchParams = useSearchParams();

  // After login redirect: if ?plan=<tier> is in the URL and user is
  // authenticated, send them straight to Stripe Checkout.
  useEffect(() => {
    const plan = searchParams.get("plan");
    if (plan && isAuthenticated && checkoutUrls[plan]) {
      window.location.href = checkoutUrls[plan];
    }
  }, [searchParams, isAuthenticated]);

  const handleGetStarted = useCallback(
    (tierKey: string) => {
      if (isAuthenticated) {
        window.location.href = checkoutUrls[tierKey];
      } else {
        loginWithRedirect({
          appState: { returnTo: `/pricing?plan=${tierKey}` },
        });
      }
    },
    [isAuthenticated, loginWithRedirect],
  );

  return (
    <>
      {/* Hero */}
      <section className="py-28 md:py-40">
        <div className="mx-auto max-w-7xl px-6">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Pricing
          </p>
          <h1 className="mt-6 max-w-4xl font-serif text-5xl leading-tight tracking-tight md:text-7xl">
            Simple pricing that{" "}
            <span className="text-sage-400">scales</span> with your clinic.
          </h1>
          <div className="mt-10 h-px w-full max-w-md bg-border" />
          <p className="mt-8 max-w-lg text-base leading-relaxed text-muted-foreground">
            A low base subscription for platform access plus pay-per-use on top.
            No surprises, no long contracts. Start small and scale as you grow.
          </p>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-20 md:pb-28">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid gap-6 md:grid-cols-3">
            {tiers.map((tier) => (
              <div
                key={tier.name}
                className={`flex flex-col rounded-2xl border p-8 transition-transform duration-200 hover:scale-[1.03] ${
                  tier.highlight
                    ? "border-sage bg-sage-50/50"
                    : "border-border"
                }`}
              >
                {tier.highlight && (
                  <span className="mb-4 w-fit rounded-full bg-sage-100 px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-sage-600">
                    Most Popular
                  </span>
                )}
                <h3 className="font-serif text-2xl tracking-tight">
                  {tier.name}
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {tier.description}
                </p>
                <div className="mt-6 flex items-baseline gap-1">
                  <span className="font-mono text-5xl font-bold tracking-tighter text-foreground">
                    {tier.price}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {tier.period}
                  </span>
                </div>
                <div className="mt-3 space-y-1">
                  <p className="text-sm font-medium text-foreground">
                    {tier.includes}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {tier.overage}
                  </p>
                </div>
                <div className="mt-8 h-px bg-border" />
                <ul className="mt-6 flex-1 space-y-3">
                  {tier.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-2 text-sm text-muted-foreground"
                    >
                      <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sage-500" />
                      {feature}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => handleGetStarted(tier.key)}
                  className={`mt-8 inline-flex cursor-pointer items-center justify-center rounded-full px-5 py-2.5 text-sm font-medium transition-opacity hover:opacity-80 ${
                    tier.highlight
                      ? "bg-foreground text-background"
                      : "border border-border bg-background text-foreground"
                  }`}
                >
                  {tier.cta}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Enterprise */}
      <section className="bg-sage-50 py-28 md:py-36">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid gap-12 md:grid-cols-[160px_1fr_1fr] md:gap-8">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
              Enterprise
            </p>
            <div>
              <h2 className="font-serif text-4xl leading-tight tracking-tight md:text-5xl">
                Custom plans for{" "}
                <span className="text-sage-400">large organizations.</span>
              </h2>
              <p className="mt-6 max-w-lg text-base leading-relaxed text-muted-foreground">
                Unlimited calls, negotiated rates, signed BAA for HIPAA
                compliance, dedicated support, custom integrations, and SLA
                guarantees. Built for hospital networks and multi-clinic
                operations.
              </p>
              <Link
                href="/contact"
                className="group mt-8 inline-flex items-center gap-2 text-sm font-medium text-foreground transition-colors hover:text-primary"
              >
                Contact sales
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>
            <div className="space-y-0">
              {[
                "Unlimited automated calls",
                "Signed BAA for HIPAA compliance",
                "Dedicated account manager",
                "Custom EMR integrations",
                "99.9% uptime SLA",
                "On-premise deployment option",
              ].map((item) => (
                <div
                  key={item}
                  className="flex items-center gap-3 border-b border-foreground/10 py-5 text-sm text-foreground"
                >
                  <Check className="h-3.5 w-3.5 shrink-0 text-sage-500" />
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            FAQ
          </p>
          <h2 className="mt-6 font-serif text-4xl tracking-tight md:text-5xl">
            Common questions.
          </h2>
          <div className="mt-14 grid gap-x-12 gap-y-0 md:grid-cols-2">
            {faqs.map((faq) => (
              <div key={faq.q} className="border-b border-border py-6">
                <p className="text-sm font-medium text-foreground">{faq.q}</p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {faq.a}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-28 md:py-40">
        <div className="mx-auto max-w-7xl px-6">
          <h2 className="max-w-3xl font-serif text-5xl leading-tight tracking-tight md:text-7xl">
            Start <span className="text-sage-400">automating</span> today.
          </h2>
          <div className="mt-10 h-px w-full max-w-md bg-border" />
          <p className="mt-8 max-w-sm text-base leading-relaxed text-muted-foreground">
            14-day free trial on Pro. No credit card required. Set up your first
            trigger in under 5 minutes.
          </p>
        </div>
      </section>
    </>
  );
}
