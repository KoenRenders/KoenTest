"use client";
import { useEffect, useRef, useState } from "react";
import type { PostalOption } from "./types";

// Gedeelde postcode-autocomplete (vervangt de drie eerdere varianten, #125).
// Postcode is altijd een dropdown-selectie, nooit vrije tekst: `onChange` levert
// pas een waarde zodra de gebruiker een geldige optie kiest. (Fixed UI-decision.)
export default function PostalAutocomplete({
  value,
  onChange,
  postalCodes,
  required = false,
  placeholder = "Type postcode of gemeente…",
}: {
  value: string;
  onChange: (code: string) => void;
  postalCodes: PostalOption[];
  required?: boolean;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Toon de reeds geselecteerde postcode als leesbare tekst zodra de lijst er is.
  useEffect(() => {
    if (!value) return;
    const match = postalCodes.find((p) => p.postal_code === value);
    setInput(match ? `${match.postal_code} — ${match.municipality}` : value);
  }, [value, postalCodes]);

  useEffect(() => {
    function outside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, []);

  const filtered = input.length < 2
    ? []
    : postalCodes.filter(
        (p) => p.postal_code.startsWith(input) || p.municipality.toLowerCase().includes(input.toLowerCase())
      ).slice(0, 8);

  return (
    <div className="relative" ref={ref}>
      <input
        className="input"
        required={required}
        data-testid="postal-input"
        autoComplete="off"
        value={input}
        placeholder={placeholder}
        onChange={(e) => { setInput(e.target.value); onChange(""); setOpen(true); }}
        onFocus={() => setOpen(true)}
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-10 w-full bg-white border border-gray-200 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto">
          {filtered.map((p) => (
            <li
              key={p.postal_code}
              data-testid="postal-option"
              className="px-3 py-2 hover:bg-blue-50 cursor-pointer text-sm"
              onMouseDown={() => { setInput(`${p.postal_code} — ${p.municipality}`); onChange(p.postal_code); setOpen(false); }}
            >
              <span className="font-medium">{p.postal_code}</span> — {p.municipality}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
