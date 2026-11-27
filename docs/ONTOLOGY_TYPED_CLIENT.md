# Typed Python Types from a Domain Pack

**Status:** Library and command only (first O3 slice, 28 Nov 2026). This is not a versioned API, a client of any service, or a released SDK. Checked with synthetic data in this repository's tests; no outside application has used it.

## 1. Use

```
python -m agora.ontology.typed domain_packs/retail_in/pack.yaml > retail_types.py
```

In code: `generate_python_types(pack)` in `agora/ontology/typed.py` returns the same text. The output imports only the standard library, so an application can use it without installing Agora. Do not edit it; generate it again from the pack. Review it before use, like any other code you add to an application.

```python
page = store.query_objects(retail_types.PACK_FINGERPRINT, retail_types.Customer.TYPE_ID,
                           retail_types.Customer.TYPE_VERSION, import_id, {}, 50, None, ...)
customers = [retail_types.Customer.from_instance(row) for row in page["objects"]]
```

The module has `PACK_ID`, `PACK_SCHEMA_VERSION`, `PACK_FINGERPRINT`, `GENERATOR_VERSION`, one frozen dataclass per object type, and `OBJECT_TYPES`, keyed by type ID and version. Link types, action types and query filters get no generated form.

## 2. Names

The class name is the part of the type ID after the colon. It must start with an ASCII capital. A field name is the part of the property ID after the last dot (of the text after the colon). Names use ASCII letters, digits and underscores and start with a letter. A Python keyword, a name the module needs, or two definitions that give one name are refused. Nothing is renamed automatically, so some valid packs cannot be generated.

## 3. What `from_instance` checks

It takes one instance dictionary, as returned by `materialize_instances`, `get_object` or the `objects` of `query_objects`, and raises `InstanceError` unless:

- the object type ID and version are the class's;
- `property_values` and `property_sensitivity` name exactly the type's properties;
- no classification is unknown or below the one the pack declares;
- a null appears only on a nullable property;
- each value has the stored form of its data type (below) and is in `allowed_values` when the pack lists them;
- the provenance fields are present.

| `data_type` | Stored form accepted | Python type |
|---|---|---|
| `string`, `identifier`, `enum` | String | `str` |
| `integer` | Integer, not a boolean | `int` |
| `boolean` | `true` or `false` | `bool` |
| `decimal` | Plain decimal string (no spaces, underscores or exponent) or integer; never a float | `decimal.Decimal` |
| `date` | `2026-01-31` | `datetime.date` |
| `timestamp` | Stored UTC form, such as `2026-01-31T10:00:00+00:00` | `datetime.datetime` with UTC |
| `structured_object` | Not supported: generation is refused | — |

Error messages name properties and never carry values. Each object keeps `provenance`: record key, import, row, dataset, binding and its fingerprint, source file hash and source registry ID when present, and the classification of each property. The full source locator and the schema fields are not kept.

Property values are left out of `repr`. They are not otherwise protected: attributes, `dataclasses.asdict`, pickling and an application's own logs can all expose them.

## 4. Limits

- **A shape check, not proof of origin.** `from_instance` accepts any dictionary that fits. It does not authenticate it, apply policy or consult the audit chain. Read data through the ontology library's checked calls.
- **The pack is not checked per row.** An instance dictionary carries no pack fingerprint, so a row from another pack with the same type ID and version and a fitting shape is accepted. The caller passes `PACK_FINGERPRINT` to store calls; the [read interface](ONTOLOGY_READ_INTERFACE.md) does this.
- **Precision and scale** of decimals are not checked.
- **Generator input is untrusted.** Pack text reaches the output only as ASCII-escaped literals or validated names; names, descriptions and units are not written out. Tests cover a set of hostile strings, not every possible one.
- **Compatibility.** There is no compatibility promise for the generated code yet. `GENERATOR_VERSION` marks its form; pack changes are covered by [ONTOLOGY_COMPATIBILITY.md](ONTOLOGY_COMPATIBILITY.md).
