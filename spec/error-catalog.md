# TourneyHub — Stable Error Code Catalog

All API errors use RFC 7807 `application/problem+json` with a stable `code` field. Clients must branch on `code`, never on `title`/`detail`/`status`.

| Code | HTTP Status | Description |
|---|---|---|
| `unknown_error` | 500 | Unhandled server error. |
| `validation_failed` | 422 | Request payload/params failed validation. `errors` map carries per-field messages. |
| `not_supported` | 501 | Feature not implemented yet. |
| `no_tenant_resolved` | 400 | No organization resolved for a tenant-scoped request. |
| `cross_tenant_access` | 403 | Attempted to read/write another organization's resource. |
| `unauthorized` | 401 | Missing or invalid credentials. |
| `forbidden` | 403 | Authenticated but lacks required permission. |
| `email_already_registered` | 409 | Email already in use. |
| `email_not_verified` | 403 | Action requires a verified email address. |
| `invalid_credentials` | 401 | Wrong email or password. |
| `token_expired` | 410 | Verification or password-reset token has expired. |
| `not_found` | 404 | Requested resource does not exist or is not visible. |
| `already_exists` | 409 | Resource with the same identity already exists. |
| `slug_already_taken` | 409 | The requested slug is in use. |
| `concurrency_conflict` | 409 | The entity was modified by another request. Retry with the updated ETag. |
| `precondition_required` | 428 | A mutating request on a versioned resource must include `If-Match`. |
| `idempotency_replay` | — | Internal flag; responses are replayed as the original status. |
| `rate_limited` | 429 | Too many requests; retry after the `Retry-After` period. |
| `invalid_tournament_state` | 409 | The tournament is not in a state that allows this operation. |
| `registration_closed` | 409 | The registration window is closed. |
| `registration_full` | 409 | The tournament has reached its capacity. |
| `participant_already_registered` | 409 | A participant with the same identity is already registered. |
| `duplicate_player_in_tournament` | 409 | A player appears in more than one participant (FR-045). |
| `invalid_result` | 422 | The submitted result does not match the tournament's resultModel/scoreConfig. |
| `bracket_already_generated` | 409 | The bracket has already been generated (use force to regenerate). |
| `insufficient_participants` | 422 | Not enough participants to generate the bracket. |
| `season_already_active` | 409 | Another season is already active in this league (BR-002). |
| `invalid_currency` | 422 | The currency is not supported or does not match the scope. |
| `payment_already_recorded` | 409 | Payment for this registration has already been recorded. |
| `payout_already_paid` | 409 | This payout has already been marked as paid. |
| `insufficient_funds` | 422 | The operation would result in a negative balance. |
| `invalid_money_operation` | 422 | The money operation is invalid (e.g. mismatched currencies). |
| `organization_suspended` | 403 | The organization is suspended (read-only). |
| `sole_owner_cannot_leave` | 409 | The sole OrgOwner must transfer ownership before leaving (BR-106). |
| `invitation_expired` | 410 | The invitation has expired. |
| `invitation_already_accepted` | 409 | The invitation has already been accepted. |
| `idempotency_key_reused` | 422 | The `Idempotency-Key` was already used with a different request payload. |
| `precondition_failed` | 412 | `If-None-Match` / conditional request not satisfiable. |
| `org_owner_required` | 422 | The operation would leave the organization without an owner (BR-013). |
| `league_owner_required` | 422 | The operation would leave the league without an owner (BR-001). |
| `bracket_generation_blocked` | 409 | Tournament already started; regeneration needs `force=true` by an owner (BR-011). |
| `roster_incomplete` | 422 | Participant does not have exactly `team_size` accepted members (FR-044a). |
| `result_confirmation_pending` | 409 | Match awaits opponent confirmation; only confirm/dispute/override are allowed. |
| `invalid_transition` | 409 | Requested state transition is not allowed by the aggregate's state machine. |
| `plan_limit_reached` | 402 | Organization plan limit reached (reserved for ROADMAP M-ENT). |
