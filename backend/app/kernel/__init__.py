"""Kernel — de plumbing waar elk component op steunt (architectuurdoc §5.8, §13).

Bevat géén businesslogica en hangt van geen enkel domein af. Onderdelen:
- events:   synchrone, in-transactie event-dispatcher (event-ladder trede 1)
- jobs:     achtergrondwerk-primitief (Postgres-jobtabel + scheduler-loop)
- tenancy:  tenant-context + TenantMixin (RLS-klaar: NOT NULL + index)
- history:  snapshot-hulp voor het per-component history-patroon
- contracts: DTO's en event-definities die componenten delen
"""
