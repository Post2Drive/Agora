from datetime import date

import pytest

from agora import cutoff, events, news_rss

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Candidate faces corruption claims</title>
<link>https://news.example.com/a</link>
<pubDate>Tue, 22 Oct 2024 09:30:00 GMT</pubDate>
<description>&lt;p&gt;Allegations about <b>campaign</b> funds.&lt;/p&gt;</description></item>
<item><title>Weather update</title><link>https://news.example.com/b</link>
<pubDate>Tue, 22 Oct 2024 10:00:00 GMT</pubDate><description>Rain.</description></item>
<item><title>Election results certified</title><link>https://news.example.com/c</link>
<pubDate>Wed, 06 Nov 2024 12:00:00 GMT</pubDate><description>Campaign ends.</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Campaign rally draws crowds</title>
<link href="https://atom.example.com/x"/>
<published>2024-10-24T18:00:00Z</published>
<summary>Crowd size in Ohio.</summary></entry>
</feed>"""


def test_parses_rss_items_with_dates_and_clean_text():
    items = news_rss.parse_feed(RSS)
    assert len(items) == 3
    assert items[0]["published"] == "2024-10-22"
    assert items[0]["summary"] == "Allegations about campaign funds."
    assert items[0]["url"] == "https://news.example.com/a"


def test_parses_atom_entries():
    items = news_rss.parse_feed(ATOM)
    assert items == [{"title": "Campaign rally draws crowds", "url": "https://atom.example.com/x",
                      "published": "2024-10-24", "summary": "Crowd size in Ohio."}]


def test_select_applies_keyword_window_and_cutoff():
    items = news_rss.parse_feed(RSS) + news_rss.parse_feed(ATOM)
    got = news_rss.select(items, ["corruption", "campaign"], cutoff=date(2024, 10, 26))
    titles = [i["title"] for i in got]
    assert "Candidate faces corruption claims" in titles
    assert "Campaign rally draws crowds" in titles
    assert "Election results certified" not in titles      # after the cutoff
    assert "Weather update" not in titles                   # no keyword


def test_select_drops_items_without_a_date():
    items = [{"title": "campaign", "url": "", "published": "", "summary": ""}]
    assert news_rss.select(items, ["campaign"]) == []


def test_pull_writes_candidates_once_and_reports_bad_feeds(tmp_path):
    cutoff.set_cutoff(tmp_path, "2024-10-26")
    fake = {"https://news.example.com/rss": RSS, "https://atom.example.com/feed": ATOM}

    def get(url):
        if url not in fake:
            raise OSError("unreachable")
        return fake[url]

    feeds = ["https://news.example.com/rss", "https://atom.example.com/feed", "https://down.example.com/x",
             "ftp://files.example.com/rss"]
    r = news_rss.pull(tmp_path, feeds, ["corruption", "campaign"], get=get)
    assert {a["published"] for a in r["added"]} == {"2024-10-22", "2024-10-24"}
    assert len(r["errors"]) == 2
    assert {e["feed"] for e in r["errors"]} == {"https://down.example.com/x", "ftp://files.example.com/rss"}

    again = news_rss.pull(tmp_path, feeds, ["corruption", "campaign"], get=get)
    assert again["added"] == []                             # nothing new the second time
    assert len(news_rss.read_candidates(tmp_path)) == 2


def test_pull_needs_a_keyword(tmp_path):
    with pytest.raises(ValueError, match="keyword"):
        news_rss.pull(tmp_path, ["https://x.example.com/rss"], ["  "], get=lambda u: RSS)


def test_approve_moves_a_candidate_into_the_queue_with_the_same_id(tmp_path):
    cutoff.set_cutoff(tmp_path, "2024-10-26")
    fake = {"https://news.example.com/rss": RSS}
    news_rss.pull(tmp_path, ["https://news.example.com/rss"], ["corruption"], get=lambda u: fake[u])
    cand = news_rss.read_candidates(tmp_path)[0]
    r = news_rss.approve(tmp_path, cand["id"])
    assert r["id"] == cand["id"] and not r["duplicate"]
    queued = events.read(tmp_path)
    assert queued[0]["published"] == "2024-10-22"
    assert queued[0]["source"] == "news.example.com"
    assert news_rss.approve(tmp_path, cand["id"])["duplicate"] is True


def test_approve_unknown_id_says_so(tmp_path):
    with pytest.raises(ValueError, match="No candidate"):
        news_rss.approve(tmp_path, "nope")
