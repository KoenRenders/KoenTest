"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PostalOption } from "./types";

// Eén gedeelde bron voor de postcodes. Module-cache zodat de lijst maar één keer
// over het net komt, ongeacht hoeveel formulieren ze tegelijk gebruiken.
// Gaat via de gedeelde axios-instance (baseURL = backend) i.p.v. een kale fetch,
// zodat het ook werkt wanneer frontend en backend op verschillende origins draaien
// (bv. de e2e-stack); in productie blijft baseURL leeg → relatief via Caddy. (#128)
let cache: PostalOption[] | null = null;

export function usePostalCodes(): PostalOption[] {
  const [codes, setCodes] = useState<PostalOption[]>(cache ?? []);

  useEffect(() => {
    if (cache) return;
    api.get<PostalOption[]>("/api/v1/postal-codes")
      .then((r) => { cache = r.data; setCodes(r.data); })
      .catch(() => {});
  }, []);

  return codes;
}
