"""One-shot migrator for projects on a pre-Part-C layout.

Turns existing All-Might projects into the new shape:

* ``personalities/<project>-corpus/`` -> ``personalities/<default>/``
  (typically ``knowledge``)
* ``personalities/<project>-memory/`` -> ``personalities/memory/``
* Single root ``AGENTS.md`` marker-fenced sections -> per-personality
  ``ROLE.md`` files; root re-composed via ``compose_agents_md``
* ``/reflect`` command + symlink dropped (its content lives in the
  new ``/remember`` body's Reflect section)
* ``.allmight/personalities.yaml`` rewritten with the new names
* ``.opencode/`` re-composed so symlinks point at the renamed dirs

Re-running the migrator on an already-migrated project is a no-op
because the detection probe (legacy instance dirs, marker-fenced
sections, ``/reflect.md``) won't match.
"""
