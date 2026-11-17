# Frontend

Stack: Next.js 16, React 19, TypeScript.

## Structure

src/
├── app/             # Routes, layouts, API proxy
├── features/        # Feature-owned components and state
├── components/ui/   # Shared visual primitives
└── lib/             # Transport and technical utilities

## Architecture

- Backend is authoritative for business rules and access.
- Keep feature code inside its owning feature.
- Pages compose features; do not duplicate business logic.
- Prefer Server Components unless interaction requires client code.
- Preserve the same-origin API proxy and session contracts.
- Follow installed Next.js documentation when APIs are uncertain.

## Invariants

- Handle loading, empty, error and permission-denied states.
- Prevent stale responses after session/project changes.
- Preserve CSRF, cookie and authorization behavior.
- Never persist revealed credentials in browser storage.
- Do not add dependencies without a concrete requirement.

## Verification

From frontend/:

npm run typecheck
npm run build

Test affected user flows when possible.
A successful build does not prove runtime behavior.
