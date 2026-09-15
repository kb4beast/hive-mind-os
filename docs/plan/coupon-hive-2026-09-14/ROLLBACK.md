# Coupon Hive rollback and recovery

## Release 0.1.0 rollback

1. Disable or unpublish the plugin version in the publisher controls.
2. Restore the last independently approved plugin version if one exists.
3. Preserve the failed version, source ledger, evaluation results, review receipts, incident notes, and dissent as append-only evidence.
4. Notify affected users through the available publisher channel when an accuracy, privacy, or security defect is material.
5. Fix in a new version and rerun all positive, negative, deterministic, and independent evaluations before promotion.

Version 0.1.0 has no publisher database, OAuth tokens, background workers, payment flow, or affiliate account to migrate or purge.

## Scheduled-task cleanup

Plugin removal does not necessarily pause or delete tasks users already created. Use task titles beginning “Coupon Hive —” so they are discoverable. Direct users to the host's Scheduled controls to pause or delete each task. When the skill performs cleanup, each standalone pause, resume, or delete requires its own freshly confirmed LifecycleSpec, matching host observation, retained consumption marker, and receipt. An unknown create outcome must be resolved by listing before retry; never create a replacement or auto-delete as compensation. A version-bound task must fail closed if the skill becomes unavailable or incompatible.

## Legacy GPT rollback

Unshare or archive the GPT under current workspace controls. Existing recurring prompts pasted into regular chats are independent; locate and pause or delete their tasks separately.

## Future MCP rollback

A future remote service must add, before release:

- a kill switch and version compatibility gate;
- per-user token revocation;
- job halt and notification suppression;
- user export and deletion procedures;
- database backup and tested restore;
- tenant-isolation and credential-rotation procedures;
- a migration plan from and back to the previous champion.

That authority is not present in release 0.1.0.
