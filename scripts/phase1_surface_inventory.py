from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import inspect
import json
import sys
import types
from enum import Enum
from pathlib import Path
from types import FunctionType
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    Union,
    cast,
    get_args,
    get_origin,
)

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os import cli

SCHEMA_VERSION = 1
ARTIFACT_PATH = Path("evidence/phase1/generation_zero_surface_inventory.json")

_SQL_WRITING_VERBS = {
    "ALTER",
    "CREATE",
    "DELETE",
    "DROP",
    "INSERT",
    "REINDEX",
    "REPLACE",
    "UPDATE",
    "VACUUM",
}
_SQL_TRANSACTION_VERBS = {"BEGIN", "COMMIT", "END", "ROLLBACK", "SAVEPOINT"}
_PATH_MUTATORS = {
    "chmod",
    "hardlink_to",
    "mkdir",
    "rename",
    "rmdir",
    "symlink_to",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}
_HANDLE_MUTATORS = {"flush", "truncate", "write", "writelines"}
_OS_MUTATORS = {
    "chmod",
    "fdopen",
    "link",
    "makedirs",
    "mkdir",
    "remove",
    "removedirs",
    "rename",
    "renames",
    "replace",
    "rmdir",
    "symlink",
    "unlink",
}
_SHUTIL_MUTATORS = {
    "copy",
    "copy2",
    "copyfile",
    "copytree",
    "move",
    "rmtree",
}
_TEMPFILE_CREATORS = {
    "tempfile.NamedTemporaryFile",
    "tempfile.TemporaryDirectory",
    "tempfile.mkdtemp",
    "tempfile.mkstemp",
}
_PROCESS_BOUNDARIES = {
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.run",
}
_WRITE_OPEN_FLAGS = frozenset("awx+")


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _qualified_name(value: object) -> str:
    module = getattr(value, "__module__", type(value).__module__)
    qualname = getattr(value, "__qualname__", type(value).__qualname__)
    return f"{module}.{qualname}"


def _required_int(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("inventory receipt field is not an integer")
    return value


def _stable_value(value: object) -> object:
    if value is inspect.Parameter.empty or value is inspect.Signature.empty:
        return {"state": "absent"}
    if value is dataclasses.MISSING:
        return {"state": "missing"}
    if repr(value) == "<factory>":
        return {"state": "factory"}
    if isinstance(value, Enum):
        return {
            "enum": _qualified_name(type(value)),
            "name": value.name,
            "value": _stable_value(value.value),
        }
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and Path(value) == Path(sys.executable):
            return {"runtime": "sys.executable"}
        return value
    if isinstance(value, bytes):
        return {
            "type": "builtins.bytes",
            "digest": f"sha256:{hashlib.sha256(value).hexdigest()}",
            "length": len(value),
        }
    if isinstance(value, Path):
        return {"path": value.as_posix()}
    if isinstance(value, tuple):
        items = [_stable_value(item) for item in value]
        if len(items) > 8:
            return {
                "collection": "tuple",
                "count": len(items),
                "digest": _digest_json(items),
            }
        return items
    if isinstance(value, frozenset):
        items = [_stable_value(item) for item in value]
        ordered = sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
        if len(ordered) > 8:
            return {
                "collection": "frozenset",
                "count": len(ordered),
                "digest": _digest_json(ordered),
            }
        return ordered
    if isinstance(value, (FunctionType, staticmethod, classmethod)) or inspect.isbuiltin(
        value
    ):
        target = value.__func__ if isinstance(value, (staticmethod, classmethod)) else value
        return {"callable": _qualified_name(target)}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {
            field.name: _stable_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
        return {
            "dataclass": _qualified_name(type(value)),
            "fields_digest": _digest_json(fields),
        }
    type_arguments = get_args(value)
    if type_arguments:
        return {
            "type_expression": {
                "arguments": [
                    _qualified_name(item)
                    if isinstance(item, type)
                    else str(item).replace("typing.", "")
                    for item in type_arguments
                ],
                "kind": (
                    "union"
                    if get_origin(value) in {types.UnionType, Union}
                    else "generic"
                ),
            }
        }
    return {"type": _qualified_name(type(value))}


def _annotation(value: object) -> object:
    if value is inspect.Parameter.empty or value is inspect.Signature.empty:
        return {"state": "absent"}
    if isinstance(value, str):
        return value
    if value is None:
        return "None"
    if isinstance(value, type):
        return _qualified_name(value)
    return str(value).replace("typing.", "")


def _signature(value: object) -> dict[str, object]:
    try:
        signature = inspect.signature(
            cast(Callable[..., object], value),
            eval_str=False,
        )
    except (TypeError, ValueError) as error:
        return {
            "available": False,
            "reason": type(error).__name__,
        }
    return {
        "available": True,
        "parameters": [
            {
                "annotation": _annotation(parameter.annotation),
                "default": _stable_value(parameter.default),
                "kind": parameter.kind.name.lower(),
                "name": parameter.name,
            }
            for parameter in signature.parameters.values()
        ],
        "return": _annotation(signature.return_annotation),
    }


def _public_members(value: type[object]) -> list[dict[str, object]]:
    members: list[dict[str, object]] = []
    for name, raw_member in sorted(value.__dict__.items()):
        if name.startswith("_"):
            continue
        member_kind = "attribute"
        member: object = raw_member
        if isinstance(raw_member, staticmethod):
            member_kind = "staticmethod"
            member = raw_member.__func__
        elif isinstance(raw_member, classmethod):
            member_kind = "classmethod"
            member = raw_member.__func__
        elif isinstance(raw_member, property):
            member_kind = "property"
            member = raw_member.fget
        elif inspect.isfunction(raw_member):
            member_kind = "method"
        entry: dict[str, object] = {
            "kind": member_kind,
            "name": name,
        }
        if callable(member):
            entry["signature"] = _signature(member)
        if callable(member) or isinstance(raw_member, property):
            members.append(entry)
    return members


def _facade_entries(
    module: object,
    facade_name: str,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    exported = getattr(module, "__all__")
    for name in sorted(exported):
        value = getattr(module, name)
        entry: dict[str, object] = {
            "defined_in": getattr(value, "__module__", "hive_mind_os"),
            "facade": facade_name,
            "name": name,
            "qualname": getattr(value, "__qualname__", name),
        }
        if inspect.isclass(value):
            entry["kind"] = "class"
            entry["bases"] = [
                _qualified_name(base) for base in value.__bases__
            ]
            entry["members"] = _public_members(value)
            if issubclass(value, Enum):
                entry["signature"] = {
                    "available": True,
                    "contract": "enum-value-lookup",
                    "parameters": [
                        {
                            "annotation": {"state": "absent"},
                            "default": {"state": "absent"},
                            "kind": "positional_or_keyword",
                            "name": "value",
                        }
                    ],
                    "return": _qualified_name(value),
                }
                entry["enum_members"] = [
                    {
                        "name": member.name,
                        "value": _stable_value(member.value),
                    }
                    for member in value
                ]
            else:
                entry["signature"] = _signature(value)
        elif inspect.isfunction(value):
            entry["kind"] = "function"
            entry["signature"] = _signature(value)
        else:
            entry["defined_in"] = facade_name
            entry["kind"] = "constant"
            entry["qualname"] = name
            entry["value"] = _stable_value(value)
        entries.append(entry)
    return entries


def public_api_inventory() -> dict[str, object]:
    entries_by_facade = {
        "hive_mind_os": _facade_entries(hive_mind_os, "hive_mind_os"),
        "hive_mind_os.package_system": _facade_entries(
            package_system,
            "hive_mind_os.package_system",
        ),
    }
    definitions: dict[str, object] = {}
    bindings: dict[str, dict[str, str]] = {}
    for facade, entries in entries_by_facade.items():
        bindings[facade] = {}
        for entry in entries:
            definition_id = (
                f"{entry['defined_in']}:{entry['qualname']}:{entry['kind']}"
            )
            definition = dict(entry)
            definition.pop("facade")
            definition.pop("name")
            definitions.setdefault(definition_id, definition)
            bindings[facade][str(entry["name"])] = definition_id
    body = {
        "bindings": bindings,
        "definitions": definitions,
        "entry_count": sum(len(entries) for entries in entries_by_facade.values()),
        "facades": {
            "hive_mind_os": {
                "export_count": len(hive_mind_os.__all__),
                "version": hive_mind_os.__version__,
            },
            "hive_mind_os.package_system": {
                "export_count": len(package_system.__all__),
            },
        },
    }
    return {
        **body,
        "digest": _digest_json(body),
    }


def cli_inventory() -> dict[str, object]:
    builders = {
        "default": cli.build_parser,
        "audit": cli.build_audit_parser,
        "benchmark": cli.build_benchmark_parser,
        "defer": cli.build_defer_parser,
        "deliver": cli.build_deliver_parser,
        "enqueue": cli.build_enqueue_parser,
        "experiment": cli.build_experiment_parser,
        "ingest": cli.build_ingest_parser,
        "missions": cli.build_missions_parser,
        "pit-episode": cli.build_pit_episode_parser,
        "resume": cli.build_resume_parser,
        "serve": cli.build_serve_parser,
        "status": cli.build_status_parser,
    }
    parsers: dict[str, object] = {}
    for name, builder in builders.items():
        parser = builder()
        actions = []
        for action in parser._actions:
            actions.append(
                {
                    "choices": (
                        sorted(str(choice) for choice in action.choices)
                        if action.choices is not None
                        else None
                    ),
                    "const": _stable_value(action.const),
                    "default": _stable_value(action.default),
                    "dest": action.dest,
                    "nargs": action.nargs,
                    "option_strings": list(action.option_strings),
                    "required": action.required,
                    "type": (
                        _qualified_name(action.type)
                        if callable(action.type)
                        else _stable_value(action.type)
                    ),
                }
            )
        parsers[name] = {
            "actions": actions,
            "prog": parser.prog,
        }
    return {
        "console_script": "hive-mind=hive_mind_os.cli:main",
        "digest": _digest_json(parsers),
        "parser_count": len(parsers),
        "parsers": parsers,
    }


def _source_arguments_contract(
    source: str,
    arguments: ast.arguments,
) -> list[dict[str, object]]:
    parameters: list[dict[str, object]] = []
    positional = [
        *(("positional_only", item) for item in arguments.posonlyargs),
        *(("positional_or_keyword", item) for item in arguments.args),
    ]
    defaults: list[ast.expr | None] = [
        *([None] * (len(positional) - len(arguments.defaults))),
        *arguments.defaults,
    ]

    def parameter(
        kind: str,
        item: ast.arg,
        default: ast.expr | None,
    ) -> dict[str, object]:
        return {
            "annotation": (
                ast.get_source_segment(source, item.annotation)
                if item.annotation is not None
                else None
            ),
            "default": (
                ast.get_source_segment(source, default)
                if default is not None
                else {"state": "absent"}
            ),
            "kind": kind,
            "name": item.arg,
        }

    parameters.extend(
        parameter(kind, item, default)
        for (kind, item), default in zip(positional, defaults, strict=True)
    )
    if arguments.vararg is not None:
        parameters.append(parameter("var_positional", arguments.vararg, None))
    parameters.extend(
        parameter("keyword_only", item, default)
        for item, default in zip(
            arguments.kwonlyargs,
            arguments.kw_defaults,
            strict=True,
        )
    )
    if arguments.kwarg is not None:
        parameters.append(parameter("var_keyword", arguments.kwarg, None))
    return parameters


def observable_module_inventory(
    repository: Path,
    *,
    include_additive: bool = False,
) -> dict[str, object]:
    source_root = repository / "src" / "hive_mind_os"
    definitions: list[dict[str, object]] = []
    constants: list[dict[str, object]] = []
    module_count = 0
    for path in _source_files(source_root, include_additive=include_additive):
        relative = path.relative_to(repository).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        module_count += 1
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name.startswith("_"):
                    continue
                entry: dict[str, object] = {
                    "kind": (
                        "class"
                        if isinstance(node, ast.ClassDef)
                        else "async-function"
                        if isinstance(node, ast.AsyncFunctionDef)
                        else "function"
                    ),
                    "line": node.lineno,
                    "name": node.name,
                    "path": relative,
                }
                if isinstance(node, ast.ClassDef):
                    entry["bases"] = [
                        ast.get_source_segment(source, base)
                        for base in node.bases
                    ]
                else:
                    entry["arguments_digest"] = _digest_json(
                        _source_arguments_contract(source, node.args)
                    )
                    entry["returns"] = (
                        ast.get_source_segment(source, node.returns)
                        if node.returns is not None
                        else None
                    )
                definitions.append(entry)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets: list[ast.expr]
                value: ast.expr | None
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                    value = node.value
                else:
                    targets = [node.target]
                    value = node.value
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if target.id.startswith("_") or not target.id.isupper():
                        continue
                    constants.append(
                        {
                            "expression_digest": (
                                _digest_json(
                                    ast.get_source_segment(source, value)
                                )
                                if value is not None
                                else None
                            ),
                            "line": node.lineno,
                            "name": target.id,
                            "path": relative,
                        }
                    )
    definitions.sort(
        key=lambda item: (
            str(item["path"]),
            _required_int(item["line"]),
        )
    )
    constants.sort(
        key=lambda item: (
            str(item["path"]),
            _required_int(item["line"]),
        )
    )
    return {
        "classification": "de-facto-observable-not-promised-supported",
        "constant_count": len(constants),
        "constants": constants,
        "definition_count": len(definitions),
        "definitions": definitions,
        "digest": _digest_json(
            {
                "constants": constants,
                "definitions": definitions,
            }
        ),
        "module_count": module_count,
    }


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _literal_string(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ast.unparse(node)
    return None


def _argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    if len(call.args) > position:
        return call.args[position]
    for item in call.keywords:
        if item.arg == keyword:
            return item.value
    return None


def _sql_verbs(statement: str) -> list[str]:
    verbs: list[str] = []
    for fragment in statement.split(";"):
        normalized = fragment.lstrip()
        if not normalized:
            continue
        verb = normalized.split(None, 1)[0].upper()
        verbs.append(verb)
    return verbs


def _write_mode(call: ast.Call, position: int = 0) -> str | None:
    mode_node = _argument(call, position, "mode")
    if mode_node is None:
        return "r"
    return _literal_string(mode_node)


class _EffectVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.scope: list[str] = []
        self.bindings: list[dict[str, str]] = [{}]
        self.event_producers: list[dict[str, object]] = []
        self.event_emitters: list[dict[str, object]] = []
        self.persistence_writers: list[dict[str, object]] = []
        self.unclassified_candidates: list[dict[str, object]] = []

    @property
    def owner(self) -> str:
        return ".".join(self.scope) if self.scope else "<module>"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.bindings.append({})
        self.generic_visit(node)
        self.bindings.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.bindings.append({})
        self.generic_visit(node)
        self.bindings.pop()
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.bindings.append({})
        self.generic_visit(node)
        self.bindings.pop()
        self.scope.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        value = _literal_string(node.value)
        if value is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.bindings[-1][target.id] = value
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        value = _literal_string(node.value)
        if value is not None and isinstance(node.target, ast.Name):
            self.bindings[-1][node.target.id] = value
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        value = _literal_string(node.value)
        if (
            value is not None
            and isinstance(node.op, ast.Add)
            and isinstance(node.target, ast.Name)
            and node.target.id in self.bindings[-1]
        ):
            self.bindings[-1][node.target.id] += value
        self.generic_visit(node)

    def _resolved_string(self, node: ast.expr | None) -> str | None:
        value = _literal_string(node)
        if value is not None:
            return value
        if isinstance(node, ast.Name):
            for bindings in reversed(self.bindings):
                if node.id in bindings:
                    return bindings[node.id]
        return None

    def _receipt(
        self,
        node: ast.Call,
        *,
        category: str,
        sink: str,
        detail: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        receipt: dict[str, object] = {
            "category": category,
            "column": node.col_offset,
            "line": node.lineno,
            "owner": self.owner,
            "path": self.relative_path,
            "sink": sink,
        }
        if detail:
            receipt.update(detail)
        return receipt

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        terminal = call_name.rsplit(".", 1)[-1] if call_name else None

        if terminal == "append_event":
            event_type = _argument(node, 1, "event_type")
            event_value = _literal_string(event_type)
            receipt = self._receipt(
                node,
                category="ledger.event-sink",
                sink=call_name or "append_event",
                detail={
                    "event_type_expression": (
                        ast.unparse(event_type)
                        if event_type is not None
                        else {"state": "missing"}
                    ),
                    "literal_event_type": event_value,
                },
            )
            self.event_emitters.append(receipt)
            if event_value is not None:
                self.event_producers.append(
                    {
                        **receipt,
                        "category": "ledger.event-producer",
                    }
                )
            elif not self.owner.endswith("._event"):
                self.unclassified_candidates.append(
                    {
                        **receipt,
                        "category": "ledger.dynamic-event-type",
                    }
                )
        elif terminal == "_event":
            event_type = _argument(node, 0, "event_type")
            event_value = _literal_string(event_type)
            receipt = self._receipt(
                node,
                category="ledger.event-producer",
                sink=call_name or "_event",
                detail={
                    "event_type_expression": (
                        ast.unparse(event_type)
                        if event_type is not None
                        else {"state": "missing"}
                    ),
                    "literal_event_type": event_value,
                    "via": "ExhibitStore._event",
                },
            )
            self.event_producers.append(receipt)
            if event_value is None:
                self.unclassified_candidates.append(
                    {
                        **receipt,
                        "category": "ledger.dynamic-event-type",
                    }
                )
        elif terminal == "append_lessons":
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="ledger.lessons",
                    sink=call_name or "append_lessons",
                )
            )

        if terminal in {"execute", "executemany", "executescript"}:
            receiver = (
                _call_name(node.func.value)
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if receiver and (
                receiver.endswith("_connection")
                or receiver.endswith(".connection")
                or receiver == "connection"
            ):
                statement_node = _argument(node, 0, "sql")
                statement = self._resolved_string(statement_node)
                if statement is None:
                    self.unclassified_candidates.append(
                        self._receipt(
                            node,
                            category="database.unknown",
                            sink=call_name or terminal,
                            detail={
                                "statement_expression": (
                                    ast.unparse(statement_node)
                                    if statement_node is not None
                                    else {"state": "missing"}
                                )
                            },
                        )
                    )
                else:
                    verbs = _sql_verbs(statement)
                    if any(verb in _SQL_WRITING_VERBS for verb in verbs):
                        category = "database.write"
                    elif any(verb in _SQL_TRANSACTION_VERBS for verb in verbs):
                        category = "database.transaction"
                    else:
                        category = "database.read"
                    if category != "database.read":
                        self.persistence_writers.append(
                            self._receipt(
                                node,
                                category=category,
                                sink=call_name or terminal,
                                detail={"sql_verbs": verbs},
                            )
                        )

        if terminal in _PATH_MUTATORS:
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="filesystem.mutation",
                    sink=call_name or terminal or "<unknown>",
                )
            )
        elif terminal == "open":
            mode = _write_mode(node, 1 if call_name == "open" else 0)
            if mode is None:
                self.unclassified_candidates.append(
                    self._receipt(
                        node,
                        category="filesystem.unknown-open",
                        sink=call_name or terminal,
                    )
                )
            elif any(flag in mode for flag in _WRITE_OPEN_FLAGS):
                self.persistence_writers.append(
                    self._receipt(
                        node,
                        category="filesystem.open-write",
                        sink=call_name or terminal,
                        detail={"mode": mode},
                    )
                )
        elif terminal in _HANDLE_MUTATORS:
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="filesystem.handle-write",
                    sink=call_name or terminal or "<unknown>",
                )
            )
        elif call_name in {f"os.{name}" for name in _OS_MUTATORS}:
            if call_name == "os.fdopen":
                mode = _write_mode(node, 1)
                if mode is None:
                    self.unclassified_candidates.append(
                        self._receipt(
                            node,
                            category="filesystem.unknown-fdopen",
                            sink=call_name,
                        )
                    )
                elif any(flag in mode for flag in _WRITE_OPEN_FLAGS):
                    self.persistence_writers.append(
                        self._receipt(
                            node,
                            category="filesystem.os-mutation",
                            sink=call_name,
                            detail={"mode": mode},
                        )
                    )
            else:
                self.persistence_writers.append(
                    self._receipt(
                        node,
                        category="filesystem.os-mutation",
                        sink=call_name,
                    )
                )
        elif call_name in {f"shutil.{name}" for name in _SHUTIL_MUTATORS}:
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="filesystem.shutil-mutation",
                    sink=call_name,
                )
            )
        elif call_name == "json.dump":
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="filesystem.serialized-write",
                    sink=call_name,
                )
            )
        elif call_name in _TEMPFILE_CREATORS:
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="filesystem.temporary-creation",
                    sink=call_name,
                )
            )
        elif call_name == "os.fsync":
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="filesystem.durability",
                    sink=call_name,
                )
            )
        elif (
            call_name in _PROCESS_BOUNDARIES
            or terminal in {"_git", "_run_git"}
        ):
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="external.process-potential-write",
                    sink=call_name or terminal or "<unknown>",
                )
            )
        elif call_name == "urllib.request.urlopen":
            self.persistence_writers.append(
                self._receipt(
                    node,
                    category="external.network-potential-write",
                    sink=call_name,
                )
            )
        elif terminal == "_request":
            method = _literal_string(_argument(node, 0, "method"))
            if method is not None and method.upper() not in {"GET", "HEAD"}:
                self.persistence_writers.append(
                    self._receipt(
                        node,
                        category="external.remote-api-write",
                        sink=call_name or terminal,
                        detail={"method": method.upper()},
                    )
                )

        self.generic_visit(node)


def _source_files(
    source_root: Path,
    *,
    include_additive: bool = False,
) -> Iterable[Path]:
    return sorted(
        path
        for path in source_root.rglob("*.py")
        if path.is_file()
        and (
            include_additive
            or "foundation" not in path.relative_to(source_root).parts
        )
    )


def effect_inventory(
    repository: Path,
    *,
    include_additive: bool = False,
) -> dict[str, object]:
    source_root = repository / "src" / "hive_mind_os"
    events: list[dict[str, object]] = []
    producers: list[dict[str, object]] = []
    writers: list[dict[str, object]] = []
    unclassified: list[dict[str, object]] = []
    files_scanned = 0
    for path in _source_files(source_root, include_additive=include_additive):
        relative = path.relative_to(repository).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        visitor = _EffectVisitor(relative)
        visitor.visit(tree)
        events.extend(visitor.event_emitters)
        producers.extend(visitor.event_producers)
        writers.extend(visitor.persistence_writers)
        unclassified.extend(visitor.unclassified_candidates)
        files_scanned += 1
    def key(item: Mapping[str, object]) -> tuple[str, int, int, str]:
        return (
            str(item["path"]),
            _required_int(item["line"]),
            _required_int(item["column"]),
            str(item["category"]),
        )
    events.sort(key=key)
    producers.sort(key=key)
    writers.sort(key=key)
    unclassified.sort(key=key)
    return {
        "coverage_contract": {
            "database_receivers": [
                "*._connection",
                "*.connection",
                "connection",
            ],
            "event_sink": "*.append_event",
            "event_wrapper": "ExhibitStore._event",
            "filesystem_handle_mutators": sorted(_HANDLE_MUTATORS),
            "filesystem_os_mutators": sorted(_OS_MUTATORS),
            "filesystem_path_mutators": sorted(_PATH_MUTATORS),
            "filesystem_shutil_mutators": sorted(_SHUTIL_MUTATORS),
            "filesystem_temporary_creators": sorted(_TEMPFILE_CREATORS),
            "lesson_sink": "*.append_lessons",
            "root": "src/hive_mind_os/**/*.py",
            "sql_methods": ["execute", "executemany", "executescript"],
            "sql_transaction_verbs": sorted(_SQL_TRANSACTION_VERBS),
            "sql_writing_verbs": sorted(_SQL_WRITING_VERBS),
            "truth_boundary": (
                "Bounded static characterization of declared sinks; "
                "receiver aliases, native extensions, generated code, and "
                "semantics hidden behind unlisted adapters require dynamic "
                "tracing before completeness can be claimed."
            ),
        },
        "event_producer_count": len(producers),
        "event_producers": producers,
        "event_sink_count": len(events),
        "event_sinks": events,
        "event_type_count": len(
            {
                item["literal_event_type"]
                for item in producers
                if item["literal_event_type"] is not None
            }
        ),
        "event_types": sorted(
            {
                str(item["literal_event_type"])
                for item in producers
                if item["literal_event_type"] is not None
            }
        ),
        "files_scanned": files_scanned,
        "persistence_writer_count": len(writers),
        "persistence_writers": writers,
        "unclassified_candidate_count": len(unclassified),
        "unclassified_candidates": unclassified,
    }


def build_inventory(
    repository: Path,
    *,
    include_additive: bool = False,
) -> dict[str, Any]:
    effects = effect_inventory(repository, include_additive=include_additive)
    public_api = public_api_inventory()
    body = {
        "schema_version": SCHEMA_VERSION,
        "cli": cli_inventory(),
        "observable_module_surface": observable_module_inventory(
            repository,
            include_additive=include_additive,
        ),
        "scope": {
            "package": "hive_mind_os",
            "public_api_facades": [
                "hive_mind_os.__all__",
                "hive_mind_os.package_system.__all__",
            ],
            "source_root": "src/hive_mind_os",
            "surface_classifications": {
                "cli": "supported",
                "module_public_definitions": "de-facto",
                "package_facades": "supported",
            },
        },
        "public_api": public_api,
        "runtime_effects": effects,
    }
    return {
        **body,
        "inventory_digest": _digest_json(body),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"write {ARTIFACT_PATH.as_posix()}",
    )
    args = parser.parse_args()
    repository = args.repository.resolve()
    inventory = build_inventory(repository)
    rendered = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    if args.write:
        output = repository / ARTIFACT_PATH
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
