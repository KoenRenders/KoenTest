"use client";

// Gedeeld betaalkeuze-blok voor registratie (1) en "Mijn gezin" (2). Default is
// online (Mollie). Zie #125.
export default function PaymentMethodChoice({
  value,
  onChange,
}: {
  value: string;
  onChange: (method: string) => void;
}) {
  return (
    <div>
      <h3 className="font-semibold text-lg mb-3 text-blue-800">Betaling</h3>
      <div className="space-y-2">
        {[
          { value: "online", label: "Online betalen" },
          { value: "transfer", label: "Overschrijving" },
        ].map(({ value: v, label }) => (
          <label key={v} className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="payment_method"
              value={v}
              checked={value === v}
              onChange={() => onChange(v)}
            />
            <span>{label}</span>
          </label>
        ))}
      </div>
      {value === "online" && (
        <p className="mt-2 text-sm text-gray-600">Je wordt doorgestuurd naar Mollie om veilig online te betalen.</p>
      )}
      {value === "transfer" && (
        <p className="mt-2 text-sm text-gray-600">Na registratie ontvang je de rekeninggegevens per e-mail.</p>
      )}
    </div>
  );
}
