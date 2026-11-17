---
name: frontend-development
description: Change an existing Developers-Hub Next.js portal workflow or its integration with an API endpoint.
---

# Developer portal workflow

Use for a concrete user flow, not generic frontend work.

## Procedure

1. Trace the affected page or feature through:
   - User interaction
   - Frontend state
   - API client
   - Session/project context
   - Backend contract

2. Handle relevant UI states:
   - Loading
   - Empty
   - Permission denied
   - Operation in progress
   - Failed
   - Retry or recovery

3. Keep Next.js server/client responsibilities explicit.

4. Never expose resource credentials in:
   - Logs
   - URLs
   - Persistent browser storage
   - Unrelated UI components

5. Prefer existing UI patterns.
   Avoid introducing another state-management
   framework for a small feature.

6. Validate the requested user journey, including:
   - Project switching
   - Session expiration
   - Failed requests
   - Pending asynchronous operations

7. Run relevant type/build checks.
   Distinguish successful builds from actual browser tests.

## Handoff

Report:
- Observable user outcome
- API integration changes
- Verification performed
- Untested scenarios

Consult frontend/AGENTS.md and frontend/DESIGN.md
only when relevant to the change.