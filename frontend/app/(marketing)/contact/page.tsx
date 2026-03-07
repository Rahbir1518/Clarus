"use client";

import { useState, type FormEvent } from "react";

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = e.currentTarget;
    const data = new FormData(form);
    try {
      const res = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        body: data,
      });
      const json = await res.json();
      if (json.success) {
        setSubmitted(true);
      } else {
        setError(json.message || "Something went wrong. Please try again.");
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
            <span className="text-primary/40">automating</span> your clinic.
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
            {/* Web3Forms form */}
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
                  className="space-y-6"
                >
                  <input
                    type="hidden"
                    name="access_key"
                    value="f3934f91-6ffe-4a8f-9a61-075cb8044676"
                  />
                  <input
                    type="hidden"
                    name="subject"
                    value="New Contact Form Submission — Clarus"
                  />

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
                      placeholder="Tell us about your clinic and what you're looking for..."
                      className="w-full resize-none rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  </div>

                  {error && (
                    <p className="text-sm text-red-500">{error}</p>
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
              <div className="h-px bg-border" />
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  Compliance
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  HIPAA &amp; PIPEDA compliant. TLS 1.2+ in transit. AES-256 at
                  rest.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
