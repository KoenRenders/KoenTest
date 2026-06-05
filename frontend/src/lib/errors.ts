interface PydanticError {
  type: string;
  loc: (string | number)[];
  msg: string;
}

const FIELD_NAMES: Record<string, string> = {
  email: "e-mailadres",
  first_name: "voornaam",
  last_name: "achternaam",
  date_of_birth: "geboortedatum",
  phone: "telefoonnummer",
  mobile: "gsm-nummer",
  postal_code: "postcode",
  street: "straat",
  house_number: "huisnummer",
  bus_number: "busnummer",
  contact_name: "naam",
  contact_email: "e-mailadres",
  contact_phone: "gsm-nummer",
  team_name: "ploegnaam",
  group_size: "aantal personen",
  remarks: "opmerkingen",
};

function locToLabel(loc: (string | number)[]): string {
  const parts = loc.filter((p) => p !== "body");
  const labels: string[] = [];
  let i = 0;
  while (i < parts.length) {
    const part = parts[i];
    if (part === "members" && typeof parts[i + 1] === "number") {
      labels.push(`Gezinslid ${(parts[i + 1] as number) + 1}`);
      i += 2;
      continue;
    }
    if (typeof part === "string") {
      labels.push(FIELD_NAMES[part] ?? part);
    }
    i++;
  }
  return labels.join(" — ");
}

function msgToDutch(err: PydanticError): string {
  const { type, msg } = err;
  if (type === "value_error" && msg.toLowerCase().includes("email")) {
    return "Ongeldig e-mailadres";
  }
  if (type === "missing") return "Dit veld is verplicht";
  if (type === "string_too_short") return "Te kort";
  if (type === "string_too_long") return "Te lang";
  if (type === "int_parsing") return "Moet een getal zijn";
  if (type === "greater_than" || type === "greater_than_equal") return "Moet groter zijn dan 0";
  return "Ongeldige waarde";
}

export function parseApiError(
  err: unknown,
  fallback = "Er is iets misgelopen. Controleer je gegevens en probeer opnieuw."
): string {
  if (!err || typeof err !== "object") return fallback;

  // Axios error
  const axiosErr = err as { response?: { status?: number; data?: { detail?: unknown } } };
  const detail = axiosErr.response?.data?.detail;

  if (axiosErr.response?.status === 422 && Array.isArray(detail)) {
    const messages = (detail as PydanticError[]).map((e) => {
      const label = locToLabel(e.loc);
      const msg = msgToDutch(e);
      return label ? `${label}: ${msg}` : msg;
    });
    return messages.join("\n");
  }

  if (typeof detail === "string") return detail;

  // fetch-based error (Error instance thrown manually)
  const fetchErr = err as { message?: string };
  if (fetchErr.message) {
    try {
      const parsed = JSON.parse(fetchErr.message);
      if (Array.isArray(parsed)) {
        const messages = (parsed as PydanticError[]).map((e) => {
          const label = locToLabel(e.loc);
          const msg = msgToDutch(e);
          return label ? `${label}: ${msg}` : msg;
        });
        return messages.join("\n");
      }
    } catch {
      return fetchErr.message;
    }
  }

  return fallback;
}
