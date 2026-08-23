# Agent 86 Observability and Runtime Configuration Deployment Plan

**Status:** In progress

## Objective

Implement end-to-end Application Insights observability for the React frontend and FastAPI backend, including W3C distributed tracing, standard Application Insights telemetry, and Azure App Configuration-backed dynamic logging settings.

## Approved scope

- Browser telemetry and browser-to-API correlation.
- FastAPI request, dependency, trace, exception, custom-event, and custom-metric telemetry.
- Azure App Configuration provisioning and runtime refresh through the API Container App's system-assigned managed identity.
- Dynamic backend log levels without a revision deployment.
- A safe backend runtime-configuration endpoint for browser-safe configuration.
- Tests, documentation, and deployment workflow updates.

## Azure context

- Subscription: Visual Studio Enterprise Subscription (`1163b53b-c58d-40a4-a8b9-0b87e46b0a62`)
- Resource group: `rg-agent86-dev`
- Location: `westus`
- Application Insights: `appi-agent86-dev`
- Log Analytics workspace: `law-agent86-dev`
- API Container App: `aca-agent86-api-dev`
- Static Web App: `swa-agent86-dev`

## Security decisions

- Continue using Key Vault/Container App secrets for secrets.
- Use Azure App Configuration only for non-secret operational settings.
- Authenticate the API to App Configuration with its system-assigned managed identity and the App Configuration Data Reader role.
- The browser never accesses App Configuration directly and never receives an App Configuration credential.
- Do not emit tokens, raw prompts, model output, file content, or secrets in telemetry.

## Implementation phases

1. Add and validate backend OpenTelemetry/FastAPI instrumentation and structured telemetry.
2. Add browser Application Insights telemetry, W3C propagation, and interaction correlation.
3. Provision and integrate Azure App Configuration for dynamic settings and log levels.
4. Add operational documentation, tests, dashboards/queries, and deployment validation.

## Status log

- Plan approved by the user; implementation in progress.