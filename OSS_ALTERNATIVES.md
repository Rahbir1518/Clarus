# Clarus — Open-Source Alternatives Analysis

**Question:** For each vendor in the stack, is there an open-source option that reduces cost?
**Companion docs:** [AUDIT.md](AUDIT.md) · [REBUILD_CHECKLIST.md](REBUILD_CHECKLIST.md)

> ⚠️ **Verify every license and price before adopting.** Both change — several projects have relicensed in recent years (Sentry, Grafana, HashiCorp, Redis all did). Licenses noted below are a starting point for your own check, not legal advice.

---

## The three things to understand before the table

**1. Cost is not your best reason to do this. Control is.**

In [REBUILD_CHECKLIST.md](REBUILD_CHECKLIST.md) Phase 0, the single biggest project risk is: *will ElevenLabs sign a BAA for a PHI workload?* If they won't, your voice layer is dead and the product with it.

Self-hosting the voice pipeline makes that question disappear. PHI never leaves infrastructure you control, so there's no agreement to negotiate. **That's the real argument — the cost savings are a bonus.** Same logic applies to logging: self-hosted log storage fixes the PHI-in-Render's-logs breach identified in [AUDIT.md](AUDIT.md) §4.

**2. Self-hosting AI costs *more* than a vendor below a volume threshold.**

A vendor charges per call. A GPU charges per month whether you use it or not.

```
Rough order-of-magnitude — verify against current pricing:

Managed voice AI      ~$0.30–0.45 per 3-min call   → scales linearly from $0
Self-hosted GPU       ~$300–700/month              → flat, regardless of volume

Break-even ≈ 900–1,800 calls/month
```

Below roughly a thousand calls a month, self-hosting is the *more expensive* option and it costs you engineering time on top. Above it, the gap widens fast in your favour. **Know which side of that line your pilot sits on** — a supervised pilot with one clinic is almost certainly below it.

**3. Your engineering time is the dominant cost, and it isn't on the invoice.**

A small team self-hosting eight services will spend most of its time on ops rather than product. Every self-hosted component for a PHI system also becomes *your* responsibility to patch, back up, monitor, and defend. Pick deliberately; don't self-host by default.

---

## Component-by-component

### 🔴 ElevenLabs — biggest opportunity, by a wide margin

This is where your money goes. Voice AI is roughly **10× the per-call cost of telephony**, so effort spent here returns far more than anywhere else.

ElevenLabs Conversational AI is a *pipeline*, not one product. Replace it piece by piece:

| Layer | Open-source option | License | Notes |
|---|---|---|---|
| **Orchestration** | **Pipecat** | BSD-2 | Purpose-built for voice agents, has Twilio transport. Strong default. |
| | **LiveKit Agents** | Apache-2.0 | Excellent; LiveKit server self-hosts, native SIP support. Best if you want WebRTC too. |
| | Vocode | MIT | Smaller community |
| **Turn detection / VAD** | **Silero VAD** | MIT | Tiny, fast, the standard choice |
| | Pipecat Smart Turn | Open | Semantic turn-taking, better than raw VAD |
| **Speech-to-text** | **faster-whisper** | MIT | CTranslate2 Whisper; the pragmatic pick |
| | Moonshine | MIT | Built for streaming/low-latency |
| | NVIDIA Parakeet | Check per-model | Very accurate, streaming-capable |
| **LLM** | **Qwen 2.5 / 3** | Apache-2.0 | Cleanest license |
| | Llama 3.3+ | Llama Community | Permissive at your scale; read the terms |
| | Mistral | Apache-2.0 (some) | Per-model, check |
| | served by **vLLM** | Apache-2.0 | Production-grade serving |
| **Text-to-speech** | **Kokoro-82M** | Apache-2.0 | Small, fast, good quality — strong fit for phone audio |
| | **Piper** | MIT | CPU-only, very cheap; quality fine for 8kHz phone band |
| | F5-TTS / Chatterbox / Orpheus | MIT / Apache-2.0 | Higher quality, heavier |
| | ⚠️ **XTTS-v2** | **CPML — non-commercial** | **Do not use commercially.** Common trap; Coqui wound down. |

**Verdict:** Highest priority, but **not first**. Build the pilot on ElevenLabs to validate the product, and self-host when either (a) they decline a BAA, or (b) you cross ~1,000 calls/month. Keep it behind the `VoiceProvider` interface from Phase 5 so the swap is a week, not a quarter.

**The hard part is latency, not accuracy.** Phone conversation needs sub-800ms round trip to not feel broken. A self-hosted pipeline can hit it, but budget real engineering time for tuning.

---

### 🟡 Twilio — mostly leave it alone

You cannot open-source your way out of needing a carrier. PSTN access is a regulated telecom relationship.

| Piece | Option | Notes |
|---|---|---|
| Media server / PBX | **Asterisk** (GPL-2.0), **FreeSWITCH** (MPL-1.1), **Kamailio** (GPL-2.0) | Mature, capable, and a genuine specialty to run well |
| Carrier / SIP trunk | VoIP.ms, Thinktel, Les.net (Canadian) | Still a paid vendor — cheaper per minute than Twilio |

**Verdict: keep Twilio for now.** Telephony is ~10% of your per-call cost, so optimizing it is low-leverage. Real-time media handling is unforgiving — NAT traversal, jitter, codec negotiation, SRTP. Revisit only at high volume, and note that LiveKit/Pipecat can talk SIP directly to a cheaper trunk when you do.

---

### 🟢 Auth0 — good, early, low-risk swap

Auth0 pricing escalates sharply exactly where you're headed: multi-tenant organizations, MFA, SSO. Those are the expensive tiers, and you need all three for clinics.

| Option | License | Notes |
|---|---|---|
| **Zitadel** | Apache-2.0 | **Recommended.** Multi-tenant/organizations are native — matches the org model in Phase 3. Modern, Go, self-hosts cleanly. |
| **Keycloak** | Apache-2.0 | Most mature, Red Hat backed, does everything. Heavier to operate. |
| Authentik | MIT | Nice UX, growing |
| Ory (Kratos/Hydra) | Apache-2.0 | Composable, more assembly required |
| Logto / SuperTokens | MPL-2.0 / Apache-2.0 | Good DX, smaller scope |

**Verdict: swap, and do it during the rebuild rather than later.** Identity is painful to migrate once you have real clinic users. Bonus: credentials stay in your Canadian infrastructure, which helps the data-residency story.

⚠️ Auth0 currently supplies the Google Calendar token (badly — see [AUDIT.md](AUDIT.md) §5). If you move off Auth0, you own that OAuth flow directly. That's an improvement — you'll finally hold the refresh token — but budget for it.

---

### 🟢 Observability — swap, for compliance reasons

[AUDIT.md](AUDIT.md) §4 found transcripts and clinical payloads being logged to stdout, landing PHI in Render's log store. Self-hosting logs puts that data back under your control.

| Need | Option | License |
|---|---|---|
| Errors | **GlitchTip** (Sentry-compatible) | MIT |
| | Sentry self-hosted | Functional Source |
| Metrics/logs/traces | **Grafana + Loki + Tempo + Prometheus** | AGPL-3.0 / Apache-2.0 |
| All-in-one | **SigNoz** | MIT |
| Instrumentation | **OpenTelemetry** | Apache-2.0 |

**Verdict: adopt OSS here.** Cheap, straightforward, and a direct compliance win. Use OTel so you're never locked in again.

---

### 🟢 Workflow durability — adopt OSS, this fixes a real bug

[AUDIT.md](AUDIT.md) §5: the current engine holds 20 minutes of state in `asyncio.create_task`, so a deploy silently orphans in-flight calls.

| Option | License | Notes |
|---|---|---|
| **Temporal** | MIT | **Recommended.** Durable execution is precisely this problem. Workflows survive restarts by design. |
| Hatchet | MIT | Lighter, Postgres-backed |
| pgmq / River | PostgreSQL / MIT | Simple Postgres queues, minimal ops |
| arq / Celery / RQ | MIT / BSD | Redis-backed, familiar |
| Windmill | AGPL-3.0 | ⚠️ AGPL — check before embedding |

**Verdict: Temporal.** You're rewriting the engine anyway (Phase 6), and this converts a known class of failure into something the framework handles.

---

### 🟢 Clinical data / documents — adopt OSS, big quality win

This replaces the regex PDF parsing that [AUDIT.md](AUDIT.md) §5 flags as a patient-safety issue, and it's what Phase 5b needs.

| Need | Option | License |
|---|---|---|
| Document extraction | **Docling** (IBM) | MIT |
| | Unstructured | Apache-2.0 |
| OCR | PaddleOCR / Tesseract | Apache-2.0 |
| **HL7 v2 integration** | **Mirth Connect** | MPL-2.0 — the de-facto OSS healthcare integration engine |
| **FHIR** | **HAPI FHIR** | Apache-2.0 |
| FHIR-native backend | **Medplum** | Apache-2.0 — worth a serious look; could absorb a chunk of your data layer |

**Verdict: adopt.** This isn't cost savings, it's correctness — and Mirth in particular is standard in Canadian clinic integrations, which helps credibility in procurement.

---

### ⚪ Supabase — keep managed

Supabase is itself Apache-2.0 and self-hostable, but managed Postgres is inexpensive and self-hosting PHI-grade Postgres means owning backups, PITR, HA, and encryption.

**Verdict: keep managed, in a Canadian region.** Not a meaningful cost line. Spend the ops budget elsewhere. If you later self-host for residency reasons, plain Postgres + your own migrations is simpler than self-hosted Supabase.

---

### ⚪ Vercel / Render — swap later, watch the residency trap

| Option | License |
|---|---|
| **Coolify** | Apache-2.0 |
| Dokku / CapRover | MIT / Apache-2.0 |
| Kamail (Kamal) | MIT |
| OpenNext | MIT — self-host Next.js properly |

⚠️ **The cheapest VPS providers won't work for you.** Hetzner is the usual budget recommendation and it's EU-only — that's a data-residency problem for Ontario PHI. Canadian options: AWS `ca-central-1`, GCP `northamerica-northeast1/2` (Montreal/Toronto), Azure Canada Central, OVHcloud Canada.

**Verdict: defer.** Real savings, but hosting isn't your big cost and the residency constraint erases the cheapest options anyway.

---

### ⚪ Google Calendar — wrong problem to solve

Self-hosted CalDAV exists (**Radicale** GPL, **Baïkal** GPL, **Cal.com** AGPL, **Nextcloud**), but as noted in Phase 5b: **clinics schedule in their EMR.** Replacing Google Calendar with self-hosted CalDAV solves nothing a clinic cares about, and doctors already live in Google or Outlook.

**Verdict: keep Google/Outlook, and invest in EMR write-back instead.** That's the integration that makes the product real.

---

### ⚪ Stripe — keep, but consider OSS metering

You need a payment processor; that's an acquiring relationship, not software. Fees (~2.9% + 30¢) are the cost of doing business.

But your pricing model is **usage-based per call**, and metering that correctly is genuinely fiddly:

| Option | License | Notes |
|---|---|---|
| **Lago** | AGPL-3.0 | Open-source usage-based billing/metering. Good fit. ⚠️ AGPL. |
| Kill Bill | Apache-2.0 | Mature, heavier |

**Verdict: keep Stripe for processing.** Consider Lago if per-call metering gets complicated. Also — the hardcoded test-mode payment links from [AUDIT.md](AUDIT.md) §2 need removing regardless.

---

### ⚪ Web3Forms — just delete it

A contact form doesn't need a vendor. A FastAPI endpoint + SMTP (or Resend/Postmark at trivial cost) does it. Self-hosted mail: **Listmonk** (AGPL), **Postal** (MIT), **Mailu** (MIT) — though running your own outbound SMTP means fighting deliverability, which is rarely worth it.

**Verdict: replace with your own endpoint.** Removes a hardcoded key and a dependency in one move.

---

## Summary — ranked by value per unit of effort

| Priority | Change | Why | When |
|---|---|---|---|
| 1 | **Temporal** for workflow durability | Fixes a known data-loss bug | During Phase 6 rebuild |
| 2 | **Docling + Mirth/HAPI** for clinical data | Fixes a patient-safety issue; required for Phase 5b | During Phase 5b |
| 3 | **Self-hosted observability** | Fixes PHI-in-logs breach | During Phase 8 |
| 4 | **Zitadel** replacing Auth0 | Real savings; migrate before you have clinic users | During Phase 3 |
| 5 | **Self-hosted voice pipeline** | Biggest cost lever *and* removes BAA risk | When BAA fails, or >1k calls/mo |
| 6 | Own contact-form endpoint | Trivial; removes hardcoded key | Anytime |
| — | Hosting, Supabase, Twilio, Stripe, Calendar | Low leverage, or wrong problem | Defer / keep |

## What I'd actually do

**During the rebuild:** items 1–4 and 6. Every one of them is something you're building fresh anyway, so choosing the OSS option costs nothing extra — and three of the four fix a finding from the audit rather than merely saving money.

**Not yet:** the voice pipeline. Build the pilot on ElevenLabs, keep it behind the `VoiceProvider` interface, and let the BAA answer and your call volume decide the timing. Self-hosting it during a pilot would cost more money *and* more time, at the exact moment you should be validating whether clinics want the product at all.

**The one to start investigating now regardless:** whether ElevenLabs will sign. If the answer is no, item 5 jumps to the top of this list and it's better to know in month 1 than month 6.
