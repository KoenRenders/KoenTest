"use client";
import { useEffect, useState } from "react";
import type { PostalOption } from "./types";

// Eén gedeelde bron voor de postcodes. Module-cache zodat de lijst maar één keer
// over het net komt, ongeacht hoeveel formulieren ze tegelijk gebruiken.
let cache: PostalOption[] | null = null;

export function usePostalCodes(): PostalOption[] {
  const [codes, setCodes] = useState<PostalOption[]>(cache ?? []);

  useEffect(() => {
    if (cache) return;
    fetch("/api/v1/postal-codes")
      .then((r) => r.json())
      .then((data: PostalOption[]) => { cache = data; setCodes(data); })
      .catch(() => {});
  }, []);

  return codes;
}
