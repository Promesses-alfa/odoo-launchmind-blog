# Changelog

## 18.0.1.6.0

Release candidate. Customer rollout is not authorized by this artifact.

- Require explicit website/blog selection and lock it once owned posts exist.
- Update and withdraw owned articles, reconcile local deletion, and retain
  per-item retry and media-pending outcomes.
- Store delivered cover/inline images locally with bounded admission.
- Use connector-owned authors and exact-label native tags without modifying
  shared customer identities.
- Preserve native SEO and add Article JSON-LD only where no article owner exists.
- Add customer-first discovery, opt-in telemetry, daily runtime health and
  production-proof-gated IndexNow, disabled by default.
- Add per-installation signed enrollment, timestamped HMAC and durable replay
  admission. Pending enrollment holds delivery; signed failures never downgrade.
- Enforce the actual Odoo 18 runtime and isolate native database duplicates.
- Produce a versioned reproducible ZIP and an allowlisted release-mirror export.

Customer installation, production migrations, canary publication, backlog
activation and live IndexNow submission are not part of release preparation.
