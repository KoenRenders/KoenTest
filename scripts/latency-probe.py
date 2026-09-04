#!/usr/bin/env python3
"""Meet de serverlatentie per adminroute (#645).

Met htmx is de snelheid van de UI gelijk aan de snelheid van de server: React
verborg trage antwoorden achter optimistische updates, htmx toont ze. Dit script
zet daar een cijfer op — p50, p95 en max per route — zodat "het voelt traag" een
meting wordt in plaats van een indruk.

Gebruik (vanaf de laptop, tegen HDEV):

    python3 scripts/latency-probe.py --base-url https://<hdev-host> \\
        --session "$(cat ~/sessie.txt)" --n 20

De sessiewaarde maak je op de server, en je zet ze NOOIT in de repo of in een
commando dat in je shell-history belandt:

    raakctl exec hdev backend python -c \\
      "from app.domains.auth.api import make_session_value; print(make_session_value('<admin-email>'))"

Zonder --session worden alleen de publieke routes gemeten; de adminroutes geven
dan 401 en worden overgeslagen (met vermelding).

Uitvoer is een markdown-tabel op stdout, klaar om in het release-issue te
plakken. `X-Process-Time` (gezet door de access-log-middleware) staat ernaast, wat
serverduur en netwerkduur scheidbaar maakt.
"""
import argparse
import statistics
import sys

try:
    import httpx
except ImportError:                                   # pragma: no cover
    sys.exit("httpx ontbreekt — draai dit vanuit de backend-omgeving")

# De schermen die ertoe doen: de admin-navigatie plus de twee publieke pagina's
# die het meeste bekeken worden. Bewust een vaste lijst en niet admin_nav()
# importeren: dit script draait vanaf een laptop, buiten de app-omgeving.
ROUTES = [
    ("publiek", "/"),
    ("publiek", "/activiteiten"),
    ("admin", "/admin"),
    ("admin", "/admin/leden"),
    ("admin", "/admin/activiteiten"),
    ("admin", "/admin/betalingen"),
    ("admin", "/admin/ledenwijzigingen"),
    ("admin", "/admin/werkbank"),
    ("admin", "/admin/formulieren"),
    ("admin", "/admin/paginas"),
    ("admin", "/admin/media"),
]


def _percentiel(waarden: list[float], p: float) -> float:
    """p-percentiel zonder numpy: sorteren en de dichtstbijzijnde rang nemen.

    Bij n=20 is p95 de op één na hoogste meting. Dat is grof, en juist daarom
    bruikbaar: meer precisie suggereren dan twintig metingen dragen, zou het
    cijfer betrouwbaarder doen lijken dan het is.
    """
    if not waarden:
        return 0.0
    geordend = sorted(waarden)
    rang = max(0, min(len(geordend) - 1, round(p / 100 * len(geordend)) - 1))
    return geordend[rang]


def meet(client: httpx.Client, pad: str, n: int) -> dict | None:
    duren: list[float] = []
    server: list[float] = []
    status = None
    for _ in range(n):
        antwoord = client.get(pad)
        status = antwoord.status_code
        if status in (401, 403):
            return {"pad": pad, "status": status, "overgeslagen": True}
        duren.append(antwoord.elapsed.total_seconds() * 1000)
        kop = antwoord.headers.get("X-Process-Time")
        if kop:
            try:
                server.append(float(kop))
            except ValueError:
                pass
    return {
        "pad": pad, "status": status, "overgeslagen": False,
        "p50": _percentiel(duren, 50), "p95": _percentiel(duren, 95),
        "max": max(duren) if duren else 0.0,
        "server_p95": _percentiel(server, 95) if server else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", required=True)
    p.add_argument("--session", default=None,
                   help="waarde van de raak_session-cookie (zie de docstring)")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--drempel", type=int, default=300,
                   help="p95 hierboven wordt gemarkeerd (default 300 ms)")
    args = p.parse_args()

    cookies = {"raak_session": args.session} if args.session else {}
    resultaten = []
    with httpx.Client(base_url=args.base_url.rstrip("/"), cookies=cookies,
                      timeout=30.0, follow_redirects=False) as client:
        for soort, pad in ROUTES:
            if soort == "admin" and not args.session:
                resultaten.append({"pad": pad, "overgeslagen": True, "status": None})
                continue
            resultaten.append(meet(client, pad, args.n))

    print(f"| Route | p50 (ms) | p95 (ms) | max (ms) | server-p95 | |")
    print(f"|---|---:|---:|---:|---:|---|")
    for r in resultaten:
        if r.get("overgeslagen"):
            reden = "geen sessie" if r["status"] is None else f"HTTP {r['status']}"
            print(f"| `{r['pad']}` | — | — | — | — | overgeslagen ({reden}) |")
            continue
        vlag = "**traag**" if r["p95"] > args.drempel else ""
        server = f"{r['server_p95']:.0f}" if r["server_p95"] is not None else "—"
        print(f"| `{r['pad']}` | {r['p50']:.0f} | {r['p95']:.0f} | {r['max']:.0f} "
              f"| {server} | {vlag} |")
    print(f"\n_n={args.n} per route; drempel p95 > {args.drempel} ms._")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
