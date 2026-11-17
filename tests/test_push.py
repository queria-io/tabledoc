from __future__ import annotations

import gzip
import hashlib
import json

import pytest

from tabledoc.build import Options, build
from tabledoc.git import https
from tabledoc.push import PushError, Reply, files_url, push
from tabledoc.report import Report


def test_files_url_drops_the_query():
    url = "https://queria.io/api/datasets/a/b/metadata?version=V1"
    assert files_url(url, "ab") == "https://queria.io/api/datasets/a/b/metadata/files/ab"


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("git@github.com:queria-io/dataset-boj.git", "https://github.com/queria-io/dataset-boj"),
        ("https://x-access-token:t@github.com/queria-io/dataset-boj.git", "https://github.com/queria-io/dataset-boj"),
        ("ssh://git@github.com/queria-io/dataset-boj", "https://github.com/queria-io/dataset-boj"),
        ("https://github.com/queria-io/dataset-boj/", "https://github.com/queria-io/dataset-boj"),
    ],
)
def test_https(remote, expected):
    assert https(remote) == expected


def built(write):
    root = write(
        {
            "tabledoc.yml": "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\nname: d\n",
            "README.md": "Hello\n",
        }
    )
    return root, build(Options(root, with_source=False), Report()).document


def test_sends_the_missing_files_then_again(write):
    root, document = built(write)
    sha = hashlib.sha256(b"Hello\n").hexdigest()
    calls = []

    def put(url, body, headers):
        calls.append((url, body, headers))
        if len(calls) == 1:
            return Reply(409, {"error": "missing_files", "missing": [sha]})
        return Reply(201 if url.endswith("V1") else 201, {"revision": 1, "created": True})

    reply = push("https://q/api/datasets/a/d/metadata?version=V1", document, root, "T", put=put, log=lambda m: None)
    assert reply.status == 201
    assert [c[0] for c in calls] == [
        "https://q/api/datasets/a/d/metadata?version=V1",
        f"https://q/api/datasets/a/d/metadata/files/{sha}",
        "https://q/api/datasets/a/d/metadata?version=V1",
    ]
    assert json.loads(gzip.decompress(calls[0][1])) == document
    assert calls[0][2]["Authorization"] == "Bearer T"
    assert calls[1][1] == b"Hello\n" and calls[1][2]["Content-Type"] == "text/markdown"


def test_refuses_a_file_changed_since_the_build(write):
    root, document = built(write)
    (root / "README.md").write_text("Changed\n", encoding="utf-8")
    with pytest.raises(PushError):
        push("https://q/m", document, root, "T", put=lambda *a: Reply(200, {}))


def test_reports_a_refusal(write):
    root, document = built(write)
    with pytest.raises(PushError, match="422"):
        push("https://q/m", document, root, "T", put=lambda *a: Reply(422, {"error": "unknown_columns"}))
