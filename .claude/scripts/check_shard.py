"""pytest plugin of check-worktree.sh: run one shard of the test suite.

`--shard I/N` keeps the tests whose node id falls into shard I of N and deselects the
rest. CRC-32 is the same in every process (unlike `hash()`), so the N shards together
run every collected test exactly once. `--shard-report FILE` receives the line
"<kept> <collected>", which check-backend.sh adds up to prove that.
"""

import zlib
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("check-worktree")
    group.addoption(
        "--shard", required=True, metavar="I/N", help="run shard I (from 0) of N"
    )
    group.addoption("--shard-report", required=True, metavar="FILE")


# Last, so that the counts are those of the tests left by -m and -k.
@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    index, count = (int(part) for part in config.getoption("shard").split("/"))
    kept: list[pytest.Item] = []
    dropped: list[pytest.Item] = []
    for item in items:
        in_shard = zlib.crc32(item.nodeid.encode()) % count == index
        (kept if in_shard else dropped).append(item)
    Path(config.getoption("shard_report")).write_text(f"{len(kept)} {len(items)}\n")
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = kept
