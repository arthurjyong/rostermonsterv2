"""First-release production-side template registry.

Houses the normative template artifacts the production CLI consumes. Tests
re-export from here so there's a single source of truth between test
fixtures and production runs.

When a second template lands, register it here and switch the CLI's
`--template` flag to look up by identity rather than hard-coding ICU/HD.
"""

from .icu_hd import icu_hd_template_artifact

__all__ = ["icu_hd_template_artifact"]
