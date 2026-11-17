---
name: system-design
description: Investigate or change Developers-Hub business concepts, bounded-context ownership, or cross-capability contracts.
---

# Domain and architecture discovery

Use for a substantial change where ownership of a concept,
invariant or API across capabilities is uncertain.
Not needed for ordinary implementation.

1. Identify the developer/operator outcome first;
   explain who performs it and why.

2. Trace one existing end-to-end workflow and compare
   observed code with the proposed product model.

3. Define the smallest consistent vocabulary:
   - Project: team workspace
   - Application: independently deployable unit
   - Environment: logical deployment destination
   - Deployment: release of an artifact
   - Resource: managed infrastructure

4. Name one owner for each invariant, state transition,
   transaction and external effect.

5. Distinguish business subdomains from implemented
   bounded contexts. Default to the existing
   Identity and DeveloperPlatform contexts.

6. Propose the minimum changes and integration sequence.
   Show a short diagram or table only when it helps.

7. Return decisions, trade-offs, unknowns and observable
   acceptance criteria to the coordinator.

Do not create extensive plans or additional bounded
contexts by default.

The live conversation owns the current design decision.

Write a durable decision note only when requested or
when the decision must survive another work session.

Investigation alone does not authorize implementation.