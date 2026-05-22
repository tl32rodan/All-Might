"""Generated-file markers for overwrite-guard.

Every file the initializer emits is prefixed with one of these tokens so
that re-init can tell its own files from user-owned files at the same
path.  ``write_guarded`` (in :mod:`allmight.core.safe_write`) refuses to
overwrite a path whose existing content lacks the marker.
"""

ALLMIGHT_MARKER_MD = "<!-- all-might generated -->"
ALLMIGHT_MARKER_TS = "// all-might generated"
ALLMIGHT_MARKER_YAML = "# all-might generated"
