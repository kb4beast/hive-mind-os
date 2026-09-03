# Portable planner prompt

`hive_mind_os.planner_prompt` contains the repository-owned MIT-licensed prompt used to
request an inert portable DAG. Its artifact records the exact UTF-8 byte count and
SHA-256. Runtime request, subject, standard, snapshot, and authority bindings are supplied
as separate structured inputs so prompt wording cannot silently become an authority grant.

The prompt is vendor-, language-, repository-, and branch-neutral. It requires all eight
lifecycle roles, explicit resource/capability/evidence references, identity separation,
rollback, typed blockers, and denial of external effects unless an independently
authenticated one-run capability permits them. It emits JSON data only and contains no
credential, signature, command, or execution path.
