"""Versioned in-process read interface that returns generated ontology types.

See docs/ONTOLOGY_READ_INTERFACE.md. A reader is pinned to one interface
version, one generated type module (and so one pack fingerprint), one policy,
one audit writer and one purpose and retention. It calls ``get_object``,
``query_objects`` and ``traverse_links`` on the ontology store and adds no
access of its own. It is not a network service.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

from .registry import OntologyError
from .store import OntologyObjectStore
from .typed import GENERATOR_VERSION


READ_API_VERSION = "1"
_LINK_STATUSES = frozenset({"active", "superseded", "retracted"})
_Result = TypeVar("_Result")


class OntologyReadError(OntologyError):
    """A read failed in a reader built with ``error_sink``.

    The message is the same for every cause. ``reference`` is random and matches
    the one the sink received with the original error.
    """

    def __init__(self, reference: str):
        super().__init__(f"ontology read failed (reference {reference})")
        self.reference = reference


@dataclass(frozen=True)
class ObjectRef:
    """One pinned object identity. ``record_key`` is left out of ``repr``."""

    type_id: str
    type_version: str
    import_id: str
    record_key: str = field(repr=False)


@dataclass(frozen=True)
class Link:
    """One stored link record. Read ``status`` before using a link as current.

    ``provenance`` and ``retraction`` are fresh dictionaries from the store; the
    reader does not interpret them.
    """

    link_id: str
    link_type_id: str
    link_type_version: str
    source: ObjectRef
    target: ObjectRef
    status: str
    valid_from: str
    valid_to: str | None
    created_at: str
    supersedes_link_id: str | None
    actor_id: str = field(repr=False)
    reason: str = field(repr=False)
    provenance: Mapping[str, Any] = field(repr=False, compare=False)
    retraction: Mapping[str, Any] | None = field(repr=False, compare=False)


@dataclass(frozen=True)
class ObjectPage:
    """One query page. It can be empty while ``next_cursor`` is not ``None``."""

    objects: tuple[Any, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class LinkPage:
    links: tuple[Link, ...]
    next_cursor: str | None


def _ref(endpoint: Mapping[str, Any]) -> ObjectRef:
    return ObjectRef(
        type_id=endpoint["type_id"], type_version=endpoint["type_version"],
        import_id=endpoint["import_id"], record_key=endpoint["record_key"],
    )


class OntologyReader:
    """Read typed objects and links for exactly one pack fingerprint."""

    def __init__(
        self, store: OntologyObjectStore, types: Any, *, api_version: str,
        policy: Any, audit: Any, purpose: str | None = None, retention: str | None = None,
        error_sink: Callable[[str, Exception], None] | None = None,
    ):
        if api_version != READ_API_VERSION:
            raise OntologyError("unsupported read interface version")
        if getattr(types, "GENERATOR_VERSION", None) != GENERATOR_VERSION:
            raise OntologyError("the type module comes from another generator version; generate it again")
        fingerprint = getattr(types, "PACK_FINGERPRINT", None)
        classes = getattr(types, "OBJECT_TYPES", None)
        error = getattr(types, "InstanceError", None)
        if (
            type(fingerprint) is not str or not fingerprint
            or not isinstance(classes, Mapping) or not classes
            or not (isinstance(error, type) and issubclass(error, ValueError))
        ):
            raise OntologyError("not a generated type module")
        if error_sink is not None and not callable(error_sink):
            raise OntologyError("error_sink must be callable")
        self._error_sink = error_sink
        self._store = store
        self._pack_fingerprint = fingerprint
        # Copied, so a later change to the module does not change this reader.
        self._classes = dict(classes)
        self._instance_error = error
        self._access = {"policy": policy, "audit": audit}
        self._privacy = {"purpose": purpose, "retention": retention}

    @property
    def pack_fingerprint(self) -> str:
        return self._pack_fingerprint

    def _require_class(self, cls: Any) -> None:
        # Identity, not name: a class generated from another pack can carry the
        # same type ID and version.
        if not any(candidate is cls for candidate in self._classes.values()):
            raise OntologyError("the class is not an object type of this reader's type module")

    def _guarded(self, read: Callable[[], _Result]) -> _Result:
        """Run one read. With a sink, no detail of a failure reaches the caller."""
        sink = self._error_sink
        if sink is None:
            return read()
        try:
            return read()
        except Exception as exc:
            reference = uuid.uuid4().hex
            try:
                sink(reference, exc)
            except Exception:
                # A failing sink must not put the detail back in front of the caller.
                pass
        # Raised outside the handler, so neither __cause__ nor __context__ holds
        # the original. ``from None`` alone would keep it in __context__.
        raise OntologyReadError(reference)

    def _typed(self, cls: Any, instance: Mapping[str, Any]) -> Any:
        try:
            return cls.from_instance(instance)
        except self._instance_error as exc:
            # Generated messages name properties and never carry values.
            raise OntologyError(f"stored object does not fit the generated type: {exc}") from None

    def get(self, cls: Any, record_key: str, import_id: str) -> Any:
        """Return one object of ``cls`` from an exact import."""
        self._require_class(cls)
        return self._guarded(lambda: self._typed(cls, self._store.get_object(
            self._pack_fingerprint, cls.TYPE_ID, cls.TYPE_VERSION, record_key, import_id,
            **self._access, **self._privacy,
        )))

    def query(
        self, cls: Any, import_id: str, filters: Mapping[str, Any] | None = None, *,
        page_size: int = 50, cursor: str | None = None,
    ) -> ObjectPage:
        """Return one page of ``cls`` objects. Filters are those of ``query_objects``.

        If any object of the page does not fit the type, no part of it is returned.
        """
        self._require_class(cls)
        return self._guarded(
            lambda: self._query_page(cls, import_id, filters, page_size, cursor))

    def _query_page(
        self, cls: Any, import_id: str, filters: Mapping[str, Any] | None,
        page_size: int, cursor: str | None,
    ) -> ObjectPage:
        page = self._store.query_objects(
            self._pack_fingerprint, cls.TYPE_ID, cls.TYPE_VERSION, import_id,
            {} if filters is None else filters, page_size, cursor,
            **self._access, **self._privacy,
        )
        return ObjectPage(
            objects=tuple(self._typed(cls, item) for item in page["objects"]),
            next_cursor=page["next_cursor"],
        )

    def links(
        self, link_type_id: str, link_type_version: str, obj: Any, *,
        direction: str = "both", page_size: int = 50, cursor: str | None = None,
    ) -> LinkPage:
        """Return one page of links next to a typed object read through this module.

        The page includes superseded and retracted links.
        """
        self._require_class(type(obj))
        return self._guarded(lambda: self._link_page(
            link_type_id, link_type_version, obj, direction, page_size, cursor))

    def _link_page(
        self, link_type_id: str, link_type_version: str, obj: Any,
        direction: str, page_size: int, cursor: str | None,
    ) -> LinkPage:
        endpoint = {
            "project_id": self._store.project_id, "pack_fingerprint": self._pack_fingerprint,
            "type_id": obj.TYPE_ID, "type_version": obj.TYPE_VERSION,
            "import_id": obj.provenance.import_id, "record_key": obj.provenance.record_key,
        }
        page = self._store.traverse_links(
            self._pack_fingerprint, link_type_id, link_type_version, endpoint,
            obj.provenance.import_id, page_size, cursor, direction=direction, **self._access,
        )
        result = []
        for item in page["links"]:
            if item["status"] not in _LINK_STATUSES:
                raise OntologyError("stored link has a status this interface version does not know")
            result.append(Link(
                link_id=item["link_id"], link_type_id=item["link_type_id"],
                link_type_version=item["link_type_version"],
                source=_ref(item["source"]), target=_ref(item["target"]), status=item["status"],
                valid_from=item["valid_from"], valid_to=item["valid_to"],
                created_at=item["created_at"], supersedes_link_id=item["supersedes_link_id"],
                actor_id=item["actor_id"], reason=item["reason"],
                provenance=item["provenance"], retraction=item["retraction"],
            ))
        return LinkPage(links=tuple(result), next_cursor=page["next_cursor"])

    def resolve(self, ref: ObjectRef) -> Any:
        """Read the object a link end points to, as its generated type."""
        if not isinstance(ref, ObjectRef):
            raise OntologyError("resolve needs an ObjectRef")
        cls = self._classes.get((ref.type_id, ref.type_version))
        if cls is None:
            raise OntologyError("the type module has no such object type and version")
        return self.get(cls, ref.record_key, ref.import_id)
