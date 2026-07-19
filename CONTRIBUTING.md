# Contributing to TourneyHub

Thank you for your interest in contributing to TourneyHub!

## Contributor License Agreement (CLA)

TourneyHub is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

Before we can accept your first contribution, you must sign a **Contributor License Agreement (CLA)**. This is required by Decision #1 (NFR-019) and preserves dual-licensing / commercial-hosting optionality while keeping the project copyleft for the public commons.

### Why a CLA?

- The AGPL-3.0 protects the hosted-service commons — operators who modify the networked application must publish their changes.
- The CLA preserves the ability to offer alternative licensing (e.g. for commercial hosting) without requiring copyright assignment from every contributor.
- It is a lightweight agreement: you retain copyright to your contribution and grant the project a broad license to use and relicense it.

### How to sign

1. Read the CLA at [`docs/CLA.md`](./docs/CLA.md) (to be added).
2. Follow the instructions there to sign electronically.

Until the electronic signing flow is set up, please indicate your agreement by including the following line in your first pull request description:

```
I have read and agree to the TourneyHub Contributor License Agreement.
```

**Contributions without CLA agreement cannot be accepted.**

## How to Contribute

1. **Read the docs**: Start with [`AGENTS.md`](./AGENTS.md) (the agent operating manual) and [`PRD.md`](./PRD.md) (the product spec).
2. **Pick a slice**: Check [`spec/requirements.yaml`](./spec/requirements.yaml) for unimplemented requirements.
3. **Follow the workflow**: AGENTS.md §6 describes the slice loop — write failing tests first, implement, verify against the Definition of Done (AGENTS.md §8).
4. **Commit conventions**: Use Conventional Commits with a leading gitmoji (AGENTS.md §9). Reference FR/NFR IDs.

## Definition of Done

Every contribution must pass all gates in AGENTS.md §8 before it is reviewable:

- [ ] `dotnet build` clean (analyzers/format pass)
- [ ] `dotnet test` green
- [ ] Frontend `typecheck` + `lint` + `build` clean (if FE touched)
- [ ] OpenAPI lints and matches implemented endpoints
- [ ] EF migration added + `database update` applies cleanly
- [ ] Tenant-isolation test passes
- [ ] Relevant test vectors covered
- [ ] `spec/requirements.yaml` updated

## Code of Conduct

Be respectful. TourneyHub is a community project for tournament organizers of all competitive disciplines.