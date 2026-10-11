"""Fix #4: one tweet tagged with several tickers must yield one document per ticker."""
from src.ingestion.historical_tweets import read_tweets
from src.ingestion.normalization import deduplicate

HEADER = "Date,Tweet,Stock Name,Company Name\n"


def write_csv(path, rows):
    path.write_text(HEADER + "".join(rows), encoding="utf-8")


def test_same_tweet_for_two_tickers_survives_dedupe(tmp_path):
    path = tmp_path / "tweets.csv"
    write_csv(path, [
        '2022-01-03 10:00:00+00:00,"Big day for EVs and chips",TSLA,"Tesla, Inc."\n',
        '2022-01-03 10:00:00+00:00,"Big day for EVs and chips",AMD,"Advanced Micro Devices, Inc."\n',
    ])
    docs = deduplicate(read_tweets(path))
    assert len(docs) == 2
    assert {d.raw_meta["ticker"] for d in docs} == {"TSLA", "AMD"}
    assert docs[0].id != docs[1].id


def test_true_duplicate_rows_still_collapse(tmp_path):
    path = tmp_path / "tweets.csv"
    row = '2022-01-03 10:00:00+00:00,"Tesla to the moon",TSLA,"Tesla, Inc."\n'
    write_csv(path, [row, row])
    assert len(deduplicate(read_tweets(path))) == 1


def test_ids_are_deterministic_across_runs(tmp_path):
    path = tmp_path / "tweets.csv"
    write_csv(path, ['2022-01-03 10:00:00+00:00,"Hello",AAPL,"Apple Inc."\n'])
    assert [d.id for d in read_tweets(path)] == [d.id for d in read_tweets(path)]


def test_unconfigured_tickers_are_skipped(tmp_path):
    path = tmp_path / "tweets.csv"
    write_csv(path, ['2022-01-03 10:00:00+00:00,"Nio deliveries up",NIO,"NIO Inc."\n'])
    assert list(read_tweets(path)) == []
