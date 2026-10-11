from datetime import datetime, timezone

from src.common.schemas import Channel
from src.ingestion.news_vs_market import read_news_vs_market


def test_news_vs_market_normalizes_article_and_preserves_source_sentiment(tmp_path):
    path = tmp_path / "news.csv"
    path.write_text(
        "date,published_at,source,topic,title,description,url,compound,pos,neg,neu,sentiment_cat,source_weight\n"
        '2026-10-08,2026-10-08T17:04:24Z,CNBC,markets,"Market update","Stocks rise",https://example.com/a,0.5,0.4,0.1,0.5,positive,1.5\n',
        encoding="utf-8",
    )
    docs = list(read_news_vs_market(path))
    assert len(docs) == 1
    doc = docs[0]
    assert doc.source == "news_vs_market_2020"
    assert doc.channel == Channel.NEWS
    assert doc.timestamp == datetime(2026, 10, 8, 17, 4, 24, tzinfo=timezone.utc)
    assert doc.text == "Market update — Stocks rise"
    assert doc.raw_meta["publisher"] == "CNBC"
    assert doc.raw_meta["source_sentiment"]["compound"] == 0.5
    assert doc.raw_meta["entity_scope"] in {"company", "market"}


def test_news_vs_market_allows_missing_description(tmp_path):
    path = tmp_path / "news.csv"
    path.write_text(
        "date,published_at,source,topic,title,description,url,compound,pos,neg,neu,sentiment_cat,source_weight\n"
        '2026-10-08,2026-10-08T17:04:24Z,CNBC,markets,"Market update",,https://example.com/a,0.5,0.4,0.1,0.5,positive,1.5\n',
        encoding="utf-8",
    )
    docs = list(read_news_vs_market(path))
    assert len(docs) == 1
    assert docs[0].text == "Market update"
