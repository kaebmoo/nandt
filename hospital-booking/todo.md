# Provider Availability & Scheduling Overhaul

## 1. Data Model Extensions (shared_db)
- [x] Add new tables: `template_providers`, `provider_schedules`, `provider_leaves`, optional `resource_capacities`.
- [x] Extend `AvailabilityTemplate` with fields for template type, concurrency, assignment flags.
- [x] Update `Provider` relationships to reference new tables.
- [x] Ensure enums/indexes/constraints (e.g., unique template-provider pair) are defined.
- [x] Draft migration scripts covering tenant schema creation for legacy tenants.

## 2. FastAPI Layer (fastapi_app)
- [x] Update availability endpoints to compute capacity using provider schedules & new tables.
- [x] Add CRUD endpoints for managing template-provider assignments, provider schedules, leaves, and resource capacities.
- [x] Extend booking availability endpoint to return provider lists (when selection allowed) and capacity metadata.
- [x] Update booking creation/reschedule logic to allocate provider (auto or specific) and enforce capacity.
- [ ] Enhance holiday/date override handling to interact with provider-level schedules.

## 3. Flask Admin UI (flask_app)
- [x] Update settings UI (`availability` + `event-types`) to configure template type, provider assignments, and slot capacity.
- [x] Add management interfaces for provider schedules, leaves, and resource capacities.
- [x] Modify booking forms to optionally expose provider selection (with validation rules).
- [x] Ensure reschedule/cancel flows respect new provider scheduling logic.

## 4. Public Booking Flow
- [ ] Adjust calendar rendering to consume new capacity metadata (remaining slots, per-provider options).
- [ ] Implement provider selection UI (conditional) and messaging for auto-assigned scenarios.
- [ ] Update slot fetch logic to include provider availability and room limits.

## 5. Migration & Backfill Strategy
- [x] Create migrations for new tables/columns with safeguards for existing tenant schemas.
- [ ] Provide data backfill scripts to map current templates/providers to new structure.
- [ ] Document migration order and rollback steps.

## 6. Testing & Rollout
- [ ] Add unit/integration tests for capacity calculations and booking flows.
- [ ] Update automated tests for FastAPI and Flask endpoints.
- [ ] Plan phased rollout with feature flags or tenant opt-in.
