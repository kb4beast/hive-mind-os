# ADR-WOS-N17: externally controlled self-upgrade transition

Status: accepted implementation contract; production activation remains externally
authorized and independently qualified.

## Decision

Hive may construct an immutable `RuntimeChallenger`, but it cannot activate itself.
The challenger binds its artifact, parent champion, source, dependency and migration
manifests, rollback artifact, held-out evaluation, distinct builder/evaluator/judge
identities, and bounded canary scope. `UpgradeController` records the candidate intent
before asking an injected host broker to change a version pointer.

A lost activation response enters `RECONCILIATION_REQUIRED`. Restart loads the same
pending challenger digest and calls the broker's observation seam; it never repeats
activation. Rollback is accepted only for the observed active challenger and uses the
same external broker. Missing broker authority returns a canary-ready local artifact,
not a fabricated promotion.

## Alternatives and threats

Editing the running controller, letting a candidate hold supervisor credentials, and
retrying an uncertain pointer mutation were rejected because they permit survival
incentives, authority expansion, or duplicate effects. A successful unit, benchmark,
or self-authored verdict is also insufficient: evaluator and Judge identities must be
distinct from the Builder, the held-out evaluation must pass, and rollback must have
been rehearsed.

The persisted state contains only version/digest identities and receipt references;
credentials and host secrets stay behind the broker. A digest proves identity, not
superiority or permission. Real canary isolation, pointer authority, and restoration
evidence remain N31 external qualification inputs.

## Migration and rollback

The controller's optional state file is a closed record containing state, active and
pending challenger digests, and the retained parent. Installations without it retain
the prior in-memory behavior. A malformed record fails closed. Rollback asks the host
to restore the retained compatible champion, clears the active/pending challenger,
and preserves the historical receipts for later judgment.
