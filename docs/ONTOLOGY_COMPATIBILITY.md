# Ontology Pack Compatibility Policy

**Status:** Current for the check in `agora/ontology/compat.py`. It is a library and command-line check. `OntologyObjectStore` does not call it, so it does not stop a pack from being registered. Running it in a release process is the caller's job.

## 1. Meaning of "compatible"

A change is **compatible** only if it is on this list:

- a new object, property, link or action type;
- a new `name` on any definition, or a new `description` on an object type;
- the same object `properties`, object `unique_keys` (keys, or the properties inside a key) or property `allowed_values` in a different order.

Every other change is **breaking**. That includes any field added to the registry later, until it is listed here. Some breaking cases are stricter than they may look:

| Change | Why it is breaking |
|---|---|
| A property added to an existing object type, even an optional one | A data binding must map exactly the object's properties, so an existing column map stops matching |
| A `unique_keys` entry added or removed | Adding refuses data that was accepted; removing withdraws a guarantee. A changed key counts as both |
| `allowed_values` widened | Readers can receive a value they have not seen before |
| `required` or `nullable` changed in either direction | Either stored records or readers lose a guarantee |
| Sensitivity raised | Existing consumers can be denied by policy |
| Sensitivity lowered | A protection is weakened and needs review |
| Link cardinality loosened or tightened | Either readers or stored links lose a guarantee |
| Any action field except `name` | Actor, target, inputs, preconditions, effects or permissions change what is allowed |

The list does not show that a change is safe for a particular application. A new action type is compatible with existing consumers but adds a simulated capability and permissions, so review it.

## 2. Version rules

Versions are compared by semantic version precedence. Build metadata does not count.

1. No definition or pack version may go down.
2. A changed definition needs a higher version.
3. A breaking change needs a higher major version. This applies to `0.x` versions too.
4. When a property type has a breaking change, every object type that keeps that property also needs a higher major version. Bindings pin the object type version, so without this the same object version would mean something else.
5. If any definition is added, removed, changed or re-versioned, the pack `schema_version` must go up. A breaking change needs a higher major pack version. A removed definition has no version left, so the pack version is what records the removal.

## 3. Use

```
python -m agora.ontology.compat old-pack.yaml new-pack.yaml
python -m agora.ontology.compat old-pack.yaml new-pack.yaml --allow-breaking
```

The output is JSON listing each change and each version rule breach. Exit status is `0` when the release is allowed, `1` when it is refused and `2` when an input cannot be used. Breaking changes are refused unless `--allow-breaking` is given. A breach of a version rule is always refused. In code, use `compare_packs` or `require_release`.

## 4. Limits

- The check compares only the two packs it is given. It cannot tell whether the old pack is the one actually released.
- It does not inspect stored objects, links or bindings, and it migrates nothing. Old packs remain separate immutable snapshots selected by fingerprint.
- A breaking change to an object type does not force new versions on the link or action types that refer to it.
- Migration reports over stored records are not implemented. Structural schemas for packs and bindings are described in [ONTOLOGY_PORTABLE_SCHEMAS.md](ONTOLOGY_PORTABLE_SCHEMAS.md); they do not check compatibility.
