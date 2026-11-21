#!/usr/bin/env bash
# Rebuilds StarPilot's raylib extension (openpilot/starpilot/ui/native/_raylib_extra.so) with Tandem's
# release_font_glyph_images, on a parked comma, in a temporary folder; the installed extension isn't touched.
#
#   ssh comma@<device> 'bash -s' < openpilot/selfdrive/ui/tandem/tools/build_raylib_extra.sh
#   scp comma@<device>:/tmp/tandem-raylib/_raylib_extra.so openpilot/starpilot/ui/native/
#
# The flags are StarPilot's comma_arm64 build (SConstruct) and the extension's own (starpilot/ui/native/SConscript),
# with the device's nanobind and raylib headers, which match uv.lock. Then refresh prebuilt.json (README › After a merge).
set -euo pipefail
[ "$(cat /data/params/d/IsOffroad)" = 1 ] || { echo "Park first" >&2; exit 1; }
B=/tmp/tandem-raylib
rm -rf "$B"
mkdir -p "$B"
cd "$B"
PY=/usr/local/venv/bin/python
NB=$($PY -c "import nanobind, pathlib; print(pathlib.Path(nanobind.source_dir()).parent)")
RAYLIB=$($PY -c "from importlib.metadata import distribution; print(distribution('comma-deps-raylib').locate_file('raylib/install/include'))")
PYINC=$($PY -c "import sysconfig; print(sysconfig.get_paths()['include'])")
INC=(-I"$PYINC" -I"$NB/include" -I"$NB/ext/robin_map/include" -I"$RAYLIB")
COMMON=(-g -fPIC -pipe -O2 -Wunused -Wno-unknown-warning-option -Wno-inconsistent-missing-override -Wno-c99-designator
        -Wno-reorder-init-list -Wno-vla-cxx-extension -std=c++1z -D__COMMA_HARDWARE__ -mcpu=cortex-a57
        -fvisibility=hidden -fno-strict-aliasing -DPy_LIMITED_API=0x030C0000)
nice -n 19 clang++ "${COMMON[@]}" "${INC[@]}" -c "$NB/src/nb_combined.cpp" -o nb_combined.os
nice -n 19 clang++ "${COMMON[@]}" -Wshadow "${INC[@]}" -c /data/openpilot/openpilot/starpilot/ui/native/raylib_extra.cc -o raylib_extra.o
nice -n 19 clang++ -shared -pthread raylib_extra.o nb_combined.os -ldl -o _raylib_extra.so
cat /VERSION
sha256sum _raylib_extra.so
