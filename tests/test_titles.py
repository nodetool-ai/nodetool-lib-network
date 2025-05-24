import importlib
import sys
import types
import nodetool.nodes.lib.network.http as http


def test_get_request_title():
    assert http.GetRequest.get_title() == "GET Request"


def test_fetch_rss_feed_title(monkeypatch):
    dummy = types.SimpleNamespace(parse=lambda url: types.SimpleNamespace(feed={}, entries=[]))
    monkeypatch.setitem(sys.modules, "feedparser", dummy)
    rss = importlib.import_module("nodetool.nodes.lib.network.rss")
    importlib.reload(rss)
    assert rss.FetchRSSFeed.get_title() == "Fetch RSS Feed"
