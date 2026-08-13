# Visual DAG

## Status legend

- **Green double-border** — implemented prerequisite on current `main`; reusable input,
  not completion of a new node.
- **Blue** — tournament and plan complete in this bundle.
- **Gray** — planned implementation node, not started.
- **Orange hexagon** — fail-closed gate or independent court.
- **Purple** — generated private human/Obsidian-compatible view.
- **Teal** — approved local shared-learning surface.
- **Red dashed** — deferred, rejected, or quarantined behavior outside this plan.

Every implementation node below has status `not_started`. The prior 39-node DAG being
complete does not complete these new contracts.

## Full implementation DAG

```mermaid
flowchart TB
  subgraph E["Existing current-main foundations — implemented, partial inputs"]
    E1[["Append-only kernel event spine"]]
    E2[["Bounded memory + supersession/conflict"]]
    E3[["Court + evidence-bound lessons"]]
    E4[["Champion/challenger evaluation + rollback"]]
    E5[["JSON/HTML operational projection"]]
  end

  T["Tournament + sealed 31-node plan\nCOMPLETE"]
  B{"BASELINE-000\nsealed baseline gate"}
  S["SOURCE-010\nsource/store truth"]
  A["AUTHORITY-020\nauthority prerequisites"]
  L["LEARNING-030\ninert lesson admission"]
  SC["SCAFFOLD-040\nowned scaffolds"]
  C["CLASSIFY-050\nprivacy/IP/license policy"]
  I["IDENTITY-100\nportable stable identity"]
  ID["IDEA-110\nIdea + immutable IdeaPass"]
  CV["COVERAGE-120\nroles/courts/lifecycle map"]
  PC["PROJECT-CONTRACT-130\ntransactional projection"]
  RC["RELEASE-CONTRACT-140\nallowlisted shared schema"]
  AD["ADVERSARY-150\ndisclosure/poison corpus"]
  OS{"OBSIDIAN-SOURCE-160\nofficial compatibility evidence"}
  RET{"RETENTION-170\ndeletion/takedown contract"}
  ST["STORE-200\ncanonical private store"]
  IR["IDEA-RUNTIME-210\nencounter/pass/re-entry"]
  GA["GRAPH-ADAPTERS-220\nall roles/courts/work/outcomes"]
  PP["PRIVATE-PROJECTOR-230\none-shot external projector"]
  RCB["RELEASE-CANDIDATE-240\nnewly composed abstraction"]
  OV["OBSIDIAN-VIEWS-300\nprivate notes + links + views"]
  TR["TRACE-310\nwhy it went backward"]
  RG{"RELEASE-GATE-320\noffline independent gate"}
  SR["SHARED-REGISTRY-330\nlocal sanitized registry"]
  CLI["CLI-340\nbounded commands"]
  PA["PRIOR-ART-400\nread-only Explorer/Optimizer lookup"]
  F["FEDERATION-410\ntenant + self-host isolation"]
  M["MIGRATION-420\nbackfill/backup/restore/rollback"]
  D["DASHBOARDS-430\nstatus, roles, gates, maturity"]
  Q{"QUALIFY-500\nend-to-end adversarial gate"}
  J{"RELEASE-COURT-510\ndistinct local-release Judge"}
  H["HANDOFF-520\nbounded local product"]

  E1 & E2 & E3 & E4 & E5 --> T
  T --> B --> S
  S --> A & L & SC
  A & SC --> C
  A & SC --> I
  I & L --> ID
  I --> CV
  C & I --> PC
  C & I & L --> RC
  RC --> AD
  S & SC --> OS
  C & I --> RET
  A & I & CV & RET --> ST
  ID & L & ST --> IR
  CV & L & ST --> GA
  C & PC & ST --> PP
  C & RC & ST --> RCB
  GA & IR & OS & PP --> OV
  GA & IR & ST --> TR
  AD & A & L & RCB --> RG
  RG --> SR
  OV & SR & TR --> CLI
  IR & SR --> PA
  C & OV & SR --> F
  PP & SR & ST --> M
  OV & PA & TR --> D
  AD & CLI & PA & F & M & D --> Q
  Q --> J --> H

  X1["Remote/public registry write\nQUARANTINED"]
  X2["Shared lesson auto-activates challenger\nQUARANTINED"]
  X3["Obsidian Inbox / watcher / plugins\nDEFERRED"]
  X4["Wholesale Phase 3 merge\nREJECTED"]
  X5["Markdown or Obsidian is authority\nREJECTED"]
  H -. "requires a new court + authority" .-> X1
  SR -. "never automatic" .-> X2
  OV -. "future program" .-> X3
  E1 -. "adapt patterns only" .-> X4
  ST -. "views rebuild from here" .-> X5

  classDef implemented fill:#d9f2df,stroke:#238636,stroke-width:3px,color:#102a17;
  classDef complete fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#102a43;
  classDef planned fill:#f3f4f6,stroke:#6b7280,stroke-width:1px,color:#111827;
  classDef gate fill:#ffedd5,stroke:#c2410c,stroke-width:2px,color:#431407;
  classDef private fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#2e1065;
  classDef shared fill:#ccfbf1,stroke:#0f766e,stroke-width:2px,color:#042f2e;
  classDef excluded fill:#fee2e2,stroke:#b91c1c,stroke-width:2px,stroke-dasharray:6 4,color:#450a0a;
  class E1,E2,E3,E4,E5 implemented;
  class T complete;
  class B,OS,RET,RG,Q,J gate;
  class OV,TR,D private;
  class SR,PA shared;
  class X1,X2,X3,X4,X5 excluded;
  class S,A,L,SC,C,I,ID,CV,PC,RC,AD,ST,IR,GA,PP,RCB,CLI,F,M,H planned;
```

## Runtime idea loop — unlimited passes without a cyclic execution DAG

```mermaid
flowchart LR
  I["Stable Idea IDEA-17"] --> P1["IdeaPass 17.1\nimmutable"]
  P1 --> C1{"Court/gate"}
  C1 -->|"adopt/adapt"| W1["Work attempt"]
  W1 --> V1{"Verification"}
  V1 -->|"failure + evidence"| R1["Remand\nreason, gate, actor, evidence"]
  R1 --> P2["IdeaPass 17.2\nimmutable successor"]
  P2 --> C2{"Court/gate"}
  C2 --> D2["Verified delivery"]
  D2 --> O2["Outcome / incident"]
  O2 --> R2["Re-entry trigger\nregression"]
  R2 --> P3["IdeaPass 17.3\nimmutable successor"]
  P3 --> MORE["... any later pass\nwithin leases/stopping policy"]

  R1 -. "semantic return to design/build" .-> W1
  R2 -. "semantic return to discovery/court" .-> C1

  classDef idea fill:#dbeafe,stroke:#2563eb,color:#102a43;
  classDef pass fill:#f3f4f6,stroke:#6b7280,color:#111827;
  classDef gate fill:#ffedd5,stroke:#c2410c,stroke-width:2px,color:#431407;
  classDef return fill:#fef3c7,stroke:#a16207,color:#422006;
  class I idea;
  class P1,P2,P3,W1,D2,O2,MORE pass;
  class C1,V1,C2 gate;
  class R1,R2 return;
```

The dotted arrows explain the conceptual backward movement. The durable chronology is
the solid left-to-right chain, so point-in-time replay and DAG scheduling remain valid.

## Private and shared write boundary

```mermaid
flowchart LR
  ROLES["All 8 roles + tools + court identities"] --> LEDGER[["Protected append-only canonical state\nAUTHORITY"]]
  LEDGER --> PG{"Private projection policy"}
  PG --> PV["Private generated vault\npermitted summaries + all lifecycle links"]
  PV --> OBS["Obsidian / any Markdown reader\nNON-AUTHORITATIVE"]

  LEDGER --> CB["Allowlist candidate builder\nnew abstraction, not a redacted copy"]
  CB --> LG{"Secret / private / IP / license /\nprovenance / taint / identity gates"}
  LG --> CU{"Independent Curator + Judge"}
  CU --> SR["Local shared registry\nabstract patterns only"]
  SR --> READ["Read-only prior art\nExplorer + Optimizer"]

  LG -->|"deny/quarantine"| DENY["Retained private decision + reason"]
  OBS -. "no direct canonical write" .-> LEDGER
  READ -. "no execution, authority, or promotion" .-> ROLES

  classDef authority fill:#d9f2df,stroke:#238636,stroke-width:3px,color:#102a17;
  classDef private fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#2e1065;
  classDef gate fill:#ffedd5,stroke:#c2410c,stroke-width:2px,color:#431407;
  classDef shared fill:#ccfbf1,stroke:#0f766e,stroke-width:2px,color:#042f2e;
  classDef denied fill:#fee2e2,stroke:#b91c1c,stroke-dasharray:6 4,color:#450a0a;
  class LEDGER authority;
  class PV,OBS private;
  class PG,LG,CU gate;
  class SR,READ shared;
  class DENY denied;
```
