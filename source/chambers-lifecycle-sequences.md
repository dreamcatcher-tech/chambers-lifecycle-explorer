# Chambers lifecycle sequence reference

Status: **Current working architecture authority; downstream reconciliation pending**

Architecture classification: `architecture_delta_required`

Design-lineage baseline: `b3fdfb17a9130394b66311fe9e120797a2768273`

This document is the current Chambers lifecycle architecture authority. It owns the working design
for lifecycle identity, state, sequencing, authority boundaries, custody, routing, verification,
selection, quiescence, and recovery until it is explicitly superseded. The broader
[`ark-agent-architecture.md`](ark-agent-architecture.md), owning Gherkin, schemas, implementation,
and generated projections are downstream reconciliation targets and may temporarily lag this design.
This status establishes design authority; it does not claim implementation or runtime acceptance.

## Contents

- [Lifecycle axioms](#lifecycle-axioms)
- [Lifecycle call table](#lifecycle-call-table)
- [Authoring and state shapes](#authoring-and-state-shapes)
- [Overall lifecycle](#overall-lifecycle)
- [Engine cold start](#engine-cold-start)
- [Bootstrap core services](#bootstrap-core-services)
- [Ordinary Chamber activation kernel](#ordinary-chamber-activation-kernel)
- [Fenced development](#fenced-development)
- [Form and activate a candidate](#form-and-activate-a-candidate)
- [Build an artifact](#build-an-artifact)
- [Verify a candidate](#verify-a-candidate)
- [Select or roll back](#select-or-roll-back)
- [Quiesce and wake](#quiesce-and-wake)
- [Attested multi-Ark builds (later)](#attested-multi-ark-builds-later)
- [Failure and recovery formulas](#failure-and-recovery-formulas)
- [Implementation handoff](#implementation-handoff)

## Lifecycle axioms

### Identity

- `Covenant locator = provider coordinates + optional logical credential need`.
- `provider = access, authority, and location family`.
- `kind = logical content form`.
- `immutable identity = provider-native commit, tree, digest, CID, or snapshot`.
- `credential = named Vault need`; it is never a secret value, token, or leased credential.
- `Covenant = location-independent promise`; it does not name the repository containing itself.
- `Covenant lock = exact transitive closure of Covenant bytes, provider-native revisions, image/build inputs, mounts, workers, hardware, and launch policy`.
- `Covenant lock != Realization`; a lock alone is never authority to launch `current`.
- `Realization = Covenant lock + exact boot artifact + artifact acceptance + launch plan`.
- `realization id = digest(realization manifest body)`.
- `registration contract = digest(canonical declared worker and export set for one exact Realization)`.
- `libp2p PeerId = proof-of-possession transport identity`; it is neither Chamber identity nor authority.
- `Realization = immediately launchable from exact identity`; launch performs no identity-forming resolution,
  dependency choice, build, mutable-tag lookup, or artifact substitution.
- `Build receipt = build request id + Builder realization id + output artifact id + evidence root`.
- `Inspection receipt = artifact id + plan id + evidence root + verdict`.
- `Acceptance receipt = artifact id + evidence receipt ids + policy id + decision`.
- `Run receipt = realization id + Chamber id + host evidence + runtime-spec id + outcome`.
- `latest = resolution policy`; it is never runtime identity.

### Cardinality

- `one Chamber -> one runnable Covenant realization`.
- `one runnable Covenant realization -> zero or many concurrent Chambers`.
- `one durable named Runnable lifecycle -> zero or one current realization + zero or many candidate realizations`.
- `one Chamber -> one lease + one independent failure and cleanup fate`.
- `one runnable Covenant -> one or more workers inside that Chamber`.
- `Assembly Covenant -> process-tree subtree`; the Assembly itself has no Chamber.
- `Contract Covenant -> promise only`; it has no Chamber.

### Runtime

- `Realization = immutable + transportable`.
- `Chamber = one ephemeral host-local activation of one exact realization`.
- `Activation` is not a separate lifecycle identity or record; `activate` is the operation that creates a Chamber.
- `containerd/runsc state = disposable cache`.
- `current realization may have zero live Chambers`.
- `activate(realization, lease) = committed Chamber intent -> fresh Chamber id -> readiness or terminal failure`.
- `restart = same realization + fresh Chamber id`.
- `activate current(name) = snapshot current revision + exact realization -> fresh Chamber + run receipt`.
- `activate candidate(name, realization) = valid Hold + exact realization -> fresh Chamber + run receipt`.
- `same lock + different non-repeatable build output = different realization`.
- `missing exact artifact = exact realization cannot start`.
- `realize from Covenant lock = candidate formation`; it never recreates or silently replaces `current`.

### State

- `durable named process tree = Assembly-expanded logical names + revisioned current selections`.
- `current[name] = {revision, realization}`.
- `candidates[name][realization id] = Hold reference`; candidate state adds no duplicate realization fields.
- `chambers[Chamber id] = {name, realization, lease, phase}`.
- `admissions[lease] = {peer id, Chamber id, realization, registration contract, listener,
  connection epoch, profile, expiry, state}`; it is the durable `procman` authority behind the
  Engine's disposable PeerId admission index.
- `phase = intended | starting | ready | stopping`; terminal Chambers leave immutable receipts, not live state.
- `operations[operation id] = durable intent until matching terminal receipt`; unrelated Chamber starts do not
  share one inline per-name operation lock.
- `last(name) = prior realization in the latest completed selection receipt`.
- `next(name) = exact candidate named by an open fenced selection operation, otherwise null`.
- `new exact development or build output -> candidate`; several candidates may coexist.
- `Realization` is the sole public immutable executable lifecycle identity; there is no parallel
  `Generation` noun or record.
- `selection receipt = completed compare-and-swap from expected current (possibly null) to one exact realization`.

`current`, `last`, and `next` are readable projections over selection, candidate Holds, and history;
they are not three Chamber-bearing slots. A Hold is one exact reference to bounded candidate custody;
its owner, expiry, and cleanup authority remain transitively bound by that referenced receipt rather
than repeated in candidate state.

### Routing

- `route(name) = activation factory for current[name]`; it is not a Chamber selector.
- `route(Chamber id) = exact ready Chamber` for admitted execution and inspection.
- Candidate and fixture calls use exact realization and Chamber selectors; they never acquire the stable
  current route before selection.
- `exports(function) = worker endpoint inside the addressed Chamber`.
- An exact-Chamber export is unavailable until libp2p Noise has authenticated both pinned peers,
  the HPM admission permits the Worker Manager stream, the Engine has assigned `chamber::<Chamber id>`,
  and the complete registration contract has matched.
- Engine routing is built in; a physical route cache is never authority.
- `procman` supplies current revisions and exact Chamber observations to Engine routing;
  it does not maintain a second writable current or route authority.

### Transition

- `operation intent -> physical/Engine effect -> evidence -> operation receipt`.
- Intent is durable before effect; completion follows evidence.
- `selection = compare-and-swap current[name] from expected revision to exact candidate realization`.
- `promotion selects a realization, never a Chamber`.
- `selection affects future Chambers`; existing Chambers remain pinned until completion, cancellation, or
  explicit drain.
- `rollback = the same fenced selection operation targeting a retained accepted realization`.
- Reaping a Chamber never changes current selection or candidate custody.

### Authority

- Supervisor proposes logical change and ordinary Chamber activation.
- `procman` owns current/candidate/Chamber state mutation and physical Chamber creation/reaping.
- Supervisor resolves the Covenant/Realization worker exports into an immutable, content-addressed
  registration contract; `procman` binds that contract to the physical launch admission.
- `procman` mints each non-Engine Chamber's fresh lease-scoped libp2p identity, commits only its
  public PeerId binding, and supplies private key material through a protected runtime capability.
- For an Engine Chamber, the HPM likewise commits the expected boot-scoped Engine PeerId and its exact
  Chamber, Realization, listener, lease, and epoch binding before launch; `procman` pins that PeerId.
- `procman` materializes Chambers from accepted exact artifacts; it is not an image builder.
- Engine owns typed transport, registration, derived routing, and the ordinary activation-factory surface.
- Engine owns the Noise listener, PeerId connection gate, Worker Manager stream gate, server-assigned
  Chamber prefix, complete-set registration quarantine, and atomic publication into its built-in router.
- Vault owns live ordinary-RBAC authorization after Noise authentication; Noise key possession does not
  grant Chamber status, direct authority, function registration, or router mutation.
- `procman` owns the irreducible Engine wake edge; it may activate only the exact selected
  Engine realization and does not choose application policy.
- Filesystem/provider adapters own exact resource custody and transfer.
- Tester or the gate-appropriate verifier judges an exact candidate realization and Chamber.
- A distinct fenced promoter authorizes current selection.
- No Chamber receives the runtime socket or raw host path.

## Lifecycle call table

Every arrow in a `sequenceDiagram` below is an invocation labelled with exactly one function name.
Function completion and results are implied by the invocation and are not drawn as separate arrows.
Arguments, results, and local state changes remain in the surrounding text or Mermaid notes rather than
inside arrow labels. I3 SDK registration, libp2p Noise negotiation, stream admission, and router
publication are notes because they are protocol or local Engine transitions rather than I3 function
invocations.

Names containing `::` are I3 function IDs. The snake-case rows marked **external conventional call
(not I3)** are ordinary code calls made outside the Engine through the trusted host boundary. They
are listed explicitly because no Engine can route the cold wake or physical process effect that they
represent. Owner repositories define payload schemas, but those schemas must preserve the authority
boundaries in this document. Every call remains capability-scoped and fail closed.

### Participant order

Participant lanes are declared in architectural order, not in first-call order. A right-to-left arrow is
therefore legitimate and clearer than moving foundational actors between diagrams merely to make every
message point right. Apply these strata consistently from left to right:

1. `procman`, whenever present, is the leftmost lane because it is the irreducible host lifecycle authority;
2. the mechanism-only Image Materializer and its disposable `containerd` cache follow `procman` when
   exact OCI content must become locally runnable;
3. the trusted host runtime follows those host-materialization lanes whenever a physical create, start,
   stop, or reap effect appears;
4. the I3 Engine and then the authorized Supervisor/control plane;
5. addressed workload Chambers and workers;
6. Filesystem, Vault, custody, and other resource providers;
7. independent verifiers, promoters, and other assurance gates; and
8. external callers, requesters, or wake sources at the right edge.

Diagrams that omit a stratum preserve the relative order of the strata that remain. Every
`activate_chamber` or `stop_chamber` arrow targets the trusted host runtime, never the absent or running
Chamber that is the subject of the effect; a note names that exact subject.

### procman

| Function | Invocation path | Brief contract |
| --- | --- | --- |
| `chambers::process::propose` | I3 | The sole public `procman` mutation surface. Submit one exact typed and fenced lifecycle operation; `procman` commits intent before changing current, candidates, Chambers, attachments, admission, or quiescence state. |
| `chambers::process::inspect` | I3 | Return a capability-scoped read-only view of current selections, candidate Holds, Chambers, lease admissions, open operations, and receipt references. It cannot mutate state or establish a second route authority. |
| `wake_engine` | **External conventional call (not I3)** | An authenticated lower wake source submits one bounded wake and reply capability directly to `procman` while the Engine may be absent. |
| `deliver_final_reply` | **External conventional call (not I3)** | `procman` uses the handed-off lower reply capability after the required terminal receipt is durable; no stopped Engine is involved. |

The cold wake edge is deliberately outside I3: when no Engine Chamber exists, I3 routing is also absent.
After exact Engine readiness, `procman` registers `chambers::process::propose` and
`chambers::process::inspect` with the Engine.

### Image materializer and containerd

| Function | Invocation path | Brief contract |
| --- | --- | --- |
| `materialize_image` | **External conventional call (not I3)** | `procman` asks the mechanism-only Image Materializer to make one exact OCI descriptor locally runnable without treating cache state as authority. |
| `inspect_image` | **External conventional call (not I3)** | The Image Materializer inspects derivative `containerd` manifest, content, and unpacked-snapshot records by exact digest; a tag or name is insufficient. |
| `import_image` | **External conventional call (not I3)** | The Image Materializer imports digest-verified authoritative OCI manifest, config, and layers supplied through a sealed read-only capability. |
| `unpack_image` | **External conventional call (not I3)** | The Image Materializer asks `containerd` to create a derivative unpacked snapshot for the exact image and host-pinned runtime profile. |

Only the Image Materializer holds the `containerd` socket. `containerd` is a disposable acceleration cache,
not image authority: deleting its complete state must preserve reconstruction from authoritative OCI content.
Builders and the Filesystem Service never receive its socket.

### Trusted host runtime

| Function | Invocation path | Brief contract |
| --- | --- | --- |
| `activate_chamber` | **External conventional call (not I3)** | After exact image materialization, `procman` calls the trusted host runtime directly to create/start one exact Chamber through pinned runsc. The Chamber is the subject created by the call, not its receiver. |
| `stop_chamber` | **External conventional call (not I3)** | `procman` calls the trusted host runtime directly to stop and reap one exact Chamber after durable stop intent. The Chamber is the subject reaped by the call, not its receiver. |

### I3 Engine

| Function | Invocation path | Brief contract |
| --- | --- | --- |
| `engine::route::inspect` | I3 | Return operation-bound registration and readiness evidence for one exact non-Engine Chamber. |
| `engine::route::fence` | I3 | Fence new factory admissions for one logical name at the expected current revision. |
| `engine::route::install` | I3 | Install the derived activation factory for one newly selected revision and Realization. |
| `engine::route::reopen` | I3 | Reopen a fenced factory at the unchanged authoritative revision after a failed selection. |
| `engine::wake::deliver` | I3 | Deliver one already authenticated wake event and its bounded reply capability over the exact Noise-authenticated, HPM-authorized Engine session. |
| `engine::quiescence::plan` | I3 | Close admission and return the dependency-ordered exact Chamber stop plan. |
| `engine::quiescence::chamber` | I3 | Drive one exact Chamber to terminal quiescence evidence under the committed host stop plan. |

### Filesystem Service

| Function | Invocation path | Brief contract |
| --- | --- | --- |
| `resource::resolve` | I3 | Resolve a permitted locator once, or fetch an exact selector, and return verified immutable descriptors or bounded transfer capabilities. |
| `filesystem::object::read` | I3 | Read an exact content-addressed lifecycle object through capability-gated Filesystem custody. |
| `filesystem::hold::acquire` | I3 | Acquire one bounded Hold over exact candidate Realization custody. |
| `filesystem::hold::transfer` | I3 | Transfer one exact candidate Hold into selected-current custody under the fenced selection operation. |
| `filesystem::hold::release` | I3 | Release one exact candidate Hold after authorized rejection, expiry, cancellation, or cleanup. |
| `resource::workspace::open` | I3 | Open one writer-fenced mutable workspace from an exact base and return its scoped attachment capability. |
| `resource::workspace::edit` | I3 | Apply an authorized mutation through the workspace fence without exposing a raw host path. |
| `resource::workspace::renew` | I3 | Renew the same workspace fence and lease for the same owner and cleanup duty; it cannot change lineage. |
| `resource::workspace::close` | I3 | Terminalize one exact workspace fence and reap unretained overlay data. |
| `resource::snapshot` | I3 | Atomically seal the exact fenced workspace bytes as an immutable content-addressed revision under bounded custody. |
| `resource::commit` | I3 | Consume one exact sealed snapshot into a durable provider-native revision and receipt; it neither publishes remotely nor selects a Realization. |
| `filesystem::resources::flush` | I3 | Flush the declared durable resources covered by one committed stop operation and return operation-bound receipts. |
| `image::seal` *(optional later)* | I3 | Verify and atomically seal an exact OCI manifest, config, layers, and build receipt; it does not accept or select the resulting artifact. |

### Supervisor

| Function | Invocation path | Brief contract |
| --- | --- | --- |
| `chamber::inspect` | I3 | Return the Supervisor's capability-filtered logical lifecycle view assembled from authoritative `procman` and owner observations. |
| `chamber::covenant::load` | I3 | Orchestrate locator or lock resolution into an exact candidate Realization and Hold, optionally requesting a candidate Chamber; it cannot write `current`. |
| `chamber::workspace::materialize` | I3 | Orchestrate a named fenced workspace and its staged attachment to one exact Developer Chamber activation. |
| `chamber::version::candidate_event` | I3 | Receive an exact candidate lifecycle, evidence, expiry, or cleanup event and drive only the next separately authorized step. |
| `chamber::quiesce` | I3 | Coordinate dependency-ordered quiescence, durable flush, and final reply-duty handoff to `procman`. |

### Builders, verifiers, and gates

| Function | Invocation path | Brief contract |
| --- | --- | --- |
| `artifact::build` *(optional later)* | I3 | Execute one exact build request and return an exact artifact descriptor plus build receipt; it does not accept or select the output. |
| `artifact::accept` | I3 | Judge one exact artifact, evidence set, and policy and return an acceptance receipt or rejection. |
| `attestation::verify` *(later)* | I3 | Appraise fresh confidential-environment evidence bound to one builder identity and exact statement. |
| `verification::invoke` | I3 | Execute the exact candidate and fixture verification plan through exact Chamber routes and return subject-bound evidence and a verdict. |
| `selection::authorize` | I3 | Have the distinct fenced promoter validate fresh MET evidence and issue and consume one exact, one-use compare-and-swap permit. |

Only `chambers::process::propose` may reach `procman`-owned mutation. Selecting `current` additionally requires
the distinct promoter authorization described in **Select or roll back**; neither Supervisor nor Filesystem can confer
that authority by invoking their own functions.

Engine startup deliberately adds no application-level identity challenge signed by the same identity that
Noise has already authenticated. Noise mutually proves possession of the two libp2p identities. HPM state
then gives those PeerIds meaning: `procman` pins the expected Engine PeerId to the selected Engine binding,
and Engine authorizes the authenticated `procman` PeerId at the privileged Worker Manager stream. Successful
Noise alone grants no lifecycle or route authority, but repeating its key-possession proof would add no new
fact. Engine readiness is instead the admitted Worker Manager session plus exact registration evidence.

## Authoring and state shapes

### External Covenant locator

A boot, load, or import edge supplies the locator:

```yaml
provider: github
kind: git-tree
repository: dreamcatcher-tech/gateway
ref: main
path: covenant.yaml
credential: github-private-read  # optional logical Vault need
```

Provider examples include `github`, `git`, `local-git`, `file`, `ipfs`, and
`oci-registry`. Kind examples include `git-tree`, `file-tree`, `oci-image`, `oci-artifact`, and
`ipfs-object`. Resolution preserves the provider-native immutable identity. The declared logical
credential name may enter the lock; credential bytes and leases never do.

### Runnable Covenant

```yaml
id: gateway
name: Gateway

hardware:
  cpus: 1
  memory_mb: 512

image:
  provider: oci-registry
  kind: oci-image
  reference: docker.io/example/base@sha256:...
  credential: registry-read  # optional logical Vault need

build: null

mounts:
  common:
    provider: github
    kind: git-tree
    repository: dreamcatcher-tech/common
    ref: main
    access: read-only
    credential: github-private-read

workers:
  gateway:
    manifest: workers/gateway/iii.worker.yaml

exports:
  functions:
    - gateway::llm::responses
```

Mount declarations are flat. `access` defaults to `read-only`. Raw host paths are invalid.
Worker-specific runtime, dependencies, installation, start, and tests stay in each
`iii.worker.yaml`; Chamber-wide hardware, image, build, and mounts stay in the Covenant.

### Assembly Covenant

```yaml
id: core
name: Core assembly

imports:
  filesystem:
    provider: github
    kind: git-tree
    repository: dreamcatcher-tech/filesystem
    ref: main
    path: covenant.yaml
  gateway:
    provider: github
    kind: git-tree
    repository: dreamcatcher-tech/gateway
    ref: main
    path: covenant.yaml
```

For a durable named Assembly lifecycle, the expanded import names become stable logical names with
independent current selections. Import edges and lock closure supply logical topology; lifecycle state
does not duplicate a dependency table. An operation-scoped development child receives exact candidate
custody and Chamber identity without manufacturing another durable logical name; an exact Realization it
produces may later become a candidate for an already authorized durable name.

### Current, candidates, and Chambers

A durable logical name selects one exact current Realization independently of runtime residency.
Candidates are exact Realizations under bounded Holds. Chambers are the only host-local execution
records, and several may refer to the same current or candidate Realization.

```yaml
current:
  gateway:
    revision: 43
    realization: sha256:R18

candidates:
  gateway:
    sha256:R19: hold@sha256:H19
    sha256:R20: hold@sha256:H20

chambers:
  chamber:C42:
    name: gateway
    realization: sha256:R18
    lease: lease@sha256:L42
    phase: ready
  chamber:C43:
    name: gateway
    realization: sha256:R18
    lease: lease@sha256:L43
    phase: ready
  chamber:C50:
    name: gateway
    realization: sha256:R19
    lease: lease@sha256:L50
    phase: ready

operations: {}
```

Realization manifests are retrieved by their content identities; the state above does not repeat lock,
artifact, acceptance, or launch-plan fields. Candidate values contain only a Hold reference. The Hold
transitively binds bounded custody, expiry, and named cleanup authority. Chamber leases transitively bind
run ownership, scope, deadline, resources, and cleanup without copying those fields into lifecycle state.

`current[gateway].realization = R18` remains true if every shown Chamber is reaped. A later call may activate another
fresh Chamber from `R18`. Reaping `C50` does not discard candidate `R19` while `H19` remains valid, and
selecting `R19` does not promote or rename `C50`.

### Removed parallel concepts

- legacy image or generation record -> `Realization`;
- `last/current/next` Chamber-bearing slots -> current selection, candidate Holds, and selection history;
- proposal record -> exact candidate Realization mapped to one Hold reference;
- separate Activation record -> `Chamber`;
- route record -> derived Engine factory or exact-Chamber route;
- attachment table -> lock declaration plus Chamber endpoint observation;
- per-name inline operation -> exact operation intent and terminal receipt;
- duplicated receipt fields -> transitive references to Realization, Hold, lease, and prior evidence.

### Write-ahead operation

```mermaid
stateDiagram-v2
    direction TB
    state "Stable lifecycle state" as Stable
    state "Intent committed" as Intended
    state "Effect in progress" as Applying
    state "Interrupted effect" as Reconcile
    state "Terminal failure" as Failed

    [*] --> Stable
    Stable --> Intended: commit exact operation and expected subject revision
    Intended --> Applying: perform exact physical or Engine effect
    Applying --> Stable: verify, emit terminal receipt, remove operation
    Intended --> Reconcile: interruption
    Applying --> Reconcile: interruption
    Reconcile --> Stable: prove completion or undo residue
    Reconcile --> Intended: retry same fenced operation
    Applying --> Failed: record attributable terminal failure
    Failed --> Stable: authorized repair clears or replaces state
```

## Ordinary Chamber activation kernel

This kernel creates one ordinary, non-Engine Chamber from one already complete Realization. It applies
equally to a current Realization, a candidate under a valid Hold, a fixture, or a retained rollback
target. There is no separate Activation object. Its prerequisites are explicit: the Engine and Filesystem
Service are already ready. Cold Engine activation follows **Engine cold start**, and the first Filesystem Service activation
uses the core-bootstrap path below because neither service can depend on an I3 Filesystem route that does
not yet exist.

`entry = ready Engine + ready Filesystem Service + exact realization + current revision or candidate Hold + registration contract + authorized Chamber lease`

`exit = ready fresh Chamber + run receipt, or no live Chamber + terminal failure receipt`

The diagram includes the outer Supervisor proposal so its first step is the reason for activation rather
than an unexplained storage read. `procman` then commits the exact Chamber intent before any physical effect.

```mermaid
sequenceDiagram
    autonumber
    participant procman
    participant Materializer as Image Materializer
    participant containerd
    participant Runtime as Trusted host runtime (runsc)
    participant Engine as Engine
    participant Supervisor
    participant Chamber as New Chamber
    participant Filesystem as Filesystem Service
    participant Vault

    Supervisor->>procman: `chambers::process::propose`
    Note over procman: Commit Chamber intent and admissions[lease]<br/>before physical effects
    Note over procman: Bind the fresh Chamber ID and PeerId to the exact Realization<br/>and registration contract, plus listener, epoch, profile, and expiry
    loop Each exact lifecycle object named by the Realization
        procman->>Filesystem: `filesystem::object::read`
    end
    Note over procman,Filesystem: Read the Realization manifest, accepted boot artifact,<br/>and declared immutable mount objects by exact digest only

    alt Every exact byte is available
        procman->>Materializer: `materialize_image`
        Materializer->>containerd: `inspect_image`
        alt Exact manifest, content, and unpacked snapshot are verified locally
            Note over Materializer,containerd: Reuse the derivative cache only by exact digest,<br/>a local image name or tag is never authority
        else No complete verified materialization exists
            Note over procman,Materializer: Supply only the sealed read-only OCI capability<br/>for the exact manifest, config, and layers
            Materializer->>containerd: `import_image`
            Materializer->>containerd: `unpack_image`
        end
        Note over procman,Materializer: Continue only with the exact materialization receipt
        procman->>Runtime: `activate_chamber`
        Note over Runtime,Chamber: Create/start the new Chamber from that exact<br/>materialization through pinned runsc
        Note over procman,Chamber: Inject the fresh private identity by protected capability<br/>and pass the pinned Engine PeerId
        Note over Chamber,Engine: TCP plus Noise authenticates the Chamber PeerId<br/>and the pinned Engine PeerId while proving key possession only
        Note over Engine: Reject an unknown, expired, wrong-listener,<br/>wrong-epoch, or revoked PeerId before stream open
        alt Admission profile is privileged-direct
            Note over Engine: Enable the trusted control-plane middleware class<br/>while retaining prefix and contract gates
        else Admission profile is ordinary-rbac
            Note over Engine,Vault: Derive the ordinary RBAC principal from the admitted PeerId<br/>and retain Vault middleware on mediated calls
        end
        Note over Chamber,Engine: Open /dreamcatcher/i3-worker-manager/noise/1.0.0<br/>only after admission, then submit local registrations
        Note over Engine: Assign the chamber::Chamber-ID prefix and quarantine registrations<br/>while comparing the complete set with the registration contract
        alt Admission binding and exact complete set match while the lease is live
            Note over Engine: Atomically publish only the prefixed exact set<br/>and issue registration-complete evidence
            procman->>Engine: `engine::route::inspect`
            Note over procman: Mark ready and emit the run receipt<br/>only after exact route evidence
        else Identity, lease, profile, or registration contract fails
            Note over Engine: Close the stream and publish nothing<br/>while preserving unrelated router state
            procman->>Runtime: `stop_chamber`
            Note over Runtime,Chamber: Stop and reap the failed exact Chamber
            Note over procman: Revoke admission, emit a terminal failure receipt,<br/>and preserve unrelated lifecycle state
        end
    else Any exact byte remains unavailable
        Note over procman: Remove non-live state, emit the failure receipt, and terminalize the operation
    end
```

The Filesystem Service is the single Chamber-facing storage boundary. Provider adapters and N3/GraphFS or
other content-addressed backing stores sit behind it; they are not extra lifecycle actors in this diagram.
`filesystem::object::read` does not discover a version, read a mutable workspace, or build anything. It
retrieves only the immutable Realization manifest and exact accepted artifact or mount objects already named
by that manifest.

The Noise connection itself is never the admission result. A remote connection-gater close can propagate
after a dial appears to complete, so the fail-closed invariant is that an unauthorized PeerId cannot open
the Worker Manager protocol stream. The Engine checks the HPM projection both when the secure connection
identifies the remote PeerId and when that peer requests the protocol. A claimed Chamber ID in a worker
payload is never authority: from the authenticated PeerId, the server looks up the exact Chamber ID,
Realization, registration contract, lease, epoch, listener, and profile committed by HPM.

The private identity is fresh per physical Chamber lease, is never baked into an image or ordinary
environment variable, and is destroyed with the Chamber. Reconnects by the same live Chamber reuse that
lease identity; a replacement Chamber receives a fresh Chamber id and PeerId. An Engine replacement must
present a newly HPM-authorized pinned identity; existing Chambers remain fenced until `procman` supplies an
authorized listener update or replaces them. No peer may silently accept an arbitrary replacement key.

Privileged-direct is an explicit HPM admission profile for the Engine bootstrap and named trusted
control-plane subjects. It bypasses ordinary application RBAC middleware only; it does not bypass PeerId
admission, server-assigned prefixing, the immutable registration contract, complete-set validation, lease
revocation, or router publication gates. Ordinary Chambers receive the ordinary-RBAC profile.

This Chamber-to-Engine boundary is the intended reusable shape for a later upgrade of ordinary Ark-to-Ark
RBAC handshakes: secure-transport key possession followed by an explicit authorization contract. That
cross-Ark migration is deferred; existing Ark-to-Ark RBAC behavior is not changed by this sequence.

The kernel may fetch or import bytes already named by the Realization. It may not resolve a moving
locator, choose dependencies, execute a build from the Covenant lock, or substitute another digest.
Any attempt starting only from a Covenant lock enters **Form and activate a candidate**, even when it hopes
to reproduce a former artifact. A result with a different digest is necessarily a different
Realization; a byte-identical result is still observed and admitted through the candidate path before
it may satisfy current selection.

The current revision or candidate Hold is captured when the Chamber intent commits. A concurrent
selection change never relabels that Chamber. The selected Realization may have no Chamber before or
after this kernel.

## Overall lifecycle

```mermaid
stateDiagram-v2
    direction TB
    state "Engine wake" as Wake
    state "Basic Ark: Engine + Filesystem + Supervisor" as Basic
    state "On-demand operation" as Normal
    state "Fenced development" as Develop
    state "Form exact candidate" as Realize
    state "Verify candidate" as Verify
    state "Select or roll back" as Select
    state "No resident Chambers" as Quiescent

    [*] --> Wake
    Wake --> Basic: Engine ready, then restore core services
    Basic --> Normal: basic Ark routes ready
    Normal --> Develop: mutate named resource
    Develop --> Realize: seal exact source revision
    Normal --> Realize: resolve locator or realize from lock
    Realize --> Verify: exact candidate and Hold ready
    Verify --> Select: MET and selection authorized
    Verify --> Normal: reject, expire, or retain candidate
    Select --> Normal: current compare-and-swap completed
    Normal --> Quiescent: reap every idle Chamber
    Quiescent --> Wake: authenticated host wake
    Normal --> Wake: Engine/runtime discontinuity
```

## Engine cold start

`entry = running procman + boot-readable current selections and exact Engine custody`

`exit = one ready Engine Chamber for admitted wake work`; no other current Realization must be resident.

`host activation != first-pair acceptance`; every initial selected Realization is already authorized by
its accepted bootstrap profile and external selection fence.

This cold Engine sequence begins at an already-running `procman`. Starting or replacing `procman` belongs
to an explicitly lower platform and remains outside this lifecycle. The first in-scope event is an
authenticated `wake_engine` call reaching that process.

```mermaid
sequenceDiagram
    autonumber
    participant procman
    participant Materializer as Image Materializer
    participant containerd
    participant Runtime as Trusted host runtime (runsc)
    participant Engine
    participant Boot as Boot Store
    actor Wake as Wake Source

    Wake->>procman: `wake_engine`
    Note over procman: Authenticate the lower wake, reconcile interrupted operations,<br/>and inspect ready Engine Chambers

    opt No Engine Chamber is ready
        Note over procman: Read current[engine] and commit a fresh Engine Chamber intent
        Note over procman,Boot: Use only the selected accepted Engine Realization<br/>and exact boot artifact already held in Boot Store
        Note over procman: Commit the fresh Engine Chamber, PeerId, Realization,<br/>listener, lease, and epoch binding before launch
        procman->>Materializer: `materialize_image`
        Materializer->>containerd: `inspect_image`
        alt Exact manifest, content, and unpacked snapshot are verified locally
            Note over Materializer,containerd: Reuse the derivative cache only by exact digest,<br/>a local image name or tag is never authority
        else No complete verified materialization exists
            Note over Materializer,Boot: Consume the sealed authoritative Engine OCI content<br/>through its read-only boot capability
            Materializer->>containerd: `import_image`
            Materializer->>containerd: `unpack_image`
        end
        Note over procman,Materializer: Continue only with the exact materialization receipt
        procman->>Runtime: `activate_chamber`
        Note over Runtime,Engine: Create/start the new Engine Chamber from that exact<br/>materialization through pinned runsc
    end

    Note over procman,Engine: Establish TCP plus Noise with both expected PeerIds pinned
    Note over procman: Accept only the Engine PeerId bound by HPM<br/>to current[engine] and this live Engine Chamber
    Note over Engine: Authorize the authenticated procman PeerId<br/>for the privileged Worker Manager stream
    Note over procman,Engine: Open the admitted Worker Manager session,<br/>then procman registers its two public functions through the I3 SDK
    procman->>Engine: `engine::wake::deliver`
```

Physical Engine creation is therefore the single conditional step: an already-ready Engine skips it, while
a missing Engine takes the `activate_chamber` branch. Both paths converge on the same mutually authenticated
Noise session and HPM authorization. There is no second same-key challenge-response ceremony.

If admitted wake work needs another selected Runnable, the ready Engine invokes
`chambers::process::propose`; that target then follows the ordinary Chamber activation kernel above.

No Chamber is architecturally required to run continuously. Policy may keep an Engine Chamber or other
working set warm, but `current` selection survives with zero Chambers. `procman` is not a Chamber; it is
the mechanism-only host wake boundary. If `procman` itself is stopped, an explicitly lower platform,
cloud control plane, or physical operator must wake it—this lifecycle does not hide that recursion.

The irreducible cold edge is `wake source -> procman -> selected Engine Realization`. A worker attached to a
running Engine or an authorized Supervisor Chamber may request ordinary Chamber activation, but it
cannot be the only mechanism that wakes the absent Engine containing it. `procman` may execute the exact pre-authorized
wake; it does not select a different Engine Realization or decide application policy.

First acceptance of the host envelope and Engine/Supervisor bootstrap subjects remains an external
verification and selection ceremony. Engine cold start never forms a Realization from a Covenant lock and never
certifies its own seed.

## Bootstrap core services

This is the bridge from a ready Engine to the smallest useful Ark service set. It makes the bootstrap
exception explicit instead of letting ordinary activation appear to assume a Filesystem Service from
nowhere. The accepted bootstrap plan names the exact Filesystem Service and Supervisor Realizations;
`procman` executes that plan but does not choose replacements.

`entry = ready Engine + authenticated wake operation + accepted bootstrap plan + exact core-service custody`

`exit = ready Engine + ready Filesystem Service + ready Supervisor`

The first Filesystem Service image is available through Boot Store because no Filesystem I3 route exists
yet. Once that Chamber is ready, the Supervisor follows the normal exact-object path through the
Filesystem Service. This exit is the basic Ark state assumed by ordinary Chamber activation and fenced
development.

```mermaid
sequenceDiagram
    autonumber
    participant procman
    participant Materializer as Image Materializer
    participant containerd
    participant Runtime as Trusted host runtime (runsc)
    participant Engine
    participant Supervisor
    participant Filesystem as Filesystem Service
    participant Boot as Boot Store

    Note over procman: Continue the authenticated wake operation<br/>under the accepted bootstrap plan

    opt No Filesystem Service Chamber is ready
        Note over procman: Commit the exact Filesystem Chamber intent and<br/>PeerId admission before physical effects
        Note over procman,Boot: Use only the selected accepted Filesystem Realization<br/>and sealed OCI content held in Boot Store
        procman->>Materializer: `materialize_image`
        Materializer->>containerd: `inspect_image`
        alt Exact manifest, content, and unpacked snapshot are verified locally
            Note over Materializer,containerd: Reuse the derivative cache only by exact digest
        else No complete verified materialization exists
            Note over Materializer,Boot: Consume the sealed authoritative OCI content<br/>through its read-only boot capability
            Materializer->>containerd: `import_image`
            Materializer->>containerd: `unpack_image`
        end
        procman->>Runtime: `activate_chamber`
        Note over Runtime,Filesystem: Create/start the Filesystem Service Chamber<br/>through pinned runsc
        Note over Filesystem,Engine: Complete Noise admission and exact registration publication
        procman->>Engine: `engine::route::inspect`
    end

    opt No Supervisor Chamber is ready
        Note over procman: Commit the exact Supervisor Chamber intent and<br/>PeerId admission before physical effects
        loop Each exact lifecycle object named by the Supervisor Realization
            procman->>Filesystem: `filesystem::object::read`
        end
        procman->>Materializer: `materialize_image`
        Note over Materializer,containerd: Apply the same exact-digest inspect,<br/>import-if-missing, and unpack kernel
        procman->>Runtime: `activate_chamber`
        Note over Runtime,Supervisor: Create/start the Supervisor Chamber<br/>through pinned runsc
        Note over Supervisor,Engine: Complete Noise admission and exact registration publication
        procman->>Engine: `engine::route::inspect`
    end

    Note over Engine,Filesystem: Engine and Filesystem routes are ready
    Note over Engine,Supervisor: Supervisor may now propose ordinary lifecycle work
```

The bootstrap profile is narrow: it can restore only the externally accepted exact core set. It cannot
resolve a moving locator, build an image, select another Realization, or become a general application
policy path.

## Form and activate a candidate

`entry = authorized caller + durable logical name + locator or exact Covenant lock + candidate quota`

`exit = exact candidate Realization + bounded Hold + optional ready Chamber`

Several candidates may coexist for one logical name. This mode never changes `current`; it only forms
an exact Realization, establishes bounded custody, and optionally creates a Chamber for inspection.

```mermaid
sequenceDiagram
    autonumber
    participant procman
    participant Supervisor
    participant Candidate
    participant Builder
    participant Filesystem as Filesystem Service
    participant Acceptor
    actor Caller

    Caller->>Supervisor: `chamber::covenant::load`
    Note over Supervisor: Validate authority, parentage, candidate capacity, quota, and deadline

    alt Caller supplied a moving locator
        Supervisor->>Filesystem: `resource::resolve`
        Note over Filesystem: Acquire any scoped Vault lease and invoke the selected provider adapter
        Note over Supervisor: Form the exact Covenant lock
    else Caller supplied an exact Covenant lock
        Supervisor->>Filesystem: `resource::resolve`
    end

    alt Lock names an already accepted exact artifact
        Note over Supervisor: Verify the artifact descriptor and acceptance receipt
    else Realization requires an artifact build
        Supervisor->>Builder: `artifact::build`
        Supervisor->>Acceptor: `artifact::accept`
    end

    Note over Supervisor: Form and digest the complete immutable Realization
    Supervisor->>Filesystem: `filesystem::hold::acquire`
    Supervisor->>procman: `chambers::process::propose`

    opt Inspection or verification needs a running instance
        Supervisor->>procman: `chambers::process::propose`
        Note over procman,Candidate: Apply the ordinary activation kernel to materialize,<br/>start, admit, and prove the exact candidate Chamber
    end

```

A moving locator is resolved only while forming the lock. Re-resolving `main` later may produce another
lock and another candidate; it never mutates `current`. Candidate admission deduplicates the same
Realization identity rather than inventing another proposal record.

Starting with only a Covenant lock always follows this mode. Builds are not assumed reproducible: the
same lock may yield a different artifact and therefore a different Realization. Even when a build later
produces the same digest, its custody and evidence are admitted through the candidate path before any
selection decision. Rejection, missing Builder support, or missing exact bytes fails closed without
changing current selection.

## Fenced development

`mutable object = named Filesystem workspace`

`developer execution = one leased Chamber from an exact development Realization`

`immutable handoff = exact resource snapshot`

The Developer Chamber is ordinary execution state: it is activated from an exact development
Realization under a lease and addressed by exact Chamber identity. It terminates and is reaped. Any
immutable product it creates may enter a target lifecycle as a candidate, but the Developer Chamber
itself is never promoted.

```mermaid
sequenceDiagram
    autonumber
    participant procman
    participant Runtime as Trusted host runtime (runsc)
    participant Supervisor
    participant Developer
    participant Filesystem as Filesystem Service
    participant Agent

    Agent->>Supervisor: `chamber::workspace::materialize`
    Supervisor->>Filesystem: `resource::workspace::open`
    Supervisor->>procman: `chambers::process::propose`
    Note over procman,Developer: Stage the fenced attachment in the exact activation plan and expose no host path
    Note over procman,Developer: Apply the ordinary activation kernel only after attachment staging<br/>is durable, then return exact readiness evidence
    Agent->>Filesystem: `resource::workspace::edit`

    alt Continue development
        Agent->>Filesystem: `resource::workspace::renew`
    else Seal an exact revision
        Agent->>Filesystem: `resource::snapshot`
        opt Publish a provider-native revision
            Agent->>Filesystem: `resource::commit`
        end
    else Close or expire
        Supervisor->>procman: `chambers::process::propose`
        procman->>Runtime: `stop_chamber`
        Note over Runtime,Developer: Stop and reap the exact Developer Chamber
        Supervisor->>Filesystem: `resource::workspace::close`
    end
```

Workspace, snapshot, provider revision, Realization, and Chamber remain distinct identities. The
snapshot or provider revision becomes an input to a later lock; development never captures a
running root filesystem. If that output is later proposed for a durable logical name, it enters
**Form and activate a candidate**,
forms an exact candidate Realization under a Hold, and may be selected only after verification. No
workspace or Chamber is renamed into the candidate or current Realization.

## Build an artifact

Status: **Optional later implementation; not required by the first mount-first lifecycle.**

`build = exact request -> exact OCI artifact + build receipt`

`build output != running Builder filesystem`

`build receipt != acceptance receipt`

```mermaid
sequenceDiagram
    autonumber
    participant Supervisor
    participant Builder
    participant Filesystem as Filesystem Service

    Supervisor->>Builder: `artifact::build`
    Builder->>Filesystem: `resource::resolve`
    Note over Builder: Execute the selected frontend without runtime-socket authority
    Builder->>Filesystem: `image::seal`
    Note over Filesystem: Verify and atomically seal the manifest, config, layers, and receipt
```

`containerd` is intentionally absent from this build diagram. The Builder assembles the authoritative OCI
manifest, config, and layers in the Filesystem Service's content-addressed custody and receives no runtime
socket. Only a later activation asks the host Image Materializer to inspect or import those sealed bytes
into disposable `containerd` state before launch.

The first Builder version needs only exact inputs, an exact output digest, builder identity, and a
signed basic receipt. This sequence ends here. Artifact acceptance, Realization formation, and candidate Hold
creation belong exclusively to **Form and activate a candidate**. A build result is never installed as `current` merely because
its request used the current Covenant lock. The build request is provider-neutral; Dockerfile,
BuildKit, or another build language is an adapter rather than core Covenant syntax. The stronger
multi-Ark attestation flow below is a further deliberately deferred mode.

## Attested multi-Ark builds (later)

Status: **Later implementation; not required by the initial lifecycle.**

`mechanical provenance != software quality`

`independent convergence on one digest = stronger reproducibility evidence`

```mermaid
sequenceDiagram
    autonumber
    participant BuilderA as Builder A
    participant BuilderB as Builder B
    participant CAS as Artifact Store
    participant Attestation as Attestor
    participant Inspectors
    participant Acceptor
    actor Requester
    Requester->>BuilderA: `artifact::build`
    Requester->>BuilderB: `artifact::build`

    par Independent build A
        Note over BuilderA: Build inside the measured confidential environment
        BuilderA->>CAS: `image::seal`
        BuilderA->>Attestation: `attestation::verify`
    and Independent build B
        Note over BuilderB: Build inside the measured confidential environment
        BuilderB->>CAS: `image::seal`
        BuilderB->>Attestation: `attestation::verify`
    end

    Requester->>Inspectors: `verification::invoke`
    Inspectors->>CAS: `resource::resolve`
    Note over Inspectors: Test, inspect, and emit signed evidence over exact subjects

    Requester->>Acceptor: `artifact::accept`
    alt Builders converge on one digest
        Note over Acceptor: Evaluate the common artifact, attestations, inspections, and policy
    else Builders produce different digests
        Note over Acceptor: Select one exact artifact or accept none
    end
```

A Merkle root can commit to undisclosed builder software and evidence, but the root alone proves
no quality claim. Verification still needs accepted measurements, selective proofs, or another
named appraisal policy. The accepted artifact and every differing output produce distinct
realizations.

## Verify a candidate

`verdict subject = exact candidate Realization + exact Chamber + exact plan + environment`

`verdict != selection`

```mermaid
sequenceDiagram
    autonumber
    participant procman
    participant Runtime as Trusted host runtime (runsc)
    participant Engine
    participant Supervisor
    participant Candidate
    participant Fixtures
    participant Filesystem as Filesystem Service
    participant Verifier
    actor Requester

    Requester->>Verifier: `verification::invoke`
    Verifier->>Supervisor: `chamber::version::candidate_event`
    Supervisor->>procman: `chambers::process::propose`
    Note over procman,Candidate: Apply the ordinary activation kernel for the exact candidate
    Note over Candidate,Engine: Candidate registers its declared verification route through the I3 SDK
    procman->>Engine: `engine::route::inspect`

    opt Declared fixtures are required
        Supervisor->>procman: `chambers::process::propose`
        Note over procman,Fixtures: Apply the ordinary activation kernel for the exact fixtures
        Note over Fixtures,Engine: Fixtures register their exact routes through the I3 SDK
        procman->>Engine: `engine::route::inspect`
    end

    Verifier->>procman: `chambers::process::inspect`

    Verifier->>Candidate: `verification::invoke`
    opt Declared fixtures were activated
        Verifier->>Fixtures: `verification::invoke`
    end
    Note over Verifier: Emit MET, NOT_MET, or UNKNOWN bound to exact identities
    Verifier->>Supervisor: `chamber::version::candidate_event`

    Supervisor->>procman: `chambers::process::propose`
    procman->>Runtime: `stop_chamber`
    Note over Runtime,Candidate: Stop and reap the exact candidate Chamber
    opt Declared fixtures were activated
        procman->>Runtime: `stop_chamber`
        Note over Runtime,Fixtures: Stop and reap the exact fixture Chambers
    end

    opt Verdict rejects, expires, or cancels the candidate
        Supervisor->>procman: `chambers::process::propose`
        procman->>Filesystem: `filesystem::hold::release`
    end

```

A MET verdict permits a later selection request while its Hold remains valid; it does not require the
verification Chamber to remain alive. Further verification attempts create further Chambers of the same
candidate Realization and produce independently scoped evidence.

The first Tester is judged by the external bootstrap verifier. Once separately selected, the current
Tester Realization normally supplies an on-demand Tester Chamber for other Covenants. Tester never
writes current selection.

## Select or roll back

`selection authority = gate-appropriate fenced promoter`

`selection effect = one compare-and-swap of current[name] + derived Engine factory revision`

`entry = exact candidate Realization + valid Hold + fresh gate evidence + expected current revision`

```mermaid
sequenceDiagram
    autonumber
    participant procman
    participant Engine
    participant Supervisor
    participant Filesystem as Filesystem Service
    participant Verifier
    participant Promoter

    Verifier->>Supervisor: `chamber::version::candidate_event`
    Supervisor->>Promoter: `selection::authorize`
    Promoter->>procman: `chambers::process::inspect`
    Promoter->>procman: `chambers::process::propose`

    Note over procman: Commit the selection operation with exact before and after values
    procman->>Engine: `engine::route::fence`

    alt Expected current revision or Hold is stale
        Note over procman: Emit a failed-selection receipt without changing current
        procman->>Engine: `engine::route::reopen`
    else Exact compare-and-swap succeeds
        Note over procman: Set current[name] to the candidate Realization at the next revision
        procman->>Filesystem: `filesystem::hold::transfer`
        procman->>Engine: `engine::route::install`
        Note over procman: Emit the selection receipt and terminalize the operation
    end

```

Selection never moves, adopts, or renames a Chamber. A Chamber that supplied verification evidence may
already be gone. Chambers of the prior current Realization remain pinned to it until their independent
leases complete, cancel, expire, or are explicitly drained. Only calls admitted after the new current
revision activate the newly selected Realization.

`current` is defined only by the authoritative selection record. It is never inferred from newest
creation, latest health, fleet majority, a ready Chamber, or route-cache contents. A failure to activate
the selected Realization fails that execution; it does not silently select another one.

Supervisor replacement uses the same sequence; `supervisor` is only another logical name. Authority is
bound to the selected Supervisor Realization and attenuated capabilities granted to its Chambers, not to
one immortal Supervisor Chamber.

Rollback uses this same selection operation with a retained accepted Realization as target. Selection
history can identify a prior target but cannot make its artifact available. Without exact retained bytes,
a valid Hold, required evidence, and authorization, rollback fails closed.

## Quiesce and wake

`quiescence preserves current selections, candidate Holds, receipts, and durable resources—not Chambers`

`wake = Engine cold start`

```mermaid
sequenceDiagram
    autonumber
    participant procman
    participant Runtime as Trusted host runtime (runsc)
    participant Engine
    participant Supervisor
    participant Members as Chambers
    participant Filesystem as Filesystem Service
    actor Requester

    Requester->>Supervisor: `chamber::quiesce`
    Supervisor->>procman: `chambers::process::propose`
    Note over procman: Commit the quiesce operation before stopping Chambers
    procman->>Engine: `engine::quiescence::plan`

    loop Dependants before providers
        procman->>Engine: `engine::quiescence::chamber`
        procman->>Runtime: `stop_chamber`
        Note over Runtime,Members: Stop and reap each exact dependant Chamber
    end

    procman->>Filesystem: `filesystem::resources::flush`
    procman->>Runtime: `stop_chamber`
    Note over Runtime,Supervisor: Stop and reap the exact Supervisor Chamber
    procman->>Runtime: `stop_chamber`
    Note over Runtime,Filesystem: Stop and reap the exact Filesystem Chamber
    procman->>Runtime: `stop_chamber`
    Note over Runtime,Engine: Stop and reap the exact Engine Chamber last
    Note over procman: Persist the terminal receipt while current and candidate state remain unchanged
    procman->>Requester: `deliver_final_reply`
```

`filesystem::resources::flush` is the only Filesystem durability barrier in this sequence. It covers
the exact resource set named by the committed stop operation and returns operation-bound receipts; it
is not an unscoped service drain. Every other Filesystem operation must already complete at the
durability boundary promised by its own contract. Once the exact resource receipts are durable and no
Filesystem invocation remains active or queued, `procman` may stop the Filesystem Chamber directly;
there is no additional generic Filesystem flush.

The same rule supports ordinary idle reaping without a global quiesce: `procman` may stop any independently
idle Chamber whose lease and work state permit it. Reaping the final Engine Chamber leaves `procman` waiting
on its authenticated wake edge; the next event follows **Engine cold start**. If policy also stops `procman`, the reply and
wake obligation must first transfer to an explicitly lower layer.

A hard deadline may discard unflushed Chamber-local state. It creates no alternate artifact,
Realization, or process-memory identity and never changes `current` merely because a Chamber stopped.

## Failure and recovery formulas

- `operation remains non-terminal after interruption -> reconcile that exact operation before conflicting work`.
- `current[name] = R + zero Chambers -> valid idle state`; do nothing until demand or explicit prewarm policy.
- `admitted call snapshots current revision S and Realization R -> its Chamber remains pinned to (S, R)` even if
  selection changes before physical start completes.
- `ready Chamber fails -> terminalize its exact lease and receipt`; retry, if authorized, creates a fresh
  Chamber of the same Realization without changing current.
- `Chamber lease expires or work terminates -> stop and reap that Chamber`; sibling Chambers and current are unchanged.
- `Engine Chamber absent + authenticated wake -> procman activates exact current[engine] through Engine cold start`.
- `candidate Hold expires -> reap its candidate Chambers + remove candidates[name][R] + emit cleanup receipt`,
  unless another current, candidate, or operation reference still retains the exact bytes.
- `exact artifact unavailable -> activation fails`; do not build from the lock inside the activation kernel.
- `build starts from a Covenant lock -> output enters candidate formation`, never directly as current.
- `lock-only rebuild reproduces the complete current Realization identity -> verify candidate + perform fenced
  idempotent selection/custody confirmation before using the rebuilt bytes as current`.
- `lock-only rebuild produces a different artifact or Realization digest -> distinct candidate`; only the fenced selection sequence may select it.
- `provider credential unavailable -> resolution or build fails closed`; current is unchanged.
- `Engine route cache disagrees with current selection or authoritative Chamber state -> lifecycle state wins`;
  fence affected admission and rebuild the cache.
- `Noise authenticates a PeerId not present in a live admissions[lease], or the Engine pin is wrong -> no
  Worker Manager protocol stream`; publish no registration and leave the router unchanged.
- `admitted PeerId claims another Chamber or submits a non-exact registration set -> close the stream +
  revoke or fail the activation`; the quarantined set never becomes routable.
- `admission expires or is revoked -> reject new Worker Manager streams + close live registration authority`;
  a replacement Chamber requires a fresh Chamber id, lease, epoch, and PeerId.
- `physical id survives but cannot be proved -> reap it and create a fresh Chamber`.
- `verifier unavailable or verdict UNKNOWN -> no selection`.
- `stale current revision, Hold, lease, operation subject, or selection permit -> reject before effect`.
- `cleanup names exact Chamber ids and candidate Holds`; unrelated candidates and sibling Chambers are unaffected.
- `history preserves receipts, not artifact availability`; rollback needs retained exact custody.
- `procman unavailable -> only an explicitly lower platform may wake or replace it`; no Chamber can bootstrap its own absent procman.

## Implementation handoff

### Initial lifecycle

- external provider-specific Covenant locators with optional logical credential names;
- location-independent Covenants with top-level `hardware`, `image`, optional `build`, flat
  `mounts`, and plural `workers`;
- exact Covenant locks and content-addressed, immediately launchable Realization manifests;
- `current[name] = {revision, realization}` as the only stable named selection;
- `candidates[name][realization] = Hold reference` with several bounded candidates permitted;
- `chambers[id] = {name, realization, lease, phase}` with independent operations and cleanup;
- no separate Activation record and no Chamber-bearing `last/current/next` slots;
- a `procman`-owned Engine wake edge plus Engine-native activation factories for ordinary selected names;
- an explicit basic-state bootstrap from ready Engine to ready Filesystem Service and Supervisor, with only
  the first Filesystem Service allowed to consume externally accepted boot custody before its I3 route exists;
- a mechanism-only Image Materializer as the sole holder of the `containerd` socket, exact-digest
  inspect/import/unpack branches, and `containerd` state treated only as reconstructable derivative cache;
- explicit `procman -> trusted host runtime` conventional calls for exact Chamber create/start and stop/reap
  effects, with the Chamber represented as the subject rather than a receiver that could exist before start;
- exact-Chamber routes for execution, verification, and cleanup;
- a `procman`-owned durable lease admission binding from fresh Chamber PeerId to exact Chamber,
  Realization, registration contract, Engine listener, epoch, profile, and expiry;
- a Noise-authenticated Worker Manager protocol whose stream gate precedes registration, with
  server-assigned `chamber::<Chamber id>` prefixes and atomic complete-set publication;
- no redundant application identity challenge after Noise; expected PeerId pinning plus HPM admission and
  registration evidence establish the Engine/Chamber meaning and readiness needed by lifecycle calls;
- explicit privileged-direct and ordinary-RBAC admission profiles, both preserving lifecycle and
  registration-contract enforcement;
- fresh zero-to-many Chambers per Realization, with current remaining valid at zero residency;
- activation only from a complete exact Realization, never from a Covenant lock alone;
- lock-only realization, rebuild, and development outputs entering the candidate path before selection;
- minimal run, selection, and cleanup receipts that reference prior identities and evidence rather than
  copying their fields;
- idle Chamber reaping that does not mutate current or candidate state.

### Deliberately later

- provider-neutral build execution and basic exact-output build receipts;
- multi-Ark confidential Builder attestations, independent inspection, and collective acceptance;
- shared reusable Chamber pools, prewarm controllers, and service traffic balancing;
- lower-platform automation that also stops and wakes `procman`;
- hot dual-Engine migration;
- process-memory or rootfs checkpoint recovery.
- migration of ordinary Ark-to-Ark RBAC handshakes to the reusable Noise-plus-authorization-contract
  boundary established here.

### Required downstream reconciliation to this sequence authority

- cross-stack architecture vocabulary and narrative;
- Covenant owner schema and Gherkin (`source`, singular `worker`, and `worker.resources` are old);
- Chambers owner process-tree, routing, image-construction, activation, verification, and upgrade
  Gherkin;
- Chambers' legacy HMAC Engine-attestation companion, manifests, and startup contract, which must migrate
  to the Noise-authenticated and HPM-authorized Worker Manager boundary rather than coexist with it;
- I3 Engine router/first-host-worker contract, including pinned Engine and `procman` PeerIds;
- Filesystem/provider and Vault credential-need contracts;
- generated traceability after its authoritative inputs change.
