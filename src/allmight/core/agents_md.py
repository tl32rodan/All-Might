"""Marker-fenced ``AGENTS.md`` composition.

Root ``AGENTS.md`` is a **shared** file. All-Might composes the
framework primer plus every personality's ROLE.md into it; the user
keeps their own project instructions and dedicated agent prompts in
the same file, because that is the one file both OpenCode and (via the
``CLAUDE.md`` shim) Claude Code read automatically.

The two coexist through a fence::

    # My project
    You are a rigorous RTL reviewer...        <- user, never touched

    <!-- ALL-MIGHT:BEGIN -->
    <!-- all-might generated -->
    ...framework primer + personalities...    <- ours, rewritten
    <!-- ALL-MIGHT:END -->

    ## Build notes                            <- user, never touched

Only the region between the fence markers is rewritten on recompose.
Everything outside it survives byte-for-byte.

Before this module, ``compose_agents_md`` regenerated the whole file:
a user who appended their own agent prompts to a marker'd AGENTS.md
lost them silently on the next ``allmight add`` / ``allmight init`` /
``allmight compose``. The file-level marker only proves "All-Might
wrote this file once", never "the body is still ours" — the same hole
CLAUDE.md documents for skill bodies.

Opt-out: a file containing ``<!-- ALL-MIGHT:OFF -->`` is never
modified. The composition is staged to
``.allmight/templates/AGENTS.md`` for ``/sync`` instead.
"""

from __future__ import annotations

FENCE_BEGIN = "<!-- ALL-MIGHT:BEGIN -->"
FENCE_END = "<!-- ALL-MIGHT:END -->"
FENCE_OPT_OUT = "<!-- ALL-MIGHT:OFF -->"

#: Section markers emitted by the pre-Part-C ``_write_legacy_agents_md``
#: paths (``capabilities/*/initializer.py``). Everything from the first
#: one to EOF was All-Might-owned in that format.
LEGACY_SECTION_MARKERS = ("<!-- ALL-MIGHT -->", "<!-- ALL-MIGHT-MEMORY -->")

#: Actions returned by :func:`splice`. ``removed_content`` is True for
#: the ones where pre-existing bytes did not survive verbatim, which is
#: the caller's cue to write a ``.prev`` backup.
_ACTIONS_THAT_REMOVE = frozenset({"migrated", "legacy-cut", "forced"})


def render_fenced(body: str) -> str:
    """Wrap *body* in the All-Might fence, newline-terminated."""
    return f"{FENCE_BEGIN}\n{body.strip()}\n{FENCE_END}\n"


def removes_content(action: str) -> bool:
    """True when *action* dropped pre-existing bytes (backup warranted)."""
    return action in _ACTIONS_THAT_REMOVE


def has_fence(text: str) -> bool:
    """True when *text* already carries an All-Might fence opener."""
    return FENCE_BEGIN in text


def fence_bounds(text: str) -> tuple[int, int] | None:
    """Return ``(start, end)`` slice indices of the fenced region.

    ``None`` when *text* has no fence. A dangling ``BEGIN`` with no
    ``END`` (hand-truncated file) is read as running to EOF — that is
    what a half-deleted fence means. Multiple fences collapse into one:
    the first opener and the last closer bound the region.
    """
    if FENCE_BEGIN not in text:
        return None
    start = text.index(FENCE_BEGIN)
    if FENCE_END in text[start:]:
        end = text.rindex(FENCE_END) + len(FENCE_END)
    else:
        end = len(text)
    return start, end


def splice(existing: str | None, body: str, *, force: bool = False) -> tuple[str, str]:
    """Merge the composed *body* into *existing*, returning ``(text, action)``.

    ``existing`` is the current AGENTS.md content, or ``None`` when the
    file does not exist yet. Actions:

    ``created``
        No file existed — write the fenced block alone.
    ``unchanged``
        The fenced region already matches; nothing to write.
    ``replaced``
        A fence was present — only its interior changed. Content
        before and after the fence is preserved byte-for-byte. A
        dangling ``BEGIN`` with no ``END`` (hand-truncated file) is
        treated as running to EOF and repaired.
    ``appended``
        No fence and no All-Might content — the user authored this
        file. Their bytes are kept verbatim and the fenced block is
        appended at the end. This is what makes a hand-written
        AGENTS.md *compatible* rather than *rejected*.
    ``migrated``
        No fence, but the exact unfenced composition we used to emit is
        present — wrap that region in the fence in place, keeping
        whatever the user added around it.
    ``legacy-cut``
        A pre-Part-C ``<!-- ALL-MIGHT -->`` section was found. Those
        sections ran to EOF, so everything from the first legacy marker
        onward is replaced by the fenced block; the prefix survives.
    ``opted-out``
        ``<!-- ALL-MIGHT:OFF -->`` present — caller must stage instead.
    ``forced``
        ``force=True`` on a file with no fence and no recognisable
        All-Might content: the documented overwrite-everything path.

    The function is pure — the caller does the I/O (and the backup when
    :func:`removes_content` is true for the returned action).
    """
    block = render_fenced(body)

    if existing is None:
        return block, "created"

    bounds = fence_bounds(existing)

    # The opt-out only counts when the *user* wrote it. Our own block
    # explains the mechanism, so a token inside the fence is our prose,
    # not their instruction.
    outside = (
        existing if bounds is None else existing[: bounds[0]] + existing[bounds[1]:]
    )
    if FENCE_OPT_OUT in outside and not force:
        return existing, "opted-out"

    if bounds is not None:
        start, end = bounds
        merged = existing[:start] + block.rstrip("\n") + existing[end:]
        if not merged.endswith("\n"):
            merged += "\n"
        return (merged, "unchanged" if merged == existing else "replaced")

    for marker in LEGACY_SECTION_MARKERS:
        if marker in existing:
            prefix = existing[: existing.index(marker)].rstrip("\n")
            return _join(prefix, block), "legacy-cut"

    stripped_body = body.strip()
    if stripped_body and stripped_body in existing:
        # The unfenced composition we used to emit — wrap it in place so
        # anything the user appended around it stays where it is.
        merged = existing.replace(stripped_body, block.strip(), 1)
        if not merged.endswith("\n"):
            merged += "\n"
        return merged, "migrated"

    if force:
        return block, "forced"

    return _join(existing.rstrip("\n"), block), "appended"


def _join(prefix: str, block: str) -> str:
    """Concatenate *prefix* and *block* with exactly one blank line."""
    if not prefix.strip():
        return block
    return f"{prefix}\n\n{block}"
