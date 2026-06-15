// Lichte wrapper rond de zelf-gehoste Umami-tracker (#152, laag 1).
// No-op zolang de tracker niet geladen is (lokaal/dev, of vóór configuratie),
// zodat funnel-aanroepen overal veilig zijn. Stuur NOOIT PII mee als event-data.
type UmamiTracker = {
  track: (name: string, data?: Record<string, unknown>) => void;
};

declare global {
  interface Window {
    umami?: UmamiTracker;
  }
}

export function trackEvent(name: string, data?: Record<string, unknown>) {
  if (typeof window !== "undefined" && window.umami) {
    window.umami.track(name, data);
  }
}
