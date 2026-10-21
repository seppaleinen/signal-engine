# Signal-Engine 0.1.5 Security Hardening

A security audit of the signal-engine 0.1.5 deployment (cluster `192.168.1.95:6443`,
Helm chart `0.1.6`, image tag `0.1.5`) flagged four issues. All four are resolved or
acceptably mitigated in this change (fleet-infra commit `3597df6`, PR #717). The
chart source lives in the `signal-engine` repo; the fleet-infra copy at
`flux/apps/signal-engine/` mirrors it. This ADR records the decision and its
consequences.

## Context

The audit surfaced the following findings:

1. **Non-root execution (CRITICAL).** The image runs as root by default — the
   Dockerfile has no `USER` directive. Both the viewer Deployment and the run
   CronJob lacked pod-level `securityContext`, so every pod ran as root.
2. **Container hardening (CRITICAL).** No container-level `securityContext` was
   set; containers could escalate privileges, drop capabilities, or write
   anywhere on the root filesystem.
3. **Image integrity (HIGH).** The HelmRelease pinned `tag: "0.1.5"` but not a
   digest. A tag can be mutated after publication, so supply-chain integrity was
   not guaranteed at deploy time.
4. **Network segmentation (MEDIUM).** No NetworkPolicy restricted ingress to the
   viewer pod; any pod on the cluster could reach the viewer port.

## Decision

The following changes were made to the Helm chart templates and the fleet-infra
HelmRelease:

1. **Pod-level `securityContext`** added to both the viewer Deployment and the
   run CronJob: `runAsNonRoot: true`, `runAsUser: 1000`, `runAsGroup: 1000`,
   `fsGroup: 1000`, `seccompProfile: { type: RuntimeDefault }`.
2. **Container-level `securityContext`** added to both containers:
   `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`,
   `privileged: false`, `capabilities.drop: ["ALL"]`. `readOnlyRootFilesystem`
   is safe because the only writable paths (`/app/data`, `/app/digests`) are
   PVC-backed and gated by `.Values.persistence.enabled`.
3. **Image digest pinned** in `helmrelease.yaml`:
   `digest: "sha256:7d8b21ed1996a1f078eaab75f0ed5a821ac53deb7ad7b506845c940c48ed5eed"`.
   This is the real arm64 digest of `seppaleinen/signal-engine:0.1.5`.
4. **NetworkPolicy** added at `templates/networkpolicy.yaml`, gated by
   `.Values.networkPolicy.enabled`. It restricts viewer-pod ingress to the
   `ingress-nginx` namespace on the viewer port only.

The registry was deliberately left on public Docker Hub (`seppaleinen/signal-engine`).
A prior commit (`24c6cd75`) had switched from GHCR to Docker Hub because the GHCR
image was unavailable; that decision was not revisited here. `Chart.yaml` stayed at
`0.1.6` and the image tag stayed at `0.1.5` — this was a hardening change, not a
version bump.

## Consequences

- **Positive.** The four audit findings are closed or mitigated. Pods can no
  longer run as root, escalate privileges, write to the root filesystem, or
  accept unsolicited network traffic. Image integrity is enforced at deploy time.
- **Negative / residual.**
  - The `0.1.5` tag is arm64-only on Docker Hub. If the target cluster is amd64,
    the image pull will fail. This is environmental and cannot be verified from
    the current environment (cluster `192.168.1.95:6443` is unreachable —
    `no route to host`). Confirm node architecture when cluster access is
    restored.
  - Digest pinning is the accepted mitigation for this deployment. Sigstore/Cosign
    signing and a private-registry migration remain future recommendations, not
    blockers.
  - `readOnlyRootFilesystem: true` means any future code path that writes outside
    `/app/data` or `/app/digests` will fail at runtime; new writable paths must
    be accompanied by a PVC or an explicit opt-out.