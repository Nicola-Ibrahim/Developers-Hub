
# Frontend

Current stack: Next.js, React and TypeScript.

## Structure

frontend/src/
├── app/             # Routes, layouts and API integration
├── features/        # Feature-owned UI and state
├── components/      # Reusable UI elements
└── lib/             # Shared technical utilities

Follow existing conventions where useful.
Restructure when an agreed design warrants it.

## Engineering Guidelines

- Design around user goals and observable workflows.
- Keep components cohesive and responsibilities clear.
- Avoid duplicated state and unnecessary abstractions.
- Separate UI concerns from backend business logic.
- Choose server/client boundaries based on requirements.
- Reuse existing patterns when appropriate.
- Introduce libraries only when they add clear value.
- Evaluate accessibility, responsiveness and error handling.

## Architecture Evolution

Existing components and routes are not permanent constraints.

When redesigning:

- Investigate current user flows and dependencies.
- Identify usability and architectural problems.
- Propose improvements based on product requirements.
- Preserve useful behavior without retaining poor structure.
- Identify and coordinate intentional API changes.

## Verification

From frontend/:

npm run typecheck
npm run build

Verify affected user interactions when possible.
Distinguish build success from runtime verification.
