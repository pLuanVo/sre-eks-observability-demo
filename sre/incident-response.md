# Incident Response

## Severity Levels

| Level | Criteria | Response SLA | Example |
|-------|----------|-------------|---------|
| P1 — Critical | SLO burn rate > 14.4x (budget exhausted in < 2 days) | 5 min ack, 15 min triage | Complete service outage, data loss risk |
| P2 — High | SLO burn rate > 6x (budget exhausted in < 5 days) | 15 min ack, 30 min triage | Degraded performance, partial outage |
| P3 — Medium | SLO burn rate > 1x (budget slowly eroding) | 1 hour ack | Elevated error rate, slow queries |
| P4 — Low | No SLO impact, cosmetic or minor issues | Next business day | Dashboard glitch, non-critical log noise |

## Escalation Path

```
L0: Automated monitoring (VMAlert → VMAlertmanager)
 │
 ├─ AUTO-REMEDIATION ELIGIBLE?
 │   ├─ YES → L1: MCP Server auto-fix (rollback, pg_terminate, scale)
 │   │         └─ Verify recovery → Log + Notify
 │   │         └─ Recovery failed → Escalate to L2
 │   │
 │   └─ NO → L2: Human SRE on-call
 │             ├─ Follow runbook
 │             ├─ If unresolved in 30 min → L3
 │             └─ Post-incident: write postmortem
 │
 └─ L3: Engineering team lead + affected service owner
         └─ War room if P1
```

## On-Call Expectations

- **Rotation**: Weekly, handoff on Monday 09:00 UTC+7
- **Ack SLA**: Must acknowledge alert within severity SLA (see table above)
- **Tools**: Access to Grafana dashboards, VictoriaMetrics vmui, kubectl, MCP server
- **Handoff**: End-of-shift summary in #sre-handoff channel

## Communication

| Channel | Purpose |
|---------|---------|
| #sre-alerts | Automated alert notifications (VMAlertmanager webhook) |
| #sre-incidents | Active incident coordination |
| #sre-handoff | On-call shift summaries |
| #sre-postmortems | Completed postmortem reviews |

## Post-Incident

1. Blameless postmortem within 48 hours (use `postmortem-template.md`)
2. Action items tracked in issue tracker
3. Postmortem review in next SRE sync meeting
4. Update runbooks if new failure mode discovered
