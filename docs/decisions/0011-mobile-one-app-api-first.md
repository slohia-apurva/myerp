# 0011 One mobile app with role workspaces; API-first from Phase 1

- Status: decided as design, 4 Nov 2026
- Context: Sidharth wants a mobile app later, with apps for the production, warehouse, and receiving/dispatch supervisors.
- Decision:
  - One React Native (Expo) app with role-based workspaces (production, warehouse, receiving, dispatch, approvals), not separate apps. It is Phase 12; in v1 the floor screens are mobile-friendly web pages.
  - From Phase 1:
    - All business logic is behind a versioned API (`/api/v1/`).
    - An OpenAPI schema generates a shared TypeScript client.
    - Create and submit calls take idempotency keys.
    - A single scan endpoint resolves any barcode.
    - Lists support changed-since sync.
  - Mobile signs in with Google and gets a revocable per-device token. Offline actions are queued and replayed safely.
