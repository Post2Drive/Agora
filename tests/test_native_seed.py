"""The relationship seed declaration: strict, closed, fingerprinted, and side-effect free."""
import copy

import pytest
import yaml

from agora.society import SeedError, SocietyStore, load_seed, parse_seed
from agora.society.seed import SEED_FORMAT

FP = "ab" * 32


def _doc():
    return {
        "format": SEED_FORMAT, "pack_fingerprint": FP, "import_id": "crm-2026-11",
        "link_types": [{"link_type_id": "knows", "direction": "both", "trust": 0.6, "familiarity": 0.3},
                       {"link_type_id": "reports_to", "direction": "source_to_target", "trust": 0.5,
                        "familiarity": 0.5}],
        "records": [{"record_key": "C-1", "agent": 3}, {"record_key": "C-2", "agent": 0}],
    }


def _bad(mutate, match=None):
    d = _doc()
    mutate(d)
    with pytest.raises(SeedError, match=match):
        parse_seed(d)


def test_valid_seed_parses():
    s = parse_seed(_doc())
    assert s.pack_fingerprint == FP and s.import_id == "crm-2026-11"
    assert [r.link_type_id for r in s.link_types] == ["knows", "reports_to"]
    assert s.records == (("C-1", 3), ("C-2", 0))
    assert s.agent_of("C-1") == 3 and s.agent_of("C-9") is None
    assert s.rule_for("knows").trust == 0.6 and s.rule_for("nope") is None


def test_hash_is_stable_and_binds_every_part():
    base = parse_seed(_doc()).seed_hash
    assert parse_seed(_doc()).seed_hash == base
    changes = [
        lambda d: d.update(pack_fingerprint="cd" * 32),
        lambda d: d.update(import_id="other"),
        lambda d: d["link_types"][0].update(trust=0.7),
        lambda d: d["link_types"][0].update(familiarity=0.4),
        lambda d: d["link_types"][0].update(direction="source_to_target"),
        lambda d: d["link_types"][0].update(link_type_id="friends"),
        lambda d: d["records"][0].update(agent=9),
        lambda d: d["records"][0].update(record_key="C-9"),
    ]
    for change in changes:
        d = _doc()
        change(d)
        assert parse_seed(d).seed_hash != base


def test_hash_depends_on_record_order():
    d = _doc()
    d["records"].reverse()
    assert parse_seed(d).seed_hash != parse_seed(_doc()).seed_hash


def test_closed_set_of_fields():
    _bad(lambda d: d.update(extra=1), "unknown")
    _bad(lambda d: d["link_types"][0].update(extra=1), "unknown")
    _bad(lambda d: d["records"][0].update(extra=1), "unknown")
    _bad(lambda d: d.pop("import_id"), "missing")
    _bad(lambda d: d["link_types"][0].pop("trust"), "missing")
    _bad(lambda d: d["records"][0].pop("agent"), "missing")
    with pytest.raises(SeedError):
        parse_seed([1, 2])
    with pytest.raises(SeedError):
        parse_seed(None)


def test_format_and_fingerprint():
    _bad(lambda d: d.update(format="x"), "format")
    for bad in ("AB" * 32, "ab" * 31, "ab" * 33, "zz" * 32, 5, None):
        _bad(lambda d, b=bad: d.update(pack_fingerprint=b), "fingerprint")


def test_ranges_and_types():
    for field in ("trust", "familiarity"):
        for bad in (-0.1, 1.1, True, "0.5", None, float("nan")):
            _bad(lambda d, f=field, b=bad: d["link_types"][0].update({f: b}), field)
    for ok in (0, 1, 0.0, 1.0):
        d = _doc()
        d["link_types"][0]["trust"] = ok
        parse_seed(d)
    _bad(lambda d: d["link_types"][0].update(direction="either"), "direction")


def test_text_fields():
    for bad in ("", " x", "x ", "a\nb", "x" * 201, 5, None):
        _bad(lambda d, b=bad: d.update(import_id=b), "import_id")
        _bad(lambda d, b=bad: d["records"][0].update(record_key=b), "record_key")
        _bad(lambda d, b=bad: d["link_types"][0].update(link_type_id=b), "link_type_id")


def test_agent_ids():
    for bad in (-1, True, 1.0, "3", None):
        _bad(lambda d, b=bad: d["records"][0].update(agent=b), "agent")


def test_duplicates_refused():
    _bad(lambda d: d["link_types"].append(copy.deepcopy(d["link_types"][0])), "twice")
    _bad(lambda d: d["records"].append({"record_key": "C-1", "agent": 7}), "mapped twice")
    _bad(lambda d: d["records"].append({"record_key": "C-7", "agent": 3}), "more than one record")


def test_lists_must_be_non_empty_lists():
    _bad(lambda d: d.update(link_types=[]), "non-empty")
    _bad(lambda d: d.update(records=[]), "non-empty")
    _bad(lambda d: d.update(records={"a": 1}), "non-empty")


def test_agents_must_exist_when_given():
    parse_seed(_doc(), agents={0, 3})
    with pytest.raises(SeedError, match="not an agent"):
        parse_seed(_doc(), agents={0})


def test_size_limits(monkeypatch):
    from agora.society import seed
    monkeypatch.setattr(seed, "MAX_RECORDS", 1)
    _bad(lambda d: None, "more than 1")
    monkeypatch.setattr(seed, "MAX_RECORDS", 100)
    monkeypatch.setattr(seed, "MAX_LINK_TYPES", 1)
    _bad(lambda d: None, "more than 1")


def test_load_seed_reads_a_file_and_reports_bad_files(tmp_path):
    p = tmp_path / "relationship_seed.yaml"
    p.write_text(yaml.safe_dump(_doc()), encoding="utf-8")
    assert load_seed(p).seed_hash == parse_seed(_doc()).seed_hash
    with pytest.raises(SeedError, match="cannot read"):
        load_seed(tmp_path / "missing.yaml")
    p.write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(SeedError, match="cannot read"):
        load_seed(p)
    p.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(SeedError, match="cannot read"):
        load_seed(p)


@pytest.mark.parametrize("old,new", [
    ("import_id: crm-2026-11\n", "import_id: crm-2026-11\nimport_id: other\n"),
    ("  trust: 0.6\n", "  trust: 0.6\n  trust: 0.9\n"),
    ("- agent: 3\n", "- agent: 3\n  agent: 4\n"),
])
def test_load_seed_refuses_a_repeated_key(tmp_path, old, new):
    text = yaml.safe_dump(_doc())
    assert old in text
    p = tmp_path / "relationship_seed.yaml"
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(SeedError, match="duplicate key"):
        load_seed(p)


@pytest.mark.parametrize("text", ["[" * 100_000, "a: 2026-13-45\n"])
def test_load_seed_reports_parser_crashes_as_seed_errors(tmp_path, text):
    p = tmp_path / "relationship_seed.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(SeedError, match="cannot read"):
        load_seed(p)


def test_load_seed_does_not_construct_python_objects(tmp_path):
    p = tmp_path / "relationship_seed.yaml"
    p.write_text("a: !!python/object/apply:os.getcwd []\n", encoding="utf-8")
    with pytest.raises(SeedError, match="cannot read"):
        load_seed(p)


@pytest.mark.parametrize("bad", ["a\ud800", "a\x7fb", "a\x85b"])
def test_surrogates_and_other_controls_are_refused(bad):
    _bad(lambda d: d.update(import_id=bad), "import_id")
    _bad(lambda d: d["records"][0].update(record_key=bad), "record_key")
    _bad(lambda d: d["link_types"][0].update(link_type_id=bad), "link_type_id")


def test_agent_id_upper_bound():
    d = _doc()
    d["records"][0]["agent"] = 2**63 - 1
    parse_seed(d)
    for bad in (2**63, 10**5000):
        _bad(lambda d, b=bad: d["records"][0].update(agent=b), "agent")


def test_negative_zero_hashes_like_zero():
    a, b = _doc(), _doc()
    a["link_types"][0]["trust"], b["link_types"][0]["trust"] = 0, -0.0
    assert parse_seed(a).seed_hash == parse_seed(b).seed_hash


def test_parsing_changes_nothing():
    soc = SocietyStore(":memory:")
    before = soc.digest()
    parse_seed(_doc())
    assert soc.digest() == before
