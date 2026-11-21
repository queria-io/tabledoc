from __future__ import annotations

import pytest

from tabledoc.git import https


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
