"use client";

/**
 * End-to-end test surface for the WebRTC call path.
 *
 * Deliberately its own page rather than a card bolted onto the patient detail
 * screen: this is the harness you use to prove the whole chain works — token
 * minting, the agent, the Bangla conversation, the post-call webhook, the
 * call_logs write — without first deciding where a "Call now" button belongs
 * in the product. Once the chain is proven, drop <WebCall /> wherever it makes
 * sense and this page can go.
 *
 * It is also where workflow calls are answered while CALL_TRANSPORT=web: a
 * run that reaches call_patient parks, appears under "Waiting to be answered",
 * and resumes from the post-call webhook once the conversation ends.
 */

import { useCallback, useEffect, useState } from "react";

import { WebCall } from "@/components/calls/web-call";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import {
  answerWebCall,
  listCallLogs,
  listPatients,
  listPendingWebCalls,
  startWebCall,
  type PendingWebCall,
} from "@/services/api";

type Patient = { id: string; name: string; phone?: string };
type CallLog = {
  id: string;
  status: string;
  outcome?: string | null;
  confirmed_date?: string | null;
  confirmed_time?: string | null;
  patient_confirmed?: boolean | null;
  needs_review?: boolean;
};

export default function CallTestPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [logs, setLogs] = useState<CallLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPatients()
      .then((rows: Patient[]) => {
        setPatients(rows);
        if (rows.length > 0) setSelected(rows[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // The webhook is what makes an outcome appear here. If a finished call never
  // moves past "in_progress", the tunnel or the signing secret is wrong — not
  // the call.
  const refreshLogs = useCallback(() => {
    listCallLogs()
      .then(setLogs)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(refreshLogs, [refreshLogs]);

  const [pending, setPending] = useState<PendingWebCall[]>([]);
  const refreshPending = useCallback(() => {
    listPendingWebCalls()
      .then(setPending)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(refreshPending, [refreshPending]);

  // A workflow run that parks, and the webhook that completes a call, both
  // announce the row on the event stream — so a call waiting to be answered
  // appears here without a refresh.
  useLiveEvents((event) => {
    if (event.name === "call_log.updated") {
      refreshPending();
      refreshLogs();
    }
  });

  const patientName = (id: string | null) =>
    patients.find((p) => p.id === id)?.name ?? "Unknown patient";

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 p-8">
      <header>
        <h1 className="text-2xl font-semibold">Call test harness</h1>
        <p className="text-sm text-muted-foreground">
          Places a real conversation with the Bangla agent over WebRTC. No
          carrier, no phone number, no per-minute telephony cost.
        </p>
      </header>

      {error && (
        <p className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Waiting to be answered</h2>
          <button
            type="button"
            onClick={refreshPending}
            className="text-sm underline"
          >
            Refresh
          </button>
        </div>
        {pending.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No workflow calls waiting. With CALL_TRANSPORT=web, running a
            workflow that reaches Call Patient puts its call here.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {pending.map((call) => (
              <li key={call.call_log_id} className="rounded-lg border p-4">
                <div className="mb-3 flex justify-between text-sm">
                  <span className="font-medium">{patientName(call.patient_id)}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {call.call_log_id.slice(0, 8)}
                  </span>
                </div>
                <WebCall
                  // No reason, no name, nothing chosen here: the server hands
                  // back the variables the workflow run stored when it parked.
                  begin={() => answerWebCall(call.call_log_id)}
                  startLabel="Answer"
                  onEnded={() => {
                    // The webhook resumes the run a moment after hang-up; the
                    // event stream also refreshes both lists when it lands.
                    setTimeout(() => {
                      refreshPending();
                      refreshLogs();
                    }, 4000);
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <h2 className="text-lg font-medium">Start a call yourself</h2>

      <section className="flex flex-col gap-3">
        <label htmlFor="patient" className="text-sm font-medium">
          Patient
        </label>
        {patients.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No patients yet — create one on the Patients page first. The agent
            greets the patient by name, so it needs a real record.
          </p>
        ) : (
          <select
            id="patient"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2"
          >
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
      </section>

      {selected && (
        <section className="rounded-lg border p-4">
          <WebCall
            // Was a hand-written Bangla sentence and a hard-coded callback
            // number. Both are spoken to the patient, so both moved out of the
            // browser's reach: the reason is a code resolved against a fixed
            // vocabulary, the number is PRACTICE_CALLBACK_NUMBER.
            begin={() => startWebCall(selected, { reasonCode: "annual_check_up" })}
            onEnded={() => {
              // The webhook lands a moment after the conversation closes.
              setTimeout(refreshLogs, 4000);
            }}
          />
        </section>
      )}

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Recent calls</h2>
          <button
            type="button"
            onClick={refreshLogs}
            className="text-sm underline"
          >
            Refresh
          </button>
        </div>
        {logs.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing yet.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {logs.slice(0, 8).map((log) => (
              <li key={log.id} className="rounded-md border p-3 text-sm">
                <div className="flex justify-between">
                  <span className="font-mono text-xs">{log.id.slice(0, 8)}</span>
                  <span>{log.status}</span>
                </div>
                <div className="text-muted-foreground">
                  outcome: {log.outcome ?? "—"} · confirmed:{" "}
                  {String(log.patient_confirmed ?? "—")} · {log.confirmed_date ?? "—"}{" "}
                  {log.confirmed_time ?? ""}
                  {log.needs_review ? " · needs review" : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
