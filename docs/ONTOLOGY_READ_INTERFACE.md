# Ontology Read Interface, Version 1

**Status:** Library only (O3, 28 Nov 2026). An in-process Python interface, not a network service, a service client or a released SDK. Checked with synthetic data in this repository's tests; no outside application has used it.

## 1. Use

Generate the [typed module](ONTOLOGY_TYPED_CLIENT.md) for the pack, then pin a reader to it:

```python
from agora.ontology.reader import OntologyReader

reader = OntologyReader(store, retail_types, api_version="1",
                        policy=policy, audit=audit,
                        purpose="customer-support", retention="30d")
page = reader.query(retail_types.Customer, import_id, page_size=50)
one = reader.get(retail_types.Customer, record_key, import_id)
links = reader.links(link_type_id, link_type_version, one, direction="out")
other = reader.resolve(links.links[0].target)  # check links.links first
```

`policy`, `audit` and `api_version` are required arguments. `error_sink` is optional (see section 4). Build one reader for each purpose: its policy, audit writer, purpose and retention cannot be passed per call.

## 2. Calls

| Call | Store call | Returns |
|---|---|---|
| `get(cls, record_key, import_id)` | `get_object` | One `cls` object |
| `query(cls, import_id, filters=None, page_size=50, cursor=None)` | `query_objects` | `ObjectPage(objects, next_cursor)` |
| `links(link_type_id, link_type_version, obj, direction="both", page_size=50, cursor=None)` | `traverse_links` | `LinkPage(links, next_cursor)` |
| `resolve(ref)` | `get_object` | The object at one link end |

Filters, cursors and page sizes are those of the store calls (see [ONTOLOGY_OBJECT_STORE_DESIGN.md](ONTOLOGY_OBJECT_STORE_DESIGN.md)); filters name property IDs. A query page can be empty while `next_cursor` is set.

A `Link` has `link_id`, link type and version, `source` and `target` (`ObjectRef`), `status`, `valid_from`, `valid_to`, `created_at`, `supersedes_link_id`, `actor_id`, `reason`, `provenance` and `retraction`. **A link page includes superseded and retracted links.** Read `status`: `active`, `superseded` or `retracted`, as of the time the first page was requested.

## 3. What the reader enforces

- **Version.** Any `api_version` other than `"1"` is refused, as is a type module from another generator version.
- **One pack.** Every store call passes the module's `PACK_FINGERPRINT`, so results come from that pack's references. A class, or an object, from any other generated module is refused before the store is called, even when its type ID and version match. The class list is copied when the reader is built.
- **Whole pages.** If one object does not fit its type, the call raises and returns no part of the page. An unknown link status is also refused.
- **Errors.** A shape mismatch raises `OntologyError`, naming the property and carrying no value (with `error_sink`, the caller gets the redacted error instead).
- **Redacted failures (opt-in).** See section 4.

It adds no access: policy checks, audit entries and, under the protected defaults, the ingest-record check on objects are the store's.

## 4. Error detail

**By default, errors are detailed and are for trusted code only.** Messages from the store pass through unchanged. Different messages tell a caller whether policy refused a read, whether a record key exists in an import, and what check stored data failed. The chained cause of a policy refusal carries the policy's reason. Some failures leave the store as raw SQLite or JSON errors, and a JSON decoding error keeps the whole text it was decoding.

**With `error_sink`, a failed `get`, `query`, `links` or `resolve` tells the caller only that it failed.** Give the reader a callable that takes `(reference, error)`:

```python
reader = OntologyReader(store, retail_types, api_version="1", policy=policy,
                        audit=audit, error_sink=record_privately)
```

- Every failure after the request checks raises `OntologyReadError` (a subclass of `OntologyError`) with one fixed message and a random `reference`. A refusal by policy, a missing object, a bad filter or cursor, data that fails a check and an unexpected exception look the same.
- The error has no `__cause__` or `__context__`. The sink receives the original error with the same reference. Keep what the sink records away from the caller.
- If the sink raises, the caller still gets only `OntologyReadError`, and the detail is lost. The sink's own error is dropped.
- Three refusals keep their own messages, because they depend only on the caller's argument and the type module: a class or object from another module, a `resolve` argument that is not an `ObjectRef`, and a reference to a type the module lacks.
- Errors from building the reader are not redacted. `BaseException` subclasses such as `KeyboardInterrupt` pass through.

**What this does not hide:**

- Whether a call succeeded. A policy that lets a caller read some objects and not others shows that difference. So can `links`: its second check uses the sensitivity of the objects on the page, so a caller without that grant can see an empty page succeed and a non-empty one fail.
- How long a call took. Timing has not been measured or evened out.
- Anything from code in the same process. Tracebacks keep their frames, and the caller can hold the store. A service boundary must send only the fixed message and reference.
- Errors from the store, actions or writes called directly.

The review behind this section was by the authoring session, reading `get_object`, `query_objects` and `traverse_links` and what they call. It is not a security review.

## 5. Limits

- **The type module is trusted application code.** The reader checks the attributes it uses, not that the module is unedited generator output. A module whose fingerprint or classes were edited by hand can make the checks above meaningless.
- **Not a security boundary.** Code that holds the store can call it directly, so the pinning guards against mistakes, not against the calling process.
- **Links are read as stored.** `links` does not check that either end can still be read, apply the ingest-record check to link rows, or verify a link's cited sources again. `resolve` reads an end with the object checks.
- **`repr` is not redaction.** `ObjectRef` and `Link` leave record keys out of `repr`, and `Link` also leaves out reasons, actors, provenance and retraction details. A generated object leaves out property values, but its `provenance` still shows the record key and row ID. Cursors in a page are encoded, not encrypted, and carry a record key. All attributes stay readable; logs and serializers can expose them.
- `get_links`, writes and actions are not part of this interface.

## 6. Compatibility and deprecation

`READ_API_VERSION` covers the names, required arguments, return types and refusals in this document.

- Within version `1`, changes may add a method, an optional argument with a default that keeps today's behaviour, or a field on a returned record. Build those records only through the reader.
- Removing or renaming any of them, changing a meaning, accepting something this document says is refused, or adding a link status needs a new version number.
- A deprecated version is announced in this document before it is removed.

No second version exists, so this process has not been exercised. Pack changes are covered by [ONTOLOGY_COMPATIBILITY.md](ONTOLOGY_COMPATIBILITY.md); a changed pack has a new fingerprint and needs a newly generated module.
