---
name: delivery-engineering
description: Design, implement, refactor, or verify development environments, infrastructure, CI/CD, and deployment workflows.
---

# Delivery Engineering

## Procedure

1. Identify the intended environment and operational outcome.

2. Inspect relevant configurations, scripts, pipelines,
   infrastructure definitions, and dependencies.

3. Evaluate:
   - Correctness and reproducibility
   - Security and permissions
   - Reliability and recovery
   - Duplicate or obsolete automation
   - Operational complexity
   - Cost when relevant

4. Choose appropriate tools for the actual requirements.

5. Implement or improve the necessary workflow.

6. Validate each relevant stage using suitable checks.

## Principles

- Do not force Docker, Terraform, Kubernetes, or cloud services.
- Do not assume existing infrastructure design is correct.
- Separate application behavior from infrastructure mechanisms.
- Avoid unnecessary tooling and automation layers.
- Distinguish validation from actual deployment.
- Never perform destructive or live infrastructure operations
  without explicit authorization.