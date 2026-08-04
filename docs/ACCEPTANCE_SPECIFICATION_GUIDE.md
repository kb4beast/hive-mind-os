# Write an acceptance specification

An acceptance specification is the sealed, executable statement of what a
candidate commit must prove. `hive-mind verify` validates the document and seals
it before reading the candidate repository. The command it names is the only
command that can satisfy that criterion.

Start with the runnable
[nonprofit checkout example](../examples/verify-an-agent-change/README.md). Its
[`acceptance-spec.json`](../examples/verify-an-agent-change/acceptance-spec.json)
has this shape:

```json
{
  "schema_version": 1,
  "id": "nonprofit-discount-is-applied",
  "criterion": "A nonprofit checkout receives the documented 20 percent discount without changing the standard checkout total.",
  "command": {
    "argv": ["python", "check_discount.py"],
    "expected": "succeeded"
  },
  "declared_paths": ["discounts.py"]
}
```

## Fields

| Field | What to provide |
| --- | --- |
| `schema_version` | The number `1`. |
| `id` | A unique lowercase kebab-case identifier, such as `checkout-total-is-correct`. |
| `criterion` | The human-readable behavior the check proves. It is a requirement, not a description of the implementation. |
| `command.argv` | The exact program and arguments to execute, as an array. It is not a shell command: do not use shell quoting, pipes, or redirection. |
| `command.expected` | `"succeeded"` when the command must exit successfully, or `"failed"` when a nonzero result is the expected evidence. |
| `declared_paths` | The complete, unique set of portable relative paths the candidate commit is allowed to change. |

For the local `verify` workflow, `declared_paths` must be present and nonempty.
The candidate's changed paths must exactly match that list; an omitted or extra
path rejects the verification. Use `/`-separated relative paths such as
`src/pricing.py`, never absolute paths or `..` segments.

## Author the check before the change

Write the criterion and command against the baseline repository, then pass the
file to `verify` before considering the candidate commit:

```bash
hive-mind verify \
  --repository /path/to/local/repository \
  --spec /path/to/acceptance-spec.json \
  --output /path/to/absent/receipt-bundle
```

Choose a command that directly tests the stated behavior and has deterministic
inputs. The resulting receipt bundle records the specification's canonical digest,
the executed arguments, the command outcome, and the declared versus actual changed
paths. A passing check only establishes the behavior expressed here; it is not a
general claim about an agent or the repository.

## Common mistakes

- Declaring only the production file when the commit also changes a test, fixture, or configuration file.
- Writing a vague criterion that the command does not actually exercise.
- Passing a one-string shell command instead of a literal argument array.
- Choosing an expected failure without making the failure itself meaningful evidence.

The full contract is defined by the
[`acceptance-specification` schema](../src/hive_mind_os/schemas/acceptance-specification.schema.json)
and its [architecture decision](architecture/ADR-041-TYPED-EXECUTABLE-ACCEPTANCE-SPECS.md).
