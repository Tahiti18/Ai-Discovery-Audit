"""GeoReady AI Visibility Platform.

Phase 0 foundation. This package is intentionally isolated from the
open-source ``geo_optimizer`` engine: it *wraps and reuses* the engine via
``geoready_platform.core_bridge`` and never modifies it.

NOTE ON NAMING: the importable package is ``geoready_platform`` (not
``platform``) because Python's standard library already owns the ``platform``
module — shadowing it would break dependencies that ``import platform``.
The roadmap's ``platform/`` directory is preserved as the container; this
package lives inside it and ``platform/`` is placed on ``sys.path``.

See ``docs/ROADMAP.md`` (Appendix A — Phase 0 Execution Plan) for scope.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.0.0"  # platform is pre-MVP (Phase 0 foundation only)
