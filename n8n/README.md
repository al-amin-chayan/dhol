# n8n/

Exported n8n workflow JSON — the researcher sweep, drafting runs, approval
routing, publish, and the metrics loop. Export after every change; the flows
must be restorable onto a fresh host from this directory.

Strip credentials from exports before committing. Flows reference brand
profiles by slug and must never hard-code a brand.
