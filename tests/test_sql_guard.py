import pytest

from mcp_server.bq_client import validate_readonly_sql


def test_plain_select_passes():
    assert validate_readonly_sql("SELECT product, COUNT(*) FROM t GROUP BY product;") .startswith("SELECT")


def test_with_clause_passes():
    assert validate_readonly_sql("WITH a AS (SELECT 1 AS x) SELECT * FROM a")


def test_keywords_inside_string_literals_are_fine():
    assert validate_readonly_sql("SELECT * FROM t WHERE narrative LIKE '%update my address%'")


def test_keywords_inside_comments_are_fine():
    assert validate_readonly_sql("SELECT 1 -- drop table later\n")


@pytest.mark.parametrize(
    "bad_sql",
    [
        "DROP TABLE t",
        "DELETE FROM t WHERE 1=1",
        "SELECT 1; DROP TABLE t",
        "INSERT INTO t VALUES (1)",
        "CREATE TABLE x AS SELECT 1",
        "SELECT * FROM t; SELECT 2",
        "EXPORT DATA OPTIONS(uri='gs://x') AS SELECT 1",
        "",
    ],
)
def test_writes_and_multi_statements_are_rejected(bad_sql):
    with pytest.raises(ValueError):
        validate_readonly_sql(bad_sql)
