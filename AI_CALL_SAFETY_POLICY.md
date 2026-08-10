# Clarus — AI call safety policy

Written 2026-08-09, before the workflow engine existed. That order is
deliberate: [REBUILD_CHECKLIST.md](REBUILD_CHECKLIST.md) Phase 0 lists this
decision as one that has to be made before the code that would depend on it,
because a policy written afterwards gets shaped by whatever was already built.

This document is the authority. Where it says **enforced**, there is code that
refuses, and a test that fails if the refusal is removed. Where it says
**not yet enforced**, the gap is named rather than left to be discovered.

---

## The one rule

**The voice agent never discloses a clinical result.**

It may say that results are ready and that the practice would like to book a
time. It may not say what the results were, whether they were normal, what the
values are, what they might mean, or what the patient should do about them.

The distinction is not stylistic. "Your cholesterol came back at 6.8" is a
disclosure of personal health information to whoever picked up the phone,
delivered by a system that cannot verify who that is beyond asking, cannot
answer the question that naturally follows, and cannot tell that the person on
the line has just become distressed.

So the agent's job is narrow: confirm identity, say results are ready, agree a
time, hang up. Everything clinical happens with a human.

### What this costs, stated plainly

A patient who asks "is it bad?" will not get an answer. That is the intended
behaviour, and the agent is instructed to say the practice will discuss it at
the appointment. A workflow author cannot make the call more informative,
because the mechanism that would let them is the mechanism this policy exists
to remove.

---

## How it is enforced

### 1. There is no free-text channel into the call script

**Enforced** — `app/engine/policy.py`, `ALLOWED_CALL_REASONS`.

The reason spoken to the patient is chosen from a fixed vocabulary. A
`call_patient` node carries a `reason_code`, not a sentence:

| `reason_code` | Spoken as | In English |
|---|---|---|
| `results_ready` | আপনার সাম্প্রতিক পরীক্ষার ফলাফল, যা নিয়ে আলোচনা করা প্রয়োজন | your recent test results, which need discussing |
| `follow_up` | একটি ফলো-আপ অ্যাপয়েন্টমেন্ট | a follow-up appointment |
| `annual_check_up` | আপনার নিয়মিত স্বাস্থ্য পরীক্ষা | your regular check-up |
| `medication_review` | আপনার ওষুধের পর্যালোচনা | a medication review |
| `appointment_confirmation` | আমরা আপনার জন্য যে অ্যাপয়েন্টমেন্টটি নির্ধারণ করেছি | an appointment we have booked for you |
| `missed_appointment` | একটি অ্যাপয়েন্টমেন্ট যা মিস হয়ে গেছে | an appointment that was missed |

Bangla, because `DEFAULT_TIMEZONE` is Asia/Dhaka and these calls go to patients
in Bangladesh. The agent definition still declares `language: en` with an English
prompt, so a Bangla reason is currently spoken inside an otherwise English call.
That is what the call-test page already did by hand; it is not a good end state,
and localising `agents/appointment_confirmation.yaml` is a separate change.

An unrecognised `reason_code` is refused, not defaulted. Defaulting would mean
a typo silently changes what a patient is told.

Adding a language means giving each code another phrase and choosing between
them. It does not mean reopening free text.

This replaces the previous design's `lab_result_summary` parameter, which piped
author-written clinical text straight into the prompt. That parameter is gone
from the node catalogue, and its name is on the denylist below so an old saved
graph containing it cannot execute.

### 2. Clinical parameters are refused, not stripped

**Enforced** — `app/engine/policy.py`, `CLINICAL_PARAM_NAMES`.

If a `call_patient` node carries a non-empty parameter named
`lab_result_summary`, `result_summary`, `results`, `lab_values`, `diagnosis`,
`test_result`, `clinical_notes`, `clinical_summary` or `interpretation`, the
node is **blocked** and the branch halts. The call is not placed.

Stripping the value silently was the alternative and was rejected: a workflow
author who wrote a clinical summary intended the patient to hear it, and a
system that quietly drops it leaves them believing it was delivered. A refusal
that names the parameter is the only outcome that tells them the truth.

### 3. An abnormal result never reaches a patient by phone

**Enforced** — `app/engine/policy.py`, `RunContext.abnormal`.

A run is *abnormal-tainted* when either:

- the graph's trigger is `abnormal_result_detected`, or
- the event that started the run carried `metadata.abnormal = true`, or
- a `check_result_values` node took the branch its author marked abnormal
  (`abnormal_branch`, default `true` — the branch where the threshold is met).

A tainted run reaching a `call_patient` node is **blocked**. The engine routes
it to a human instead: the run is flagged `needs_review`, and a notification is
written for the practice.

The default matters. `abnormal_branch` defaults to the *true* branch because
that is how these graphs are drawn — threshold met means escalate — and because
the failure directions are not symmetric. Defaulting the other way would place
calls on abnormal paths until someone noticed.

### 4. A clinical condition that cannot be evaluated stops the branch

**Enforced** — `app/engine/nodes.py`, `check_result_values`.

If a threshold node cannot find the value it needs, or the value is not
numeric, the branch is **blocked** and flagged for review. It does not fall
through to the false branch.

This is the failure the checklist calls out twice: an absent value read as a
negative is how a system decides a result is normal because it could not find
it. There is no safe default for "I do not know", so there is no default.

### 5. The agent's own instructions carry the same boundaries

**Enforced** — `agents/appointment_confirmation.yaml`, under `# Boundaries`,
in version control and pushed with `scripts/sync_agent.py`.

The prompt already forbids medical advice, test results and clinical opinion,
forbids discussing the reason for the call with anyone other than the patient,
forbids stating the reason in a voicemail, requires disclosure that the caller
is automated, and routes a described emergency to emergency services.

Prompt instructions are the weakest of these layers — a language model can be
talked out of them. They are the last line, not the first. The reason the
layers above exist is that they cannot be talked out of anything.

---

## Gates on placing any call at all

Separate from what the agent says: whether it should be dialling. All four fail
closed, all four in `app/engine/policy.py`.

| Gate | Setting | Default | Behaviour |
|---|---|---|---|
| Kill switch | `CALLS_ENABLED` | `false` | No outbound call from any workflow. Per-process, instant. |
| Number allowlist | `CALL_ALLOWED_NUMBERS` | empty | Only these numbers are callable. Empty means none. |
| Calling hours | `CALLING_HOURS_START` / `_END` | 9–20 | Local time in `DEFAULT_TIMEZONE`. Outside the window, blocked. |
| Attempt cap | `MAX_CALL_ATTEMPTS_PER_PATIENT` | 3 | Calls actually placed to one patient in the trailing 24 hours. |

`CALLS_ENABLED` defaults to false so that a fresh checkout, a new environment,
or a forgotten variable places no calls. Every one of these is a variable that,
if absent, must mean *fewer* calls than intended and never more.

The allowlist is checklist stage 1 — synthetic development, your own phone as
the only reachable number, enforced in code rather than by being careful.
Turning it off is `CALL_ALLOWLIST_ENFORCED=false`, which is a deliberate
sentence someone has to write, not something an empty value achieves.

---

## Where clinical detail is allowed to go

Not everything is a patient-facing channel, and treating them all identically
would make the system useless rather than safe.

| Destination | Clinical content | Why |
|---|---|---|
| Words spoken on a call | **Never** | The rule above. |
| Dynamic variables sent to ElevenLabs | **Never** | Anything sent can be spoken, and leaves our control. |
| `notifications` rows (`send_notification`, `send_summary_to_doctor`) | Allowed | Internal, staff-facing, never read to a patient. |
| `call_logs.execution_log` | Allowed | The run's own record, tenant-scoped, soft-deleted with its row. A run that branched on a value has to be able to say which value. |
| `audit_log.metadata` | **Never** | The trail describes an access; duplicating what was accessed into it puts PHI in every log export. Pre-existing rule in `app/db/tenancy.py`. |
| SSE events | **Never** | An `Event` carries a name and a row id and must keep that shape. Pre-existing rule in `app/events/broker.py`. |

---

## Escalation to a human

A run routes to a human by flagging `call_logs.needs_review` and writing a
`notifications` row. `needs_review` defaults to `true` in the schema, so the
failure mode of every path — including one nobody wrote — is a call sitting in
the review queue rather than one that looks finished.

Post-call, `CallResult.needs_human_review` in
`app/integrations/elevenlabs/webhook.py` already escalates a callback request,
a reschedule, an emergency, an opt-out, an outcome the agent did not recognise,
and a confirmation with no pinned date and time. Nothing in this document
loosens any of those.

---

## Not yet enforced

Named because an unwritten gap is indistinguishable from a decision.

- **Consent verified before dialling.** There is no consent table. The
  checklist requires no consent row, no call; today the allowlist is what stops
  a stranger being dialled, which is adequate for synthetic development and
  nothing beyond it.
- **Do-not-call list.** `opted_out` is captured as a call outcome and sends the
  run to review, but no persistent suppression list is consulted before the
  next call.
- **Per-patient timezone.** Calling hours use `DEFAULT_TIMEZONE` for everyone.
  A patient in another zone can be called outside their own local window.
- **Human approval gate before dialling.** Checklist stage 3 requires a person
  to approve each call. The engine currently places approved-by-policy calls
  without one.
- **Durable execution.** A run parks at a call and resumes from the webhook; if
  the webhook never arrives the run stays parked forever, visible only as
  `needs_review`. There is no timer, no dead-letter queue and no retry.

None of these are blocking for synthetic development. Every one of them is
blocking before a real patient is called.
