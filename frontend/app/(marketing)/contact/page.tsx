"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { API_URL } from "@/services/api";

// Sent to our own backend (POST /api/contact), which emails the message to the
// Clarus inbox with the visitor as Reply-To. The backend rate-limits, and
// quietly drops anything that fills the hidden honeypot field or arrives
// faster than a person could type — see backend/app/api/routes/contact.py.
export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shownAt = useRef(0);

  useEffect(() => {
    shownAt.current = Date.now();
  }, []);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    const data = new FormData(e.currentTarget);
    const field = (name: string) => String(data.get(name) ?? "").trim();
    try {
      // Plain fetch, not the authenticated one in services/api: visitors to
      // the public site have no session.
      const res = await fetch(`${API_URL}/api/contact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: field("name"),
          email: field("email"),
          clinic: field("clinic"),
          role: field("role"),
          interest: field("interest"),
          message: field("message"),
          hp_extra: field("hp_extra"),
          elapsed_ms: shownAt.current ? Date.now() - shownAt.current : 0,
        }),
      });
      if (res.ok) {
        setSubmitted(true);
        return;
      }
      const body = await res.json().catch(() => null);
      const details = body?.error?.details;
      if (res.status === 422 && Array.isArray(details) && details.length > 0) {
        const fieldNames: Record<string, string> = { name: "Name", email: "Email", clinic: "Clinic", message: "Message" };
        setError(
          details
            .map((d: { loc?: string[]; msg?: string }) => {
              const name = fieldNames[d.loc?.[d.loc.length - 1] ?? ""];
              const msg = (d.msg ?? "").replace(/^Value error, /, "");
              return name ? `${name}: ${msg}` : msg;
            })
            .join(" "),
        );
      } else {
        setError(body?.error?.message || "Something went wrong. Please try again.");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      {/* Hero */}
      <section className="py-28 md:py-40">
        <div className="mx-auto max-w-7xl px-6">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Contact
          </p>
          <h1 className="mt-6 max-w-4xl font-serif text-5xl leading-tight tracking-tight md:text-7xl">
            Let&apos;s talk about{" "}
            <span className="text-sage-400">automating</span> your clinic.
          </h1>
          <div className="mt-10 h-px w-full max-w-md bg-border" />
          <p className="mt-8 max-w-lg text-base leading-relaxed text-muted-foreground">
            Whether you&apos;re a solo practitioner or a multi-clinic operation,
            we&apos;d love to hear from you. Fill out the form and our team will
            get back to you within one business day.
          </p>
        </div>
      </section>

      {/* Form */}
      <section className="pb-28 md:pb-40">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid gap-16 md:grid-cols-[1fr_320px]">
            {/* Contact form */}
            <div>
              {submitted ? (
                <div className="rounded-2xl border border-border p-10">
                  <h3 className="font-serif text-3xl tracking-tight">
                    Thank you.
                  </h3>
                  <p className="mt-4 text-base leading-relaxed text-muted-foreground">
                    We&apos;ve received your message and will be in touch
                    shortly.
                  </p>
                </div>
              ) : (
                <form
                  onSubmit={handleSubmit}
                  className="relative space-y-6"
                >
                  {/* Honeypot: off-screen and out of the tab order, so only
                      a bot filling every field ever fills it. Its name and
                      label must mean nothing to browser autofill — Chrome
                      filled a field called "website" for real visitors. */}
                  <div aria-hidden="true" className="absolute -left-[10000px] top-auto h-px w-px overflow-hidden">
                    <label htmlFor="hp_extra">Leave this empty</label>
                    <input id="hp_extra" name="hp_extra" type="text" tabIndex={-1} autoComplete="off" data-lpignore="true" data-1p-ignore defaultValue="" />
                  </div>

                  <div className="grid gap-6 md:grid-cols-2">
                    <div>
                      <label
                        htmlFor="name"
                        className="mb-2 block text-sm font-medium text-foreground"
                      >
                        Name
                      </label>
                      <input
                        id="name"
                        name="name"
                        type="text"
                        required
                        maxLength={100}
                        autoComplete="name"
                        placeholder="Dr. Priya Nair"
                        className="w-full rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/20"
                      />
                    </div>
                    <div>
                      <label
                        htmlFor="email"
                        className="mb-2 block text-sm font-medium text-foreground"
                      >
                        Email
                      </label>
                      <input
                        id="email"
                        name="email"
                        type="email"
                        required
                        maxLength={254}
                        autoComplete="email"
                        placeholder="priya@lakeviewclinic.com"
                        className="w-full rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/20"
                      />
                    </div>
                  </div>

                  <div>
                    <label
                      htmlFor="clinic"
                      className="mb-2 block text-sm font-medium text-foreground"
                    >
                      Clinic / Organization
                    </label>
                    <input
                      id="clinic"
                      name="clinic"
                      type="text"
                      maxLength={150}
                      autoComplete="organization"
                      placeholder="Lakeview Family Clinic"
                      className="w-full rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="role"
                      className="mb-2 block text-sm font-medium text-foreground"
                    >
                      Your Role
                    </label>
                    <select
                      id="role"
                      name="role"
                      className="w-full rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                    >
                      <option value="">Select a role</option>
                      <option value="physician">Physician</option>
                      <option value="admin">Clinic Administrator</option>
                      <option value="it">IT / Technical</option>
                      <option value="other">Other</option>
                    </select>
                  </div>

                  <div>
                    <label
                      htmlFor="interest"
                      className="mb-2 block text-sm font-medium text-foreground"
                    >
                      What are you interested in?
                    </label>
                    <select
                      id="interest"
                      name="interest"
                      className="w-full rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                    >
                      <option value="">Select an option</option>
                      <option value="demo">Product demo</option>
                      <option value="pricing">Pricing information</option>
                      <option value="enterprise">Enterprise plan</option>
                      <option value="integration">Integration support</option>
                      <option value="other">Something else</option>
                    </select>
                  </div>

                  <div>
                    <label
                      htmlFor="message"
                      className="mb-2 block text-sm font-medium text-foreground"
                    >
                      Message
                    </label>
                    <textarea
                      id="message"
                      name="message"
                      rows={5}
                      required
                      minLength={10}
                      maxLength={5000}
                      placeholder="Tell us about your clinic and what you're looking for..."
                      className="w-full resize-none rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  </div>

                  {error && (
                    <p className="text-sm text-red-500" role="alert">{error}</p>
                  )}

                  <button
                    type="submit"
                    disabled={submitting}
                    className="inline-flex items-center justify-center rounded-full bg-foreground px-6 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
                  >
                    {submitting ? "Sending..." : "Send message"}
                  </button>
                </form>
              )}
            </div>

            {/* Sidebar info */}
            <div className="space-y-8">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  Response Time
                </p>
                <p className="mt-2 text-sm text-foreground">
                  Within 1 business day
                </p>
              </div>
              <div className="h-px bg-border" />
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  For Existing Customers
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Log in to your dashboard for direct support access.
                </p>
              </div>
              <div className="h-px bg-border" />
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  Enterprise Inquiries
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Need a custom plan with BAA, dedicated support, or on-premise
                  deployment? Let us know in the form.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
