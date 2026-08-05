# Phase 6 trusted role model

Phase 6 currently uses a deliberately small server-side identity and role model for the self-hosted deployment. The browser does not choose its trusted user identity or role.

## Trust boundary

The browser calls the API gateway on port 8080. The gateway injects the trusted headers sent to the worker on the internal Docker network:

- `X-SIMQIN-User`
- `X-SIMQIN-Role`

The gateway obtains those values from server environment variables:

- `SIMQIN_USER_ID`
- `SIMQIN_ROLE`

The worker is not published on a host port. Privileged requests therefore pass through the gateway trust boundary.

## Roles

| Role | Review migration | Release action |
| --- | --- | --- |
| `author` | no | no |
| `reviewer` | yes | no |
| `approver` | yes | yes |

The four-eyes rule is independent of the role check: the trusted user ID must still differ from the migration's `created_by` identity.

## Local defaults

`docker-compose.yml` defaults to:

```text
SIMQIN_USER_ID=reviewer-b
SIMQIN_ROLE=reviewer
```

This keeps the migration-review smoke test operational while preventing release actions for the default reviewer identity.

To run locally as an approver in PowerShell:

```powershell
$env:SIMQIN_USER_ID = "approver-a"
$env:SIMQIN_ROLE = "approver"
docker compose up -d --build
```

To run as an author:

```powershell
$env:SIMQIN_USER_ID = "author-a"
$env:SIMQIN_ROLE = "author"
docker compose up -d --build
```

## Current scope

This is a server-side authorization boundary for the current single-user/self-hosted beta. It is intentionally not an authentication provider. A later OIDC or reverse-proxy identity integration should replace the environment-derived principal while retaining the same worker-side `Phase6Principal` permission checks.
