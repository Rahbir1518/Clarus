"use client";

/**
 * Add a patient by hand.
 *
 * The phone number is checked against the chosen country's real numbering plan
 * (libphonenumber's metadata — the same data Android uses), so a Bangladeshi
 * number must be a valid 11-digit 01… number, a Canadian one a valid 10-digit
 * NANP number, and so on. Ranges that were never assigned or have been retired
 * are refused too. What is saved is the E.164 form (+8801…), which is what the
 * calling path dials.
 */

import { useMemo, useState } from "react";
import { X } from "lucide-react";
import {
  getCountries,
  getCountryCallingCode,
  getExampleNumber,
  parsePhoneNumberFromString,
  validatePhoneNumberLength,
  type CountryCode,
} from "libphonenumber-js/max";
import examples from "libphonenumber-js/mobile/examples";

import { Button } from "@/components/ui/button";
import { createPatient } from "@/services/api";

// The pilot's country first; everything else follows alphabetically.
const DEFAULT_COUNTRY: CountryCode = "BD";

const regionNames =
  typeof Intl !== "undefined" && "DisplayNames" in Intl
    ? new Intl.DisplayNames(["en"], { type: "region" })
    : null;

function countryName(code: CountryCode): string {
  try {
    return regionNames?.of(code) ?? code;
  } catch {
    return code;
  }
}

export type PhoneCheck = { ok: true; e164: string } | { ok: false; message: string };

export function checkPhone(raw: string, country: CountryCode): PhoneCheck {
  const input = raw.trim();
  if (!input) return { ok: false, message: "Enter a phone number." };
  if (/[a-z]/i.test(input)) return { ok: false, message: "Phone numbers can only contain digits." };

  const name = countryName(country);
  const example = getExampleNumber(country, examples);
  const exampleText = example ? ` e.g. ${example.formatNational()}` : "";

  // A number typed with its own +code is read as that country's, whatever is
  // selected, so the message names the country the number actually belongs to.
  const parsed = parsePhoneNumberFromString(input, country);
  const lengthProblem = validatePhoneNumberLength(input, country);
  if (lengthProblem === "TOO_SHORT" || lengthProblem === "NOT_A_NUMBER") {
    return { ok: false, message: `Too short for a ${name} number.${exampleText}` };
  }
  if (lengthProblem === "TOO_LONG") {
    return { ok: false, message: `Too long for a ${name} number.${exampleText}` };
  }
  if (lengthProblem === "INVALID_COUNTRY") {
    return { ok: false, message: "That country code is not recognised." };
  }
  if (lengthProblem === "INVALID_LENGTH") {
    return { ok: false, message: `That is not a valid length for a ${name} number.${exampleText}` };
  }
  if (!parsed || !parsed.isValid()) {
    return {
      ok: false,
      message: `That is not a valid ${name} number — it may be mistyped or no longer in use.${exampleText}`,
    };
  }
  return { ok: true, e164: parsed.number };
}

export function AddPatientDialog({
  doctorId,
  onClose,
  onCreated,
}: {
  doctorId?: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [country, setCountry] = useState<CountryCode>(DEFAULT_COUNTRY);
  const [phone, setPhone] = useState("");
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const countries = useMemo(
    () =>
      getCountries()
        .map((code) => ({ code, name: countryName(code), dial: getCountryCallingCode(code) }))
        .sort((a, b) =>
          a.code === DEFAULT_COUNTRY ? -1 : b.code === DEFAULT_COUNTRY ? 1 : a.name.localeCompare(b.name),
        ),
    [],
  );

  const check = checkPhone(phone, country);
  const example = getExampleNumber(country, examples);
  const canSave = !saving && name.trim().length > 0 && check.ok;

  const save = async () => {
    setTouched(true);
    if (!name.trim() || !check.ok) return;
    setSaving(true);
    setError(null);
    try {
      await createPatient({ name: name.trim(), phone: check.e164, doctor_id: doctorId ?? "unknown" });
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add the patient.");
      setSaving(false);
    }
  };

  const inputClass =
    "w-full px-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
        className="bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-2xl"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">Add Patient</h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Full Name *</label>
        <input
          autoFocus
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Jane Doe"
          className={`${inputClass} mb-3`}
        />
        <label className="block text-xs font-medium text-muted-foreground mb-1">Country *</label>
        <select
          value={country}
          onChange={(e) => setCountry(e.target.value as CountryCode)}
          className={`${inputClass} mb-3`}
        >
          {countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name} (+{c.dial})
            </option>
          ))}
        </select>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Phone Number *</label>
        <input
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          onBlur={() => phone && setTouched(true)}
          placeholder={example ? `e.g. ${example.formatNational()}` : "Phone number"}
          aria-invalid={touched && !check.ok}
          className={`${inputClass} ${touched && !check.ok ? "border-destructive focus:ring-destructive" : ""}`}
        />
        <p className="mt-1 mb-4 min-h-4 text-[11px]">
          {touched && !check.ok ? (
            <span className="text-destructive">{check.message}</span>
          ) : check.ok ? (
            <span className="text-muted-foreground">Will be saved as {check.e164}</span>
          ) : null}
        </p>
        {error && (
          <p className="mb-3 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={!canSave}>
            {saving ? "Saving…" : "Save Patient"}
          </Button>
        </div>
      </form>
    </div>
  );
}
