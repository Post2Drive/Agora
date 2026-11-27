# Portable Ontology Schemas

**Status:** Current for the two document formats Agora reads today. The schemas describe structure only. They have been checked with Python `jsonschema` in the test suite. No external tool or other organisation has adopted or certified them.

## 1. What is published

| Document | Schema | Conformance vectors |
|---|---|---|
| Domain pack | `agora/ontology/schemas/domain-pack.schema.json` | `conformance/ontology/domain-pack.json` |
| Data binding | `agora/ontology/schemas/data-binding.schema.json` | `conformance/ontology/data-binding.json` |

Both use JSON Schema draft 2020-12 and ship inside the Python package. `python -m agora.ontology.schema domain-pack` (or `data-binding`) prints one. They are generated from the parser's constants, and a test fails if a published file differs from the generator.

## 2. What a schema result means

- **Schema refuses:** Agora is expected to refuse the document too. The vectors check this case by case; it is not a proof for every possible document.
- **Schema accepts:** Agora can still refuse it. Passing the schema does not make a pack or binding usable.

Agora applies these rules that the schemas do not:

| Rule | Document |
|---|---|
| Object properties, link ends and action actor and target must resolve inside the pack | Pack |
| One definition per ID in a pack | Pack |
| An object type lists each property once | Pack |
| Each `unique_keys` entry names properties of that object type, once each; no two entries name the same set; no `structured_object` property (section 2b) | Pack |
| `property_sensitivity` keys must be mapped property IDs | Binding |
| `scale` must not exceed `precision` | Pack |
| Each `allowed_values` entry must match the property's `data_type` (section 2a) | Pack |
| `precision` and `scale` must be written as integers (`2`, not `2.0`) | Pack |
| `primary_key_column` must be a key of `column_map` | Binding |
| Two columns must not map to one property | Binding |
| A supplied `fingerprint` must match the content | Binding |
| The binding must match the pack's object type, its properties, and the snapshot's schema, types and sensitivity | Binding, checked when used |

Numbers that are not finite, and repeated keys in a file, are properties of the file text, which JSON Schema does not see. Agora refuses repeated keys in JSON and YAML pack and binding files. A caller that parses JSON itself and passes Agora a mapping must reject repeated keys itself.

Pack text fields and fixed values such as `data_type` may have surrounding whitespace, which Agora removes. The schemas allow the same. Action safety guards and binding sensitivity values must be exact.

### 2a. Allowed values and data types

| `data_type` | Each entry must be |
|---|---|
| `string`, `identifier`, `enum` | A string |
| `integer` | An integer (not a boolean, not `1.0`) |
| `boolean` | `true` or `false` |
| `decimal` | A finite number, or a string that reads as one; not a boolean |
| `date` | A string in the form `2026-01-31` |
| `timestamp` | A string in the stored UTC form, such as `2026-01-31T10:00:00+00:00` (six fraction digits if any; not `Z`, not another offset) |
| `structured_object` | None: the list must be empty or absent |

A `null` entry is accepted only when the property is `nullable`; whether a null source value is allowed is still decided by `nullable` alone. In YAML, quote dates and timestamps, or the loader reads them as non-string values. The check does not apply `precision` or `scale` to decimal entries.

### 2b. Unique keys

An object type may declare `unique_keys`, a list of keys. Each key is a non-empty list of the object type's property IDs; a key with two or more IDs constrains the combination. An empty or absent list declares nothing and gives the same pack fingerprint. The record key identity stays unique whether or not it is listed.

- **Scope:** the rows of one exact import, read through one binding for that object type. It is not enforced across imports, datasets, object types or pack versions, because the same record is restated in later imports and the object store holds no property values.
- **Comparison:** decimals compare by exact numeric value (`1.5` equals `1.50`); all other values compare exactly as stored, so strings are case- and space-sensitive. Dates and timestamps are already in the stored canonical form.
- **Nulls:** a row with a null in any property of a key is not compared on that key.
- **Where it is checked:** `materialize_instances` (and so scenario inputs) and `iter_source_object_refs` (and so `materialize_binding`, which then stores no references from that call). `materialize_source_object` reads one row and cannot check it. A direct consumer of `iter_source_object_refs` receives earlier rows before the refusal, so it must discard them. The error names the key's property IDs, never values.
- **Cost:** one 32-byte digest per row and key is held in memory while an import is read (plus the language's own overhead). This has not been measured on large imports.
- **Compatibility:** `unique_keys` is optional, so previously accepted documents are still accepted and the schema major version is unchanged. Older Agora code refuses a pack that declares it. Adding or removing a key is a breaking pack change; reordering is not.

## 3. Conformance vectors

Each file has:

- `cases`: a `document`, with `schema_valid` and `agora_valid`. `agora_valid` is the result of parsing alone (`parse_domain_pack` or `load_binding`), not of checking against a snapshot.
- `json_text_cases`: raw `text` of a JSON file, with `agora_valid`, for repeated keys.

All values are synthetic. Another implementation conforms to the structural contract if its schema results match `schema_valid`. Matching `agora_valid` also requires the rules in section 2.

## 4. Versioning

The `$id` of each schema ends in its major version (`:1`). The identifiers are names, not web addresses. A change that makes a previously accepted document fail needs a new major version. The schema version is separate from a pack's `schema_version`; changes between two pack versions are covered by [ONTOLOGY_COMPATIBILITY.md](ONTOLOGY_COMPATIBILITY.md).

When these schemas were first published, the parsers were tightened to match them. Agora now refuses, with an `OntologyError`: repeated keys in JSON files; non-ASCII digits in pack versions; and, in bindings, non-string field names, a non-string primary key column or sensitivity value (these three previously raised a `TypeError`).

The later O0 close-out audit made two more parsing rules stricter without changing the schemas: an object type that repeats a property, and a binding whose `property_sensitivity` names an unmapped property, are now refused.

The `allowed_values` data type rule in section 2a is a later parser rule, also without a schema change: a pack that lists an entry of another type is now refused. This includes a pack already stored in an object store, which then fails to load and fails `verify_integrity`; the stored rows are not rewritten. No pack in this repository was affected apart from one conformance vector, which was corrected.
