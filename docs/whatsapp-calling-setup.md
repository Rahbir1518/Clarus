# WhatsApp calling — setup and testing guide

Written 2026-09-28. How to get Clarus placing real calls to patients over
WhatsApp, and how to demo the product before WhatsApp is ready.

Companion docs: [backend-status.md](backend-status.md) (what is built),
[ai-call-safety-policy.md](ai-call-safety-policy.md) (what the agent may say).

---

## Contents

1. [How a WhatsApp call works](#1-how-a-whatsapp-call-works)
2. [The blocker: Meta's 2,000 messaging limit](#2-the-blocker-metas-2000-messaging-limit)
3. [Choosing the business number](#3-choosing-the-business-number)
4. [Demo path: browser call, no WhatsApp](#4-demo-path-browser-call-no-whatsapp)
5. [Full WhatsApp setup](#5-full-whatsapp-setup)
6. [Development vs production (ngrok)](#6-development-vs-production-ngrok)
7. [Troubleshooting](#7-troubleshooting)
8. [Sources](#8-sources)

---

## 1. How a WhatsApp call works

```
Clarus backend ──HTTPS──▶ ElevenLabs API ──▶ Meta WhatsApp Cloud API ──▶ patient's WhatsApp
      ▲                         │                                          (internet/data)
      └──── post-call webhook ──┘  (the result, after hang-up)
```

- No Twilio, no carrier, no SIM on the patient side. The patient needs WhatsApp
  and a data or Wi-Fi connection.
- **Backend → ElevenLabs** is an outgoing request. It works from anywhere,
  including a laptop.
- **ElevenLabs → backend** (the webhook) is incoming, so it needs a public HTTPS
  URL. In development that is ngrok; in production it is the deployed backend.
- The transport is one setting: `CALL_TRANSPORT=whatsapp` (or `twilio`). The
  agent, the webhook and the database are the same either way.

**Permission.** WhatsApp only lets a business call someone who has agreed to it.
ElevenLabs handles this: if permission is already granted, the call happens
now; if not, it sends a Meta-approved permission template and dials when the
patient taps approve — which may be hours later.

When that happens Clarus parks the run and flags it for review, marks the call
log `outcome = whatsapp_permission_requested`, and counts it as an attempt. The
call carries a signed reference (`clarus_run_ref`), so when the patient
approves and the call finally happens, the webhook finds the right call log
and the workflow continues. Those late calls are always flagged for review,
because nobody checked calling hours at the moment they rang.

Meta's limits on permission requests: **1 per day and 2 per week** per patient.
Once granted, permission lasts until the patient revokes it.

---

## 2. The blocker: Meta's 2,000 messaging limit

Meta turns calling on for a business number only when the account's
**messaging limit is 2,000 or more**. New accounts start at **250**.

The normal way to reach 2,000 is **Meta Business Verification**, which needs
real business documents (trade licence, registered address, etc.) and can take
days. Start it before anything else.

**Check your current limit:** WhatsApp Manager
(https://business.facebook.com/latest/whatsapp_manager/) → **Overview** →
**Messaging limit**.

Two things that look like shortcuts but are not:

- Meta's free **test number** (developer app → WhatsApp → API Setup) has relaxed
  calling rules, but ElevenLabs cannot import accounts created under a
  developer app.
- Meta's **Coexistence** (one number in both the app and the API) is listed by
  ElevenLabs as "coming soon", so it cannot be used yet.

Also: the **business** number's country must not be the US, Canada, Egypt,
Vietnam or Nigeria. A Bangladeshi number is fine. The patient can be anywhere.

---

## 3. Choosing the business number

ElevenLabs can only import a number that is **not** active in the WhatsApp or
WhatsApp Business app, and not registered with another provider. Linking a
number to a business portfolio does not change that.

Using your personal number means:

- deleting that WhatsApp account from your phone first, so it only works
  through the API;
- losing its chat history unless you back it up (the backup cannot be restored
  into the API);
- a hassle to move back later (disconnect from ElevenLabs, re-register in the app).

It also cannot receive the test call, since the business number is the one
placing it. Testing needs a **second** WhatsApp account to answer.

**Recommendation:** buy a cheap prepaid SIM (Grameenphone, Robi, etc.) and use
it only as the clinic's WhatsApp number. Production needs one anyway, and
patients should not be calling a personal number. Do **not** remove your
personal number from the app while the messaging limit is still 250 — you would
lose your WhatsApp and still not get calling.

---

## 4. Demo path: browser call, no WhatsApp

Works today. It is a real conversation with the Bangla agent over WebRTC, and
the outcome shows up live in the app. It uses the same agent, webhook and
database as a WhatsApp call; only the transport differs.

**Limit to keep in mind:** a browser call records the patient's answer but does
**not** book an appointment. Automatic booking only runs when a workflow places
the call, which needs WhatsApp or a phone line.

### 4.1 Install ngrok (once)

```powershell
winget install ngrok.ngrok
```

1. Sign up free at https://ngrok.com.
2. Copy your authtoken from the dashboard and run
   `ngrok config add-authtoken <token>`.
3. In the dashboard, claim your free **static domain**
   (e.g. `yourname.ngrok-free.app`). With it the URL never changes, so the
   webhook is registered once.

### 4.2 Start the backend (terminal 1)

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Check that http://localhost:8000/health responds. If the import fails with a
missing module, the environment is out of date: run `uv sync --extra dev` in
`backend/`.

### 4.3 Start the tunnel (terminal 2)

```powershell
ngrok http --url=yourname.ngrok-free.app 8000
```

### 4.4 Register the webhook

1. Go to https://elevenlabs.io/app/agents/settings → **Post-call webhook** →
   create one with the URL
   `https://yourname.ngrok-free.app/api/elevenlabs/webhook`.
2. Copy the HMAC secret it shows. **It is shown only once.**
3. Add to `backend/.env`:
   ```
   ELEVENLABS_WEBHOOK_SECRET=<the secret>
   PRACTICE_CALLBACK_NUMBER=+880XXXXXXXXXX
   ```
4. Restart the backend (Ctrl+C in terminal 1, run it again). Settings are only
   read at startup.

### 4.5 Start the frontend (terminal 3)

`frontend/.env.local` needs the Clerk keys. `NEXT_PUBLIC_API_URL` defaults to
`http://localhost:8000`.

```powershell
cd frontend
npm run dev
```

### 4.6 Run the demo

1. Go to http://localhost:3000, sign in, open **Patients**, add a patient.
2. Open http://localhost:3000/call-test, pick the patient, click **Start call**,
   allow the microphone.
3. The agent greets you in Bangla. Agree to a time, e.g.
   "আগামী মঙ্গলবার দুপুর আড়াইটা", and end the call.
4. Within a few seconds "Recent calls" shows `completed`, `confirmed: true`, and
   the date and time.

If it stays `in_progress`, the webhook is not arriving: look for
`Rejected ElevenLabs webhook` in terminal 1 (wrong secret) and for the incoming
request in terminal 2.

**Also worth showing:** the workflow builder, and a **Run** that stops with
"⛔ Stopped by a safety rule" because `CALLS_ENABLED=false`. It shows the
guardrails that stop the AI calling patients by accident.

---

## 5. Full WhatsApp setup

### Part A — Meta Business

**A1. Business portfolio.** Create one at https://business.facebook.com, or use
one where you are an **admin**. Use the clinic's real legal name; verification
checks it.

**A2. Business Verification — start first, it is the slow part.** Business
Settings → **Security Center** → **Start verification**. Upload the legal
documents it asks for and confirm by phone, email or domain. After approval the
messaging limit should rise to 2,000; Meta re-checks every few hours.

**A3. A dedicated phone number.** See [section 3](#3-choosing-the-business-number).
It must be able to receive an SMS or voice call for the one-time code.

**A4. Payment method.** In WhatsApp Manager, add one. Meta requires it before
sending permission requests or placing calls, and bills separately from
ElevenLabs.

### Part B — Connect WhatsApp to ElevenLabs

1. https://elevenlabs.io/app/agents/whatsapp → **Import account**.
2. In the Meta window, pick the portfolio, create or select the WhatsApp
   Business account, add the number, verify it with the code.
3. On the account's settings page, assign the Bangla agent. (Optional for
   outbound calls; inbound messages are ignored without one.)
4. In the account's **⋮ menu**, click **Copy phone number ID**. Keep it for Part E.

If the import fails with "number in use", the number is still in a WhatsApp app
or with another provider. Check Business Settings → **Partners** and disconnect
any old provider.

### Part C — Turn on calling (after verification)

WhatsApp Manager → **Account tools → Phone numbers** → **gear icon** next to the
number → **Calls** tab → turn calling **on**.

Greyed out means the messaging limit is still under 2,000 — back to A2.

### Part D — Call-permission template

WhatsApp Manager → **Message templates → Create template**:

| Field | Value |
|---|---|
| Category | Utility |
| Name | e.g. `clarus_call_permission_bn` — lowercase and underscores; write it down exactly |
| Language | Bengali (`bn`) |
| Body | e.g. `আপনার স্বাস্থ্য সংক্রান্ত একটি অ্যাপয়েন্টমেন্ট নিয়ে আমরা আপনাকে WhatsApp-এ কল করতে চাই।` |
| Component | **Call permission request** (sometimes "Voice call permission") |

**No `{{1}}`-style variables.** Clarus sends only the template name and
language, so a template with variables is rejected when sent.

Submit and wait for **Approved**. A pending template silently does not deliver.

### Part E — `backend/.env`

Type the values into the file; never paste secrets into chat or commit them.

```
# --- WhatsApp calling ---
CALL_TRANSPORT=whatsapp
ELEVENLABS_WHATSAPP_PHONE_NUMBER_ID=<from Part B step 4>
WHATSAPP_CALL_PERMISSION_TEMPLATE_NAME=<exact name from Part D>
WHATSAPP_CALL_PERMISSION_TEMPLATE_LANGUAGE=bn

# --- Safety gates ---
# The phone that answers test calls. Not the business number. Only your own.
CALL_ALLOWED_NUMBERS=+8801XXXXXXXXX
CALL_ALLOWLIST_ENFORCED=true
CALLS_ENABLED=false
DEFAULT_TIMEZONE=Asia/Dhaka
CALLING_HOURS_START=9
CALLING_HOURS_END=20

# --- What the agent says ---
PRACTICE_NAME=<clinic name>
PRACTICE_CALLBACK_NUMBER=+880XXXXXXXXXX

# --- Webhook (section 4.4) ---
ELEVENLABS_WEBHOOK_SECRET=<secret>
```

Notes:

- `CALL_TRANSPORT` defaults to `twilio` in code when unset. Set it explicitly.
- `CALLS_ENABLED=false` stops every workflow call. `scripts/test_call.py`
  ignores it but still only dials `CALL_ALLOWED_NUMBERS`.
- Calling hours are measured in **Dhaka time**, wherever you are.

### Part F — Push the Bangla agent

`agents/appointment_confirmation_bn.yaml` is the source of truth; the ElevenLabs
dashboard is overwritten on every sync.

```powershell
cd backend
.venv\Scripts\python.exe scripts\sync_agent.py --spec agents\appointment_confirmation_bn.yaml --dry-run
.venv\Scripts\python.exe scripts\sync_agent.py --spec agents\appointment_confirmation_bn.yaml
```

- Without flags it updates the agent in `ELEVENLABS_AGENT_ID`.
- `--create` makes a new agent instead; copy the printed id into `.env`.
- Success is **"All declared fields are present on the server."** A warning
  about missing fields means every call would come back needing review — fix
  before calling anyone.

### Part G — First WhatsApp call (no database)

Tip: send "Hi" from the test phone to the business number first. That opens a
24-hour chat window, and Meta does not charge for permission requests inside it.

```powershell
.venv\Scripts\python.exe scripts\test_call.py --transport whatsapp
```

1. It prints the dynamic variables and `Calling +8801... over whatsapp`.
2. **First time:** `No conversation id yet: the call is waiting on WhatsApp call
   permission.` The phone gets the permission message — tap **allow**.
3. WhatsApp rings; the agent greets in Bangla. Agree to a time.
4. **Later runs** call straight away and print `Queued. conversation_id=conv_...`.

Read back what the agent extracted:

```powershell
.venv\Scripts\python.exe scripts\test_call.py --conversation conv_XXXXXXXX
```

Expect `outcome: confirmed`, `patient confirmed: True`, the date as
`YYYY-MM-DD` and the time as `HH:MM`. Without an id, find the conversation
under ElevenLabs → Agents → **Conversations**.

Other options: `--reason-code` (one of the fixed reasons in
`app/engine/policy.py`), `--patient-name`, `--doctor-name`, `--to`.

With the webhook running, the backend logs
`No call log for ElevenLabs conversation conv_...` after a script call. That is
**correct**: the signature passed, and the script creates no database row.

### Part H — Full workflow run

1. In `backend/.env` set `CALLS_ENABLED=true`, restart the backend.
2. **Patients** → a patient with the test phone's number (`+880...`).
3. **Triggers → new workflow**: **Lab results received** → **Call Patient**
   (Reason: *Follow-up* or *Annual check-up*) → **Schedule Appointment**
   (duration `30`) → **Send summary to doctor**.
4. **Save**, pick the patient, click **Run** — between **9:00 and 20:00 Dhaka time**.
5. The panel shows "⏳ Call placed — waiting for the outcome". Answer, agree to a time.
6. After hang-up the **Calls** page updates by itself and the appointment is booked.

A **blocked** run names the gate that stopped it (calls off, number not
allowed, outside calling hours, too many calls today). That is the gates
working; fix what it names.

Set `CALLS_ENABLED=false` again when done testing.

---

## 6. Development vs production (ngrok)

ngrok is only for development. The code never uses it.

| | Development | Production |
|---|---|---|
| Backend runs on | a laptop | a host with a public URL (Render, Fly.io, Railway, a VPS…) via `backend/Dockerfile` |
| Webhook URL | `https://<static>.ngrok-free.app/api/elevenlabs/webhook` | `https://api.<yourdomain>/api/elevenlabs/webhook` |

Production settings:

- `ENVIRONMENT=production`
- `CORS_ORIGINS` and `CLERK_AUTHORIZED_PARTIES` = the frontend's domain
- `NEXT_PUBLIC_API_URL` on the frontend
- **One uvicorn worker** (the Dockerfile's default). Live updates are
  in-process; a second worker breaks them.

**Keep dev and prod apart.** If both share one ElevenLabs workspace or agent,
every result goes to whichever webhook URL is registered, and a result that
reaches the wrong backend is dropped silently by design. Use a separate agent
or webhook per environment.

The webhook answers **200** (ElevenLabs requires it) — including for calls it
does not recognise, so it cannot be used to probe which conversation ids exist.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Calls toggle greyed out | Messaging limit under 2,000 | Business Verification (A2) |
| `Missing required configuration: ...` | A `.env` value is empty | Fill in the named key, restart |
| `... is not in CALL_ALLOWED_NUMBERS` | Number format differs | `+880...`, no spaces |
| Permission message never arrives | Template not Approved, no payment method | Check template status and A4 |
| Import fails, "number in use" | Number still in an app or another provider | Remove it; check **Partners** |
| Meta error 131042 | Payment problem | Fix payment in WhatsApp Manager |
| Meta error 132000 / 132001 | Template has variables, or wrong name/language | No `{{}}`; exact name; `bn` |
| Meta error 190 | Access token expired | Re-import the account in ElevenLabs |
| `Rejected ElevenLabs webhook` in log | Wrong secret | Copy it again, restart backend |
| Call ended, nothing in the log | ngrok down or wrong URL registered | Check terminal 2 and the ElevenLabs URL |
| Call stays `in_progress` | Webhook not arriving | Same as the two rows above |
| "outside the calling window" | Outside 9–20 in Dhaka | Wait, or widen the hours temporarily |
| Run shows `whatsapp_permission_requested` | Patient has not approved yet | Expected; it resumes when they approve |
| Bangla prints as `?` or crashes | Old script version | Scripts now force UTF-8; pull latest |

---

## 8. Sources

- [ElevenLabs WhatsApp — Getting started](https://elevenlabs.io/docs/eleven-agents/whatsapp/getting-started)
- [ElevenLabs WhatsApp — Outbound messages & templates](https://elevenlabs.io/docs/eleven-agents/whatsapp/outbound)
- [ElevenLabs WhatsApp — Troubleshooting & FAQ](https://elevenlabs.io/docs/eleven-agents/whatsapp/troubleshooting)
- [ElevenLabs — Post-call webhooks](https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks)
- [Meta — Cloud API Calling](https://developers.facebook.com/docs/whatsapp/cloud-api/calling/)
- [Meta — Call settings](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings)
- [Meta — Messaging limits](https://developers.facebook.com/docs/whatsapp/messaging-limits/)

Meta's rules (limits, supported countries, pricing) change often. Re-check the
Meta pages before relying on the numbers above.
