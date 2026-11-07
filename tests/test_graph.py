"""Upload -> graph -> draft pipeline, with a scripted 'model' that answers the way small
local models really do: mostly right, sometimes sloppy (wrong case, Twitter instead of
x, names instead of ids, shares that don't add up)."""
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from agora import scenario as scenario_mod
from agora.cli import main
from agora.graph import GraphStore
from agora.graph import build as gbuild, draft as gdraft, ingest as gingest, view as gview
from agora.graph.retrieve import FactIndex
from agora.llm import LLMConfig
from agora.llm.base import LLMBackend

DOC = """# Nutrivance Precision Probiotics

## Residential Community Sampling Campaign

Nutrivance Precision Probiotics (NPP) offers a free seven-day sample pack to residents of
premium apartment communities in Guntur and Vijayawada.

Registration begins only after approval from the apartment association. The form collects
only apartment name, area name and flat number.

Each sachet has 20 Billion CFU from 14 probiotic strains and 100 mg inulin. MRP is Rs 69 per sachet.
"""


class Scripted(LLMBackend):
    name = "scripted"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))
        self.prompts = []

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        p = messages[-1]["content"]
        self.prompts.append(p)
        if "design a knowledge graph" in p:
            return json.dumps({"entity_types": [{"name": "Brand"}, {"name": "Organization"},
                                                {"name": "Community"}, {"name": "Product"},
                                                {"name": "Place"}],
                               "relation_types": [{"name": "OFFERS"}, {"name": "REQUIRES"},
                                                  {"name": "LOCATED_IN"}]})
        if "Extract a knowledge graph" in p:
            return "Here is the graph:\n```json\n" + json.dumps({
                "entities": [
                    {"name": "Nutrivance Precision Probiotics", "type": "brand",
                     "description": "A probiotic brand.", "aliases": ["NPP"]},
                    {"name": "NPP", "type": "Brand", "description": "Short name"},
                    {"name": "Apartment Association", "type": "Organisation",
                     "description": "Approves campaigns in the complex."},
                    {"name": "Guntur", "type": "Place"},
                    {"name": "Free sample pack", "type": "Product", "description": "Seven sachets, free."},
                ],
                "relations": [
                    {"source": "NPP", "target": "Free sample pack", "type": "offers",
                     "fact": "NPP offers a free seven-day sample pack."},
                    {"source": "Free sample pack", "target": "Apartment Association",
                     "type": "REQUIRES", "fact": "Registration begins only after association approval."},
                    {"source": "Residents", "target": "Guntur", "type": "LIVES_IN",
                     "fact": "Residents live in premium apartments in Guntur."},
                ]}) + "\n```"
        if "Write the simulation framing" in p:
            return json.dumps({"name": "NPP sampling", "topic": "the free NPP probiotic sample",
                               "question": "How many flats register and buy?",
                               "context": "NPP offers a free 7-day sample to apartment residents after association approval.",
                               "days": "5"})
        if "Who reacts?" in p:
            return json.dumps({"segments": [
                {"name": "Young Parents", "share": 40, "persona": "Busy parents.", "stance": 0.2,
                 "stubbornness": 0.4, "activity": 0.5, "platforms": ["WhatsApp", "Twitter"],
                 "occupations": ["engineer"], "age": [28, 40]},
                {"name": "Seniors", "share": 30, "persona": "Retired residents.", "stance": "-0.2",
                 "platforms": "whatsapp", "age": [70, 60]},
                {"name": "young parents", "share": 10, "persona": "duplicate"},
                {"name": "Students", "share": 30, "persona": "College students.", "stance": 5,
                 "platforms": ["reddit", "instagram"]}]})
        if "actively speak or decide" in p:
            return json.dumps({"accounts": [
                {"id": "NPP Official", "name": "Nutrivance", "persona": "Brand account.",
                 "stance": 0.9, "platforms": ["twitter", "whatsapp"]},
                {"name": "Association Committee", "persona": "Committee that approves.",
                 "stance": 0, "decides": True, "platforms": ["whatsapp"]}]})
        if "Where do people talk" in p:
            return json.dumps({"spaces": [
                {"platform": "WhatsApp", "name": "Lakeview Residents", "size": 250},
                {"platform": "reddit", "name": "guntur", "size": "300"},
                {"platform": "x", "name": "ignored"}],
                "actions": [{"name": "Register", "label": "register the flat", "open_day": 1,
                             "close_day": 2},
                            {"name": "buy", "label": "buy a pack", "open_day": 3, "close_day": 5,
                             "requires": "register"},
                            {"name": "complain", "requires": "nonexistent"}]})
        if "Build the timeline" in p:
            return json.dumps({"events": [
                {"day": 0, "type": "news", "text": "NPP proposes free sampling."},
                {"day": 1, "type": "decision", "name": "Approval",
                 "question": "Approve the free sample programme?", "voters": ["Association Committee"]},
                {"day": 1, "type": "post", "account": "npp_official", "platform": "whatsapp",
                 "text": "Register now!", "if_decision": "approval"},
                {"day": 2, "type": "post", "account": "ghost", "text": "dropped"},
                {"day": 3, "type": "decision", "name": "x", "voters": []}]})
        if "Create one realistic person" in p:
            n = len([q for q in self.prompts if "Create one realistic person" in q])
            if n % 5 == 0:
                return "sorry I cannot"          # some calls fail -> template fills the gap
            return json.dumps({"name": f"Person{n} Surname", "age": 33, "occupation": "teacher",
                               "persona": "Teaches at a local school and reads labels carefully before buying."})
        return "{}"


@pytest.fixture
def gs(tmp_path):
    (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
    g = GraphStore(tmp_path / "graph.db")
    gingest.ingest(g, tmp_path / "proj", [tmp_path / "doc.md"], size=300, overlap=50)
    yield g
    g.close()


# ------------------------------------------------------------------ ingest
def _docx(path: Path, paras: list[str]):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}<w:tbl><w:tr><w:tc><w:p><w:r><w:t>MRP</w:t></w:r></w:p>'
           '</w:tc><w:tc><w:p><w:r><w:t>Rs 69</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


def _pdf(path: Path, text: str):
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)
    path.write_bytes(bytes(out))


def test_readers(tmp_path):
    _docx(tmp_path / "a.docx", ["Hello Guntur", "Second para"])
    assert "Hello Guntur" in gingest.read_text(tmp_path / "a.docx")
    assert "MRP | Rs 69" in gingest.read_text(tmp_path / "a.docx")
    _pdf(tmp_path / "a.pdf", "Free sample for Lakeview residents")
    assert "Free sample for Lakeview residents" in gingest.read_text(tmp_path / "a.pdf")
    (tmp_path / "a.html").write_text("<html><head><script>x=1</script></head><body><h1>Title</h1>"
                                     "<p>Body text</p></body></html>")
    t = gingest.read_text(tmp_path / "a.html")
    assert "Title" in t and "Body text" in t and "x=1" not in t
    (tmp_path / "a.csv").write_text("flat,registered\n101,yes\n102,no\n")
    assert "flat: 101; registered: yes" in gingest.read_text(tmp_path / "a.csv")
    with pytest.raises(gingest.IngestError):
        gingest.read_text(tmp_path / "a.exe")


def test_chunking_covers_text():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(20))
    parts = gingest.chunk(text, size=500, overlap=80)
    assert all(len(p) <= 600 for p in parts)
    for i in range(20):
        assert any(f"Paragraph {i}." in p for p in parts)


def test_ingest_copies_and_dedupes(tmp_path, gs):
    proj = tmp_path / "proj"
    assert (proj / "sources" / "doc.md").exists()
    again = gingest.ingest(gs, proj, [tmp_path / "doc.md"])
    assert again[0]["skipped"]


# ------------------------------------------------------------------ graph
def test_build_merges_aliases_and_cleans_types(gs):
    llm = Scripted()
    st = gbuild.build(gs, llm, "predict registrations")
    names = {r[0]: r[1] for r in gs.rows("SELECT name, type FROM nodes")}
    assert "Nutrivance Precision Probiotics" in names and "NPP" not in names   # alias folded
    assert names["Nutrivance Precision Probiotics"] == "Brand"                 # case fixed
    assert names["Apartment Association"] == "Concept"                         # unknown type
    assert names["Residents"] == "Concept"                                     # created from relation
    types = {r[0] for r in gs.rows("SELECT type FROM edges")}
    assert "OFFERS" in types and "RELATED_TO" in types                         # LIVES_IN -> RELATED_TO
    assert st["nodes"] >= 5 and st["edges"] >= 3
    # resume: nothing pending, no new model calls
    n = len(llm.prompts)
    gbuild.build(gs, llm, "predict registrations")
    assert len(llm.prompts) == n


def test_build_without_model(gs):
    st = gbuild.build(gs, None, "anything")
    assert st["nodes"] > 0


def test_viewer_is_offline(gs, tmp_path):
    gbuild.build(gs, Scripted(), "goal")
    html = gview.render(gs, "Test <graph>")
    assert "<script src" not in html and "cdn" not in html.lower()
    assert "Nutrivance Precision Probiotics" in html and "Test &lt;graph>" in html
    gbuild.export(gs, tmp_path)
    data = json.loads((tmp_path / "graph.json").read_text())
    assert data["nodes"] and data["links"]


def test_fact_retrieval(gs):
    gbuild.build(gs, Scripted(), "goal")
    idx = FactIndex.from_graph(gs)
    top = idx.search("does the association need to approve registration", k=1)
    assert top and "approval" in top[0].lower()
    assert idx.search("zzzz qqqq") == []


# ------------------------------------------------------------------ draft
def test_draft_cleans_sloppy_answers(gs):
    llm = Scripted()
    gbuild.build(gs, llm, "goal")
    sc = gdraft.draft(gs, llm, "How many flats register?", llm_agents=10, crowd_agents=200)
    parsed = scenario_mod.from_dict(json.loads(json.dumps(sc)))
    assert parsed.rounds == 5 * 6
    segs = {s.name: s for s in parsed.segments}
    assert set(segs) == {"young_parents", "seniors", "students"}           # duplicate dropped
    assert abs(sum(s.share for s in parsed.segments) - 1) < 0.01             # shares normalised
    assert segs["young_parents"].platforms == ["whatsapp", "x"]              # Twitter -> x
    assert segs["students"].stance_mean == 1.0                               # clamped
    assert segs["seniors"].age == (60, 70)                                   # swapped
    ids = {a.id for a in parsed.accounts if a.segment != "entities"}
    assert ids == {"npp_official", "association_committee"}
    poll = next(e for e in parsed.events if e.type == "poll")
    assert poll.voters == ["association_committee"]                          # name -> id
    post = next(e for e in parsed.events if e.type == "post")
    assert post.when == {"poll": "approval", "result": "yes"}
    assert not any(e.account == "ghost" for e in parsed.events)
    convs = {c.name: c for c in parsed.conversions}
    assert set(convs) == {"register", "buy", "complain"}
    assert convs["buy"].requires == ["register"] and convs["complain"].requires == []
    assert convs["register"].when == {"poll": "approval", "result": "yes"}
    assert {s.name for s in parsed.spaces} == {"Lakeview Residents", "r/guntur"}
    assert 6 <= len(parsed.voices) <= 9                                      # some persona calls failed
    assert all(v["name"].startswith("Person") and " " not in v["name"] for v in parsed.voices)


def test_draft_with_no_usable_answers_still_valid(gs):
    gbuild.build(gs, None, "goal")
    sc = gdraft.draft(gs, None, "Will people like it?", llm_agents=5, crowd_agents=100)
    scenario_mod.from_dict(json.loads(json.dumps(sc)))


def test_voices_become_llm_agents(tmp_path, gs):
    from agora.sim import population
    llm = Scripted()
    gbuild.build(gs, llm, "goal")
    sc = scenario_mod.from_dict(gdraft.draft(gs, llm, "goal", llm_agents=10, crowd_agents=50))
    w, _, _ = population.build(sc)
    voiced = [a for a in w.agents if a.attrs.get("voice")]
    assert len(voiced) == len(sc.voices)
    assert all("reads labels" in a.persona for a in voiced)


# ------------------------------------------------------------------ end to end
def test_create_then_run(tmp_path, capsys):
    doc = tmp_path / "campaign.md"
    doc.write_text(DOC, encoding="utf-8")
    proj = tmp_path / "p"
    rc = main(["create", str(proj), "--docs", str(doc), "--prompt", "How many flats register?",
               "--mock", "--llm-agents", "6", "--crowd", "150"])
    assert rc == 0
    for f in ("scenario.yaml", "graph.db", "graph.html", "graph.json", "graph.graphml",
              "prompt.txt", "sources/campaign.md"):
        assert (proj / f).exists(), f
    d = yaml.safe_load((proj / "scenario.yaml").read_text())
    assert d["population"] == {"llm_agents": 6, "crowd_agents": 150}
    assert main(["run", str(proj), "--mock"]) == 0
    assert main(["status", str(proj)]) == 0
    assert "rounds" in capsys.readouterr().out
    assert main(["create", str(proj), "--docs", str(doc), "--prompt", "x", "--mock"]) == 1


def test_entity_agents_from_graph(gs):
    llm = Scripted()
    gbuild.build(gs, llm, "goal")
    sc = gdraft.draft(gs, llm, "How many flats register?", llm_agents=6, crowd_agents=100, entity_limit=5)
    parsed = scenario_mod.from_dict(json.loads(json.dumps(sc)))
    ents = [a for a in parsed.accounts if a.segment == "entities"]
    assert ents, "people/organisations in the graph should become agents"
    names = {a.name for a in ents}
    assert "Guntur" not in names                    # places are not agents
    assert all(a.profile.get("source") for a in ents)
    assert len({a.id for a in parsed.accounts}) == len(parsed.accounts)


class ElectionScripted(Scripted):
    def _complete(self, messages, **kw):
        p = messages[-1]["content"]
        if "Write the simulation framing" in p:
            return json.dumps({"name": "city vote", "topic": "the mayoral election", "question": "Who wins?",
                               "context": "Three candidates.", "days": 5,
                               "options": ["Rao", "Okafor", "rao", "Pillai"]})
        if "Who reacts?" in p:
            return json.dumps({"segments": [
                {"name": "renters", "share": 0.5, "persona": "Renters", "leaning": {"RAO": 0.5, "Okafor": -0.3}},
                {"name": "owners", "share": 0.5, "persona": "Owners", "leaning": {"Okafor": 0.4, "Ghost": 1}}]})
        return super()._complete(messages, **kw)


def test_draft_detects_a_choice(gs):
    llm = ElectionScripted()
    gbuild.build(gs, llm, "goal")
    sc = gdraft.draft(gs, llm, "Who will win the mayoral election?", llm_agents=4, crowd_agents=60,
                      entity_limit=0, rich_personas=False)
    parsed = scenario_mod.from_dict(json.loads(json.dumps(sc)))
    assert parsed.choice.options == ["Rao", "Okafor", "Pillai"]
    assert {g.name: g for g in parsed.segments}["renters"].leaning["Rao"] == 0.5
    seg = {g.name: g for g in parsed.segments}
    assert seg["renters"].leaning["Okafor"] == -0.3
    assert "Ghost" not in seg["owners"].leaning
    assert parsed.choice.open_round < parsed.rounds



def test_personas_carry_their_own_view_and_set_the_group():
    from agora.graph import draft

    class Fake:
        i = 0
        def generate_json(self, messages, **kw):
            Fake.i += 1
            v = [-0.6, 0.0, 0.7][Fake.i % 3]
            return {"name": f"P{Fake.i}", "age": 40, "occupation": "x",
                    "persona": "A person with views.", "stance": v}
    sc = {"population": {"llm_agents": 6}, "context": "c", "topic": "the offer",
          "segments": [{"name": "a", "share": 1.0, "persona": "p", "age": [30, 50], "stance": {"mean": 0.8, "sd": 0.3}}]}
    vs = draft.personas(Fake(), sc, 1, lambda m: None)
    assert {v["stance"] for v in vs} == {-0.6, 0.0, 0.7}
    assert abs(sc["segments"][0]["stance"]["mean"] - 0.03) < 0.05       # from the people, not the draft
