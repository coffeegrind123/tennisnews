#!/usr/bin/env python3
"""Register the pre-downloaded camoufox_build/ with the installed camoufox library.

camoufox >= 0.5 replaced the flat cache layout (everything directly in
`user_cache_dir("camoufox")`) with a multiversion layout:

    <cache>/.0.5_FLAG
    <cache>/config.json            {"active_version": "browsers/<repo>/<version>"}
    <cache>/browsers/<repo>/<version>/{camoufox-bin,version.json,...}

The old CI trick of symlinking camoufox_build straight onto the cache dir no
longer resolves, so `installed_verstr()` raises CamoufoxNotInstalled and every
browser-scraped source silently returns zero articles. This script builds the
layout the resolver actually expects and then *verifies* it by asking the
library to resolve the path back.

Usage:  python3 backend/setup_camoufox.py [path/to/camoufox_build]
"""

import json
import os
import shutil
import sys
from pathlib import Path

# Directory name under <cache>/browsers/. camoufox's repos.yml defines the known
# repos (Official, CoryKing, JWriter20); matching the name keeps this layout
# consistent with what `camoufox fetch` would produce for the same build.
REPO_NAME = os.environ.get("CAMOUFOX_REPO_NAME", "jwriter20")


def main() -> int:
    build_dir = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "camoufox_build").resolve()

    binary = build_dir / "camoufox-bin"
    version_json = build_dir / "version.json"
    if not binary.exists():
        print(f"ERROR: no camoufox-bin at {binary}", file=sys.stderr)
        return 1

    # Not every release ships version.json - the JWriter20 FF152 build does not -
    # but camoufox's resolver requires it. application.ini always carries the
    # same information ("Version=152.0.4-beta.28"), so synthesise it from there
    # rather than failing or hardcoding a version in the workflow.
    if not version_json.exists():
        app_ini = build_dir / "application.ini"
        if not app_ini.exists():
            print(f"ERROR: neither version.json nor application.ini in {build_dir}", file=sys.stderr)
            return 1
        ver_line = ""
        for line in app_ini.read_text(errors="replace").splitlines():
            if line.startswith("Version="):
                ver_line = line.split("=", 1)[1].strip()
                break
        if "-" not in ver_line:
            print(f"ERROR: cannot parse a version/build from application.ini "
                  f"(Version={ver_line!r})", file=sys.stderr)
            return 1
        version, build = ver_line.split("-", 1)
        version_json.write_text(json.dumps({"version": version, "release": build}))
        print(f"synthesised version.json from application.ini: {version}-{build}")

    meta = json.loads(version_json.read_text())
    version = meta.get("version", "unknown")
    build = meta.get("release") or meta.get("tag") or "unknown"
    version_folder = f"{version}-{build}"
    rel_path = f"browsers/{REPO_NAME}/{version_folder}"

    from platformdirs import user_cache_dir

    cache = Path(user_cache_dir("camoufox"))
    target = cache / rel_path

    # Rebuild from scratch: a stale flat-layout cache makes camoufox_path() wipe
    # the directory out from under us on first use.
    if cache.exists() or cache.is_symlink():
        if cache.is_symlink():
            cache.unlink()
        else:
            shutil.rmtree(cache)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Symlink rather than copy: the build is ~1.2 GB.
    os.symlink(build_dir, target)
    (cache / ".0.5_FLAG").touch()
    (cache / "config.json").write_text(json.dumps({"active_version": rel_path}, indent=2))

    os.chmod(binary, 0o755)

    # Verify through the library itself, not by re-checking our own assumptions.
    from camoufox.pkgman import camoufox_path, installed_verstr

    verstr = installed_verstr()
    resolved = camoufox_path(download_if_missing=False)
    if Path(resolved).resolve() != build_dir:
        print(f"ERROR: camoufox resolved to {resolved}, expected {build_dir}", file=sys.stderr)
        return 1

    print(f"camoufox registered: {verstr}")
    print(f"  cache:  {cache}")
    print(f"  active: {rel_path} -> {build_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
