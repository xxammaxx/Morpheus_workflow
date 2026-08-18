#!/usr/bin/env python3
"""AutoDev contract validator — dependency-free JSON Schema subset (Draft-07 core).

Implemented subset (sufficient for all autodev.* schemas):
  type, required, properties, additionalProperties, items, enum, const,
  pattern, minLength, maxLength, minimum, maximum, minItems, maxItems, oneOf,
  $defs/$ref (single-level), $id.

API:
    validate(payload, schema) -> {"ok": bool, "contract": str|None,
                                   "errors": [str], "error_count": int}

The JS twin lives at runtime/contracts/validator.js — both MUST agree on
every schema (cross-language equivalence is part of the test matrix).
"""

import json
import os
import re


class SchemaError(Exception):
    pass


def _type_check(value, expected, path, errors):
    if expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append("%s: expected integer, got %s" % (path, type(value).__name__))
    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append("%s: expected number, got %s" % (path, type(value).__name__))
    elif expected == "string":
        if not isinstance(value, str):
            errors.append("%s: expected string, got %s" % (path, type(value).__name__))
    elif expected == "boolean":
        if not isinstance(value, bool):
            errors.append("%s: expected boolean, got %s" % (path, type(value).__name__))
    elif expected == "object":
        if not isinstance(value, dict):
            errors.append("%s: expected object, got %s" % (path, type(value).__name__))
    elif expected == "array":
        if not isinstance(value, list):
            errors.append("%s: expected array, got %s" % (path, type(value).__name__))
    elif expected == "null":
        if value is not None:
            errors.append("%s: expected null, got %s" % (path, type(value).__name__))
    else:
        raise SchemaError("unsupported type %r" % expected)


def _resolve_ref(schema, ref):
    # only "#/$defs/name" supported
    if ref.startswith("#/$defs/"):
        name = ref[len("#/$defs/") :]
        defs = schema.get("$defs", {})
        if name in defs:
            return defs[name]
        raise SchemaError("unresolved $ref %r" % ref)
    raise SchemaError("unsupported $ref %r" % ref)


def _validate(value, schema, path, errors, root):
    if schema is True:
        return
    if schema is False:
        errors.append("%s: schema forbids value" % path)
        return

    if "$ref" in schema:
        target = _resolve_ref(root, schema["$ref"])
        _validate(value, target, path, errors, root)
        return

    if "oneOf" in schema:
        matched = 0
        for sub in schema["oneOf"]:
            sub_errors = []
            _validate(value, sub, path, sub_errors, root)
            if not sub_errors:
                matched += 1
        if matched != 1:
            errors.append(
                "%s: must match exactly one of %d alternatives (matched %d)"
                % (path, len(schema["oneOf"]), matched)
            )
        return

    if "type" in schema:
        expected = schema["type"]
        if isinstance(expected, list):
            any_ok = False
            for e in expected:
                probe = []
                _type_check(value, e, path, probe)
                if not probe:
                    any_ok = True
                    break
            if not any_ok:
                errors.append("%s: type must be one of %s" % (path, expected))
        else:
            _type_check(value, expected, path, errors)
            if errors and errors[-1].startswith(path + ":"):
                # type error already recorded; skip structural checks below
                return

    if "const" in schema:
        if value != schema["const"]:
            errors.append("%s: must equal %r" % (path, schema["const"]))
        return

    if "enum" in schema:
        if value not in schema["enum"]:
            errors.append("%s: must be one of %s" % (path, schema["enum"]))
        return

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append("%s: length must be >= %d" % (path, schema["minLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append("%s: length must be <= %d" % (path, schema["maxLength"]))
        if "pattern" in schema:
            if re.search(schema["pattern"], value) is None:
                errors.append("%s: must match pattern %r" % (path, schema["pattern"]))
        return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: must be >= %d" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: must be <= %d" % (path, schema["maximum"]))
        return

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(
                "%s: must have at least %d items" % (path, schema["minItems"])
            )
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append("%s: must have at most %d items" % (path, schema["maxItems"]))
        if "items" in schema:
            items_schema = schema["items"]
            for i, item in enumerate(value):
                _validate(item, items_schema, "%s[%d]" % (path, i), errors, root)
        return

    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name, sub in props.items():
            if name in value:
                _validate(value[name], sub, "%s.%s" % (path, name), errors, root)
        required = schema.get("required", [])
        for name in required:
            if name not in value:
                errors.append("%s: %s is required" % (path, name))
        addl = schema.get("additionalProperties", True)
        if addl is False:
            for key in value:
                if key not in props:
                    errors.append(
                        "%s: additional property %r not allowed" % (path, key)
                    )
        elif isinstance(addl, dict):
            for key in value:
                if key not in props:
                    _validate(value[key], addl, "%s.%s" % (path, key), errors, root)
        return


def validate(payload, schema):
    """Validate payload against schema. Returns result dict (never raises)."""
    errors = []
    if (
        isinstance(schema, dict)
        and schema.get("type") == "object"
        and not isinstance(payload, dict)
    ):
        errors.append("$: expected object, got %s" % type(payload).__name__)
    else:
        try:
            _validate(payload, schema, "$", errors, schema)
        except SchemaError as exc:
            return {
                "ok": False,
                "contract": schema.get("$id"),
                "errors": [str(exc)],
                "error_count": 1,
            }
    contract = schema.get("$id") if isinstance(schema, dict) else None
    return {
        "ok": not errors,
        "contract": contract,
        "errors": errors,
        "error_count": len(errors),
    }


def load_schema(path):
    with open(path) as f:
        return json.load(f)


def validate_file(payload, schema_path):
    return validate(payload, load_schema(schema_path))


if __name__ == "__main__":
    import sys

    schema_path, payload_path = sys.argv[1], sys.argv[2]
    with open(payload_path) as f:
        payload = json.load(f)
    print(json.dumps(validate(payload, load_schema(schema_path)), indent=2))
