# Verify an agent-authored change

This example creates a small, real local Git repository for a nonprofit checkout
rule, applies an agent-authored patch, commits that patch, and verifies the committed
change with `hive-mind verify`. It runs offline in well under five minutes and writes
the resulting receipt bundle to a directory you choose.

The checked-in [`agent-change.patch`](agent-change.patch) was authored by Codex for
this example. The runner commits it as `Codex Example Agent`; it is a transparent,
static example input, not a claim that a model was called during the run.

## Run it

From the repository root:

```bash
python -m pip install --no-deps -e .
python examples/verify-an-agent-change/run_example.py
```

The default output is `./example-out`, which must not already exist. To choose another
location, pass `--output /path/to/absent-directory`.

## What happens

1. The runner copies [`repository/`](repository/) into `example-out/nonprofit-checkout`
   and initializes it as a Git repository.
2. It creates a baseline commit, applies the agent patch, and commits the one-file
   change as `Codex Example Agent <codex@example.invalid>`.
3. It invokes the public CLI with [`acceptance-spec.json`](acceptance-spec.json).
   The spec is sealed before Hive Mind OS reads the candidate commit.
4. It prints the Curator verdict and leaves these inspectable artifacts:

   ```text
   example-out/
   ├── nonprofit-checkout/       # Git worktree with the agent commit at HEAD
   └── receipt-bundle/
       ├── verification.json     # verdict, changed paths, sealed specification
       ├── ledger.sqlite3        # append-only verification events
       └── receipts/             # content-addressed command receipt
   ```

The acceptance spec declares only `discounts.py` as changed and executes the retained
checkout check. A passing `adopt` verdict therefore shows that the agent patch changed
only the declared implementation file and satisfied the sealed check. This is a local
educational example, not evidence of a general coding-agent capability or production
readiness.
