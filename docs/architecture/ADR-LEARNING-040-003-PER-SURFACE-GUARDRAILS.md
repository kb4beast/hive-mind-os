# ADR: Apply configured guardrails to every matching surface

Date: 2026-09-10
Status: locally verified; protected delivery pending
Idea: LEARNING-040-003; parent: LEARNING-040-002

## Source and decision

Host-supplied repository commit 89bd6ae34eb84e3e229940669165977937b77b01
contains evaluation_runtime.py blob a10334379f825104bbebf361282a3ee6de6e57d6.
Repository MIT licensing applies. No external implementation is incorporated.
COURT-050 selected the bounded correction under REVISE-048:R1 after separate
advocacy, cross-examination, witness testimony, and revision examination.
This document records that supplied judgment, not a new Builder judgment.

Distinct names within a surface kind are valid inputs. Collapsing them by kind
lets a later-named passing measurement mask an earlier regression. Check every
matching surface for each configured guardrail, using existing mean differences
and strict maximum-regression comparison. Equality remains within budget.

## Architecture, threat, and compatibility

Preserve quarantine before completeness-related retest, then hard guardrails,
then the existing held-out primary decision. Preserve deterministic ordering,
public interfaces, record schema, fingerprints, and all retained measurements.
This prevents lexical naming from hiding a guarded loss. Representative-only
selection has no declared contract; aggregation could conceal individual losses.
Multiple held-out primary selection and authenticated promotion remain open
parent obligations. Local actor labels do not prove independent administration.

## Validation, migration, and rollback

MultiSurfaceGuardrailTests covers naming/order, all kinds, budgets, retention,
controls, and precedence. Independent host execution retained the expected
baseline failure and a passing 19-test candidate receipt at tournament candidate
`a92bcf0c3558e7b1139b37cae711e52b74bfdedf`.
No data migration: preserve historical records and bind new evaluations to the
evaluator source version; a configuration fingerprint is not a code identity.
Rollback supersedes the isolated candidate while retaining receipts. No champion
pointer, promotion authority, workspace dependency, or DAG configuration changes.
