# ADR-089: Optional IANA timezone data for Windows plugin validation

## Decision

Adopt `tzdata` 2026.4 as a pinned, Windows-only optional dependency for the
bundled Coupon Hive plugin. Constitutional CI installs the same universal wheel
from a hash-locked requirements file before running the Windows matrix. Core
Hive Mind OS remains stdlib-only, and Linux hosts continue to use their system
IANA timezone database.

This fixes a platform capability gap rather than changing validation policy.
Coupon Hive continues to require `schedule.timezone` to resolve as a real IANA
timezone through `zoneinfo.ZoneInfo`; names that only look plausible remain
invalid.

## Source and court record

The adopted source is the Python Software Foundation's `tzdata` 2026.4 release
on PyPI, retrieved 2026-09-21 from `https://pypi.org/project/tzdata/2026.4/`.
The package is Apache-2.0 licensed. The admitted artifact is
`tzdata-2026.4-py2.py3-none-any.whl`, SHA-256
`c2169a8b0a7a5e9674da5a135ccdfb2b3e671b333ed9fed17b41f73c34476e81`.

The advocate's case is that Windows Python does not ship an IANA database, so
the otherwise portable stdlib validator rejects valid timezones such as
`America/Chicago`. Cross-examination considered accepting syntactically
plausible names, embedding an allowlist, and making `tzdata` a core dependency.
Those alternatives either weaken validation, create a separately maintained
database, or impose an unnecessary package on hosts that already provide the
data. The disposition is **adapt**: expose the dependency as an optional extra
and install it only in the Windows qualification job.

## Migration and rollback

Windows users of Coupon Hive install `hive-mind-os[coupon-hive-windows]`.
Existing core installations do not change. The CI install remains explicit
because its exact-package step deliberately uses `--no-deps`.

Rollback removes the optional extra, the Windows CI install, and the pinned
requirements file together. The prior fail-closed timezone behavior then
returns on Windows; no persisted data needs migration.

## Verification

The existing Coupon Hive semantic-validator tests exercise valid
`America/Chicago` and `America/New_York` schedules as well as invalid timezone
names. The repository's full constitutional gate runs those tests on Windows
Python 3.12 and 3.14 after installing the hash-locked wheel.
