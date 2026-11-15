# Branches, environments and deploy

## Environments

| Environment | Branch | Where it runs | Database | Data |
| --- | --- | --- | --- | --- |
| Development | `feature/...` | Docker Compose on the PC | `sportlab_dev` | synthetic |
| Staging | `staging` | homelab | `sportlab_staging` | synthetic |
| Production | `main` | homelab, `sportlab.lacrete.casa` | `sportlab_prod` | real |

Automated tests use a throwaway database created on every run.

## Branch flow

1. `main` and `staging` are protected by GitHub rulesets: a pull request and passing automated checks are required. `main` also asks for one approval, and the owner can merge through a pull-request-only bypass. Force pushes and branch deletion are blocked.
2. Every change starts in `feature/...`, `fix/...` or `chore/...` and reaches `staging` through a pull request.
3. Merging into `staging` starts the staging deploy.
4. When it works, `staging` is merged into `main` with a new pull request, and the production deploy starts.

## Deploy

1. GitHub Actions runs tests, style checks and security scans (dependencies and secrets).
2. On merge into `staging` or `main`, Docker images are built and stored in GitHub's private registry (GHCR) with the commit tag.
3. A GitHub runner on the homelab pulls the images and restarts the containers defined in `sportlab-infra`.
4. The migration job runs before the backend; in production it is preceded by a backup.
5. Production requires manual approval (GitHub Environments).
6. Rollback: put back the previous image tag; if a migration is incompatible, restore the backup.

Environment configuration and operating procedures are in the [sportlab-infra](https://github.com/paologiachino/sportlab-infra) repository.

## GitHub settings to configure by hand

- Branch protection for `main` and `staging` (rulesets): required pull request, required status checks, no direct pushes.
- Environments `staging` and `production`, with manual approval for `production`.
- Secret scanning and Dependabot alerts enabled.
