# Repository Learning and Anti-Cheat Rules

## Point-in-time curriculum

For target commit `N`:

- visible history contains only valid ancestors before `N`;
- target commit and every later commit are hidden;
- target tree, message, diff, review, issue linkage, CI result, and future documentation remain inaccessible;
- prediction is sealed before target reveal;
- any access to target/future SHAs invalidates the episode.

## Classic GPT simulation

The user must provide:

- ordered commit metadata or snapshots;
- explicit visible cutoff;
- hidden target identifier kept outside the prompt until prediction is sealed.

The GPT must output:

```yaml
episode_id:
visible_commit_shas:
hidden_commit_shas_declared_by_controller:
accessed_shas:
prediction:
prediction_sealed: true
leakage_status:
```

The GPT cannot enforce hidden information if the user includes it in the prompt. It must disclose that limitation.

## Repository scouting

Candidate repositories are ranked using:

- objective relevance;
- engineering quality;
- recent activity;
- security posture;
- documentation quality;
- community signal;
- license compatibility;
- complete provenance.

Default weighting:

- relevance: 30%
- engineering quality: 20%
- activity: 15%
- security: 15%
- documentation: 10%
- community: 10%

Hard filters:

- incomplete provenance;
- unknown/incompatible license;
- relevance below threshold;
- no network-addressable source URI.

## Pattern learning

Retain abstract patterns, not copied incompatible code.

Each lesson records:

- source repository;
- pinned commit SHA;
- source URI;
- SPDX license;
- abstract pattern;
- supporting evaluations;
- application location;
- measured result.

## Anti-cheat and anti-copy rules

- Never infer a future commit from a source already revealing it.
- Never treat generic advice as a successful prediction.
- Never copy code without license and provenance review.
- Never promote a repository-derived pattern without measured evidence.
