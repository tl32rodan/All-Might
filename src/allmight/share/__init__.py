"""Team-share transport for personality bundles.

Mode-1 sharing: bundles travel through a git remote (bare repo on
NFS, internal Gerrit/Gitea, or any host All-Might can reach via the
local ``git`` CLI). The framework treats git as a transport layer —
no GitHub-specific assumptions, no auth helpers, no PR semantics.

The ``/export`` skill produces a bundle directory; ``allmight share
publish`` pushes that bundle to a git URL; ``allmight share pull``
clones the bundle and runs ``allmight import`` against it.
"""

from .git_share import (
    UpstreamRecord,
    publish_bundle,
    pull_to_temp,
    read_upstream,
    write_upstream,
)

__all__ = [
    "UpstreamRecord",
    "publish_bundle",
    "pull_to_temp",
    "read_upstream",
    "write_upstream",
]
