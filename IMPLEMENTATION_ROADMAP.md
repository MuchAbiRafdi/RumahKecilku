# Rumah Kecilku — Implementation Roadmap

Status: approved scope; implementation in progress. This roadmap records the decisions made for the requested product expansion. It is not a production-readiness attestation.

## Scope decisions

- Support multiple daycare organizations with strict tenant isolation from the beginning.
- Add an operational `admin` role with least privilege. Admins must not receive raw clinical notes, allergy/medication detail, or KPSP responses by default.
- Store factual safeguarding/health records only (incident facts, allergies, medication authorization/administration); no diagnosis or unsupported clinical inference.
- Defer billing, invoices, payment collection, and payment gateways.
- Keep the local, explainable insight engine: recommendations use structured factual milestone observations, show counts/evidence and missing data, and separate practical caregiver steps from doctor review prompts. Activity logs and raw KPSP answers are not treated as developmental evidence. No third-party AI API. In demo mode, a local Naive Bayes model trained on 96 explicitly synthetic activity scenarios may choose a general nonclinical activity idea; it does not use child records for training and has no clinical validation or developmental prediction scope.

## Delivery sequence and acceptance gates

### Local insight and recommendation flow — implemented as a transparent demo, not clinical AI

**Status: functional for demo/testing.** `evidence-rules-v2` reads only structured milestone observations, shows the count/result/date basis, supplies practical actions for caregivers and separate context/review prompts for doctors, and names missing observations when data is absent. In demo mode, `mock-activity-nb-v1` (pure-Python Multinomial Naive Bayes) is actually trained in memory from 96 mock activity scenarios stored in `backend/app/data/mock_activity_training.json`; it selects only a general, nonclinical activity-idea category. The training set is marked synthetic, contains no child records or clinical labels, and is kept separate from the nine explicitly synthetic preview observations. The parent view remains limited to reviewed/shared information.

**Still open:** no clinically trained or validated ML, no clinical accuracy claim, no developmental prediction/score/diagnosis, and no external AI API. Any future clinical model requires lawful, consented data governance, expert review, calibration, independent validation, monitoring, and a controlled release gate. The demo classifier is not evidence of clinical accuracy.

### 1. Tenant and identity foundation — first implementation slice

**Status: partial foundation implemented.** Organizations, memberships, child-to-organization ownership, server-derived child scopes, admin role boundaries, organization-scoped menus, per-device sensor credentials, and cross-tenant regression tests are in code. A limited guardian-link flow now requires an admin's recorded institutional check plus a separate parent confirmation; pending/revoked links do not grant access, and actions are audited. Legacy links without verification metadata migrate to `pending` and fail closed; the demo account's relation remains explicitly synthetic. Daycare/staff onboarding, account invitations, full identity/guardian verification, and migration tooling for existing operational records remain open; this phase is not a completed launch gate.

- Organization, membership, and child-to-organization ownership must be explicit.
- A staff session sees only children in organizations where the staff account has an active membership. A family session sees only children linked to that family account.
- Every child-scoped read and write must enforce this boundary server-side (not only in the browser).
- Staff/admin accounts are not created through open self-registration; onboarding requires a controlled invitation/provisioning path.
- Demo tenant data remains synthetic and separate from real deployments.
- Cross-tenant regression tests are required before enabling tenant creation for operational use.

### 2. Operational admin and roster

- Least-privilege admin may manage daycare settings, staff assignments, rooms, schedules, and roster; no default access to clinical/KPSP raw records.
- Basic child profiles persist in the backend and tenant admins can update only roster fields (name, birth date, room); profile audit stores the actor and changed field names, not old/new values. The demo supports an admin-recorded institutional check followed by parent confirmation for a guardian link, with revocation and an audit trail; it links only existing parent accounts in the same daycare and stores no identity-document numbers.
- Emergency-contact records, full account invitations/identity checks, and independent identity verification of authorized pickup remain open. Staff invitations and guardian-link/attendance audit hardening are still required for a real deployment.

### 3. Safe daily operations

**Status: partial demo slice implemented.** Caregivers/admins can record same-day check-in/out; check-out requires an active pickup name that an admin added after recording parent confirmation outside the app, plus staff's explicit in-person name-match attestation. Admins can revoke pickup authorization; event history is tenant-scoped and admin-readable. Only name/relationship and confirmation method are stored—no phone, ID number, or document/photo. This is not independent identity verification or an immutable audit system.

- Still open: identity verification, emergency contacts, parent self-service/revocation, handover exception/emergency policy, room/shift/ratio/substitute/calendar data, and full device/browser E2E tests.
- Fact-based incident reporting; allergy and medication access is limited to authorized care staff and clinicians. Medication administration requires a valid authorization and records who/when/what was actually administered.

### 4. Nutrition, communication, and reporting

- Menu nutrients retain item-level provenance and source links; do not invent values.
- Direct-message UI now gives the contact list and thread full width, removes the two side cards, uses a multi-line composer, and stacks on tablet/mobile. The server still limits recipients to contacts linked to the selected child; do not broaden that scope.
- Delivery/read receipts, channel preferences, escalation rules, and closed-app Web Push remain open. In-app notifications are not Web Push; push requires infrastructure and explicit deployment configuration.
- Operational exports and reports are role-scoped, organization-scoped, and audited.

### 5. Privacy, reliability, and launch gates

- Consent, revocation, retention/deletion, access audit, encrypted backups, monitoring, and incident response.
- Browser/E2E tests and independent security review; verify authorization failures across tenants and roles.
- Preserve the production startup gate until unresolved security and compliance blockers are closed.

## Known blockers that remain after the first slice

The current application began as a single-tenant prototype. Do not place real children's data into it until existing repositories, sensor credentials, photo storage, backup/encryption, consent/retention, staff/guardian verification, and deployment controls have all been migrated and independently reviewed. A database schema or demo test alone does not make existing data flows production-safe.
