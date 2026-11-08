#!/usr/bin/env bash
# Build Max Payne 3 (Xbox 360, Title Update 6) for the PS4 (ps4-kit, x86-64 Jaguar). Run in WSL:
#   scripts/build-mp3.sh sdk          the ReXGlue runtime libraries only (no game files needed)
#   scripts/build-mp3.sh host         the host tools: the code generator (rexglue v0.10.0 + the PS4 PCH template) and
#                                     XenosRecomp (the shader translator)
#   scripts/build-mp3.sh codegen      the game's C++ from your default.xex + TU6 default.xexp
#   scripts/build-mp3.sh app          the eboot (game code + SDK + Xenos Vulkan back end + RADV)
#   scripts/build-mp3.sh captures     the shaders the game made on the console (/data/MP3/shader_capture, PS4_HOST)
#   scripts/build-mp3.sh shaders      Renut's shader library from them (~/mp3-build/shaders/renut_gpu)
#   scripts/build-mp3.sh pkg          out/MP3-vXX.YY.pkg (MP3_VERSION=00.01)
#   MP3_RENUT=1 (app, pkg): Renut, the MGR port's Direct3D-level renderer (mp3/renut), in build-app-renut, with the
#                 shader cache XenosRecomp made from the console's captures (~/mp3-build/shaders/renut_gpu)
# The sources come from scripts/clone-mp3.sh.
#
# Port of VasilkovND/mp3-nx done the MGR way (iHaiDeeZ/MGR-PS4): a full x86-64 conversion, no deko3d and no ARM
# code. The SDK is mp3-nx's rexglue-sdk-nx with mp3-nx's sdk-patches and the MGR port's PS4 platform layer merged in
# (branch ps4); the GPU is the SDK's Xenia-derived Vulkan back end on ps4-kit's RADV, shaders translated at run time.
#
#   ~/mp3-build/src/mp3-nx        upstream checkout (VasilkovND/mp3-nx); sdk/ on branch ps4
#   ~/mp3-build/src/rexglue-host  rexglue-sdk v0.10.0 for the host code generator (mp3-nx's tools/codegen.sh pins it)
#   ~/mp3-build/game              your game: default.xex (disc 1) + default.xexp (TU6 disc001), and the rest
#   ~/mp3-build/build-sdk         the CMake build of the SDK for the PS4
set -euo pipefail
source "$HOME/ps4-kit/toolchain/env.sh"
MP3="$HOME/mp3-build"
SRC="${MP3_SRC:-$MP3/src/mp3-nx}"
# rexglue-sdk v0.10.0 (c94f5eb): its thirdparty matches sdk/'s submodules (scripts/clone-mp3.sh; the MGR port's copy
# where that is the one there is)
UP="${MP3_REXGLUE_SDK:-$MP3/src/rexglue-sdk}"
[ -d "$UP" ] || UP="$HOME/mgr-build/src/rexglue-sdk"
GAME="${MP3_GAME:-$MP3/game}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$MP3/logs"

if [ ! -f "$SRC/sdk/thirdparty/fmt/CMakeLists.txt" ]; then
    rsync -a --ignore-existing --exclude=.git "$UP/thirdparty/" "$SRC/sdk/thirdparty/"
fi
# The PS4's FFmpeg configuration (from the MGR port): config.h picks config_ps4_x86_64.h for __PS4__.
for f in config.h config_ps4_x86_64.h; do
    cmp -s "$HERE/patches/ffmpeg/$f" "$SRC/sdk/thirdparty/FFmpeg/$f" || cp "$HERE/patches/ffmpeg/$f" "$SRC/sdk/thirdparty/FFmpeg/$f"
done

case "${1:-sdk}" in
sdk)
    B="$MP3/build-sdk"
    echo "== configure"
    ps4_cmake -S "$SRC/sdk" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DREXGLUE_PLATFORM_PS4=ON -DREXGLUE_BUILD_HOST_TOOLS=OFF -DREXGLUE_USE_VULKAN=ON \
        -DREXGLUE_ENABLE_TRACY=OFF -DREXGLUE_BUILD_TESTS=OFF \
        > "$MP3/logs/configure-sdk.log" 2>&1 || { tail -40 "$MP3/logs/configure-sdk.log"; exit 1; }
    echo "== build ${MP3_TARGETS:-rexcore}"
    ninja -C "$B" -k 0 ${MP3_TARGETS:-rexcore} > "$MP3/logs/build-sdk.log" 2>&1 \
        || { grep -E "error:|FAILED" "$MP3/logs/build-sdk.log" | head -80; exit 1; }
    echo "sdk built"
    ;;
host)
    # ReXGlue v0.10.0 (the version mp3-nx's tools/codegen.sh pins) with mp3-nx's host patch (REX_DUMP_IMAGE: the
    # loaded image, for the disassembly) and SDL3's dummy drivers only (no X11/Wayland packages on WSL).
    H="$MP3/src/rexglue-host"
    if [ ! -d "$H" ]; then
        rsync -a "$UP/" "$H/"
        git -C "$H" apply "$SRC/mp3/host-patches/0001-dump-image.patch"
        git -C "$H" apply "$HERE/patches/host-sdl-headless.patch"
    fi
    HD="$HOME/mgr-build/host-deps/root"
    export PKG_CONFIG_PATH="$HD/usr/lib/x86_64-linux-gnu/pkgconfig:$HD/usr/share/pkgconfig"
    cmake -S "$H" -B "$H/out/host" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang-21 -DCMAKE_CXX_COMPILER=clang++-21 \
        -DCMAKE_C_FLAGS=-march=x86-64-v2 -DCMAKE_CXX_FLAGS=-march=x86-64-v2 \
        -DCMAKE_SHARED_LINKER_FLAGS="-L$HD/usr/lib/x86_64-linux-gnu" -DCMAKE_EXE_LINKER_FLAGS="-L$HD/usr/lib/x86_64-linux-gnu" \
        -DREXGLUE_USE_VULKAN=ON -DREXGLUE_ENABLE_TRACY=OFF -DREXGLUE_SDL_HEADLESS=ON \
        > "$MP3/logs/configure-host.log" 2>&1 || { tail -40 "$MP3/logs/configure-host.log"; exit 1; }
    ninja -C "$H/out/host" rexglue > "$MP3/logs/build-host.log" 2>&1 \
        || { grep -E "error:|FAILED" "$MP3/logs/build-host.log" | head -40; exit 1; }
    # tools/codegen.sh looks for it in mp3/out/rexglue-host.
    mkdir -p "$SRC/mp3/out"
    ln -sfn "$H" "$SRC/mp3/out/rexglue-host"
    echo "host built: $H/out/linux-amd64/rexglue"
    # XenosRecomp (Renut's, in mp3/renut) for the shader library; it runs renderbag/dxc-bin's DXC.
    XR="$SRC/mp3/renut/thirdparty/reblue-XenosRecomp"
    if [ ! -e "$XR/thirdparty/dxc-bin/bin/x64/dxc-linux" ]; then
        DXC="${MP3_DXC_BIN:-$MP3/src/dxc-bin}"
        [ -d "$DXC" ] || DXC="$HOME/mgr-build/src/dxc-bin"
        mkdir -p "$XR/thirdparty/dxc-bin" && cp -r "$DXC/bin" "$DXC/lib" "$XR/thirdparty/dxc-bin/"
    fi
    cmake -S "$XR" -B "$MP3/build-xenos" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang-21 -DCMAKE_CXX_COMPILER=clang++-21 -DXENOS_RECOMP_RENUT=ON -DXENOS_RECOMP_DXIL=OFF \
        > "$MP3/logs/configure-xenos.log" 2>&1 || { tail -40 "$MP3/logs/configure-xenos.log"; exit 1; }
    ninja -C "$MP3/build-xenos" XenosRecomp > "$MP3/logs/build-xenos.log" 2>&1 \
        || { grep -E "error|FAILED" "$MP3/logs/build-xenos.log" | head -40; exit 1; }
    echo "host built: $MP3/build-xenos/XenosRecomp/XenosRecomp"
    ;;
captures)
    # The shader containers the game made on the console: the quick menu's Diagnostics > Capture shaders (in a build
    # without MP3_RENUT, the game creates its shaders at startup), and those Renut writes because its library lacks
    # them, from /data/MP3/shader_capture to ~/mp3-build/shaders/containers (files already there are kept).
    HOST="${PS4_HOST:?give the console IP address in PS4_HOST}"
    URL="ftp://$HOST:${PS4_FTP_PORT:-2121}/data/MP3/shader_capture"
    D="$MP3/shaders/containers"
    mkdir -p "$D"
    n=0
    for f in $(curl -sS --list-only "$URL/" | tr -d '\r' | grep -E '^[a-z]+_[0-9a-fA-F]+[.]bin$'); do
        [ -s "$D/$f" ] && continue
        curl -sS -o "$D/$f" "$URL/$f" && n=$((n + 1))
    done
    echo "$n new shader containers, $(find "$D" -name '*.bin' | wc -l) in $D"
    ;;
shaders)
    # Renut's shader library: XenosRecomp over the captured containers -> shaders/renut_gpu/shader_cache.cpp, which
    # MP3_RENUT=1 builds into the eboot (~5 minutes for the game's 3,824 shaders). Made from your game: never share it.
    XR="$SRC/mp3/renut/thirdparty/reblue-XenosRecomp"
    S="$MP3/shaders"
    [ -x "$MP3/build-xenos/XenosRecomp/XenosRecomp" ] || { echo "run '$0 host' first" >&2; exit 1; }
    [ -n "$(find "$S/containers" -name '*.bin' 2> /dev/null | head -1)" ] || { echo "no $S/containers: run '$0 captures' first" >&2; exit 1; }
    export LD_LIBRARY_PATH="$XR/thirdparty/dxc-bin/lib/x64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    rm -rf "$S/spirv" "$S/hlsl"
    mkdir -p "$S/spirv" "$S/hlsl" "$S/renut_gpu"
    BANJO_DEKO3D_SPIRV_DIR="$S/spirv" "$MP3/build-xenos/XenosRecomp/XenosRecomp" "$S/containers" \
        "$S/renut_gpu/shader_cache.cpp" "$XR/XenosRecomp/shader_common.h" "$S/hlsl" > "$MP3/logs/shaders.log" 2>&1 \
        || { tail -20 "$MP3/logs/shaders.log"; exit 1; }
    echo "shader library: $S/renut_gpu/shader_cache.cpp ($(du -h "$S/renut_gpu/shader_cache.cpp" | cut -f1))"
    ;;
codegen)
    # mp3-nx's tools/codegen.sh with the x86-64 settings: no ARM fences (BARRIERS=0: x86 orders memory as the codegen
    # assumes), the fmadd family unfused (PS4=1, tools/ps4_unfused_fma.py). Its other passes are plain C++ (branch
    # traps, vmaddfp exactness, stack accesses, inlining, guest registers as locals) and stay.
    [ -x "$SRC/mp3/out/rexglue-host/out/linux-amd64/rexglue" ] || { echo "run '$0 host' first" >&2; exit 1; }
    for f in default.xex default.xexp; do
        [ -f "$GAME/$f" ] || { echo "no $GAME/$f (disc 1's default.xex and TU6 disc001's default.xexp)" >&2; exit 1; }
    done
    # codegen/ here: the function entries and hook names for the user's 0.0.6.6 executable (mp3-nx's are for 0.0.9.6).
    (cd "$SRC" && BARRIERS=0 PS4=1 CODEGEN_CONFIG="$HERE/codegen/mp3_config.toml" CODEGEN_NAMES="$HERE/codegen/names.toml" \
        mp3/tools/codegen.sh "$GAME") 2>&1 | tee "$MP3/logs/codegen.log" | tail -12
    [ "${PIPESTATUS[0]}" = 0 ] || exit 1
    ;;
app)
    # The eboot: the generated game code, the SDK with its Xenos GPU on Vulkan, RADV (ps4-kit).
    # MP3_CODEGEN=<folder>: another codegen output (the toolchain test on another title's executable).
    CG="${MP3_CODEGEN:-$SRC/mp3/out/codegen}"
    [ -f "$CG/generated/default/sources.cmake" ] || { echo "run '$0 codegen' first" >&2; exit 1; }
    RENUT_ARGS=(-DMP3_RENUT=OFF)
    if [ "${MP3_RENUT:-0}" = 1 ]; then
        CACHE="$MP3/shaders/renut_gpu/shader_cache.cpp"
        [ -f "$CACHE" ] || { echo "no $CACHE: translate the captured shaders first" >&2; exit 1; }
        RENUT_ARGS=(-DMP3_RENUT=ON -DBANJO_RENUT_SHADER_CACHE_CPP="$CACHE")
    fi
    B="${MP3_APP_BUILD:-$MP3/build-app$([ "${MP3_RENUT:-0}" = 1 ] && echo -renut)}"
    echo "== configure"
    ps4_cmake -S "$SRC/mp3/ps4" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release "${RENUT_ARGS[@]}" \
        -DCMAKE_PROJECT_mp3_INCLUDE="$PS4_KIT/ps4-kit.cmake" -DPS4_KIT_NETFS=OFF \
        -DREXSDK_DIR="$SRC/sdk" -DMP3_CODEGEN_DIR="$CG" -DREXGLUE_PLATFORM_PS4=ON -DREXGLUE_BUILD_HOST_TOOLS=OFF \
        -DREXGLUE_USE_VULKAN=ON -DREXGLUE_ENABLE_TRACY=OFF -DREXGLUE_BUILD_TESTS=OFF \
        -DMP3_VERSION="${MP3_VERSION:-00.00}" -DMP3_NAMES_TOML="${MP3_NAMES:-$HERE/codegen/names.toml}" \
        > "$MP3/logs/configure-app.log" 2>&1 || { tail -40 "$MP3/logs/configure-app.log"; exit 1; }
    # Each generated chunk takes ~1.5 GB of RAM to compile (the MGR port's measure).
    mem_mb=$(( $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) / 1024 ))
    JOBS=$(( mem_mb / 1500 )); [ "$JOBS" -lt 1 ] && JOBS=1; [ "$JOBS" -gt "$(nproc)" ] && JOBS=$(nproc)
    echo "== build (${MP3_TARGETS:-mp3_eboot}, -j$JOBS)"
    ninja -C "$B" -k 0 -j"$JOBS" ${MP3_TARGETS:-mp3_eboot} > "$MP3/logs/build-app.log" 2>&1 \
        || { grep -E "error:|FAILED|undefined symbol|missing module" "$MP3/logs/build-app.log" | head -80; exit 1; }
    echo "app built"
    ;;
pkg)
    # out/MP3-vXX.YY.pkg (MP3_VERSION=00.01). The game is not in it: copy your disc 1 (game/) or its Games on Demand
    # package (god/), and TU6's disc001 files (update/), to the console's /data/MP3.
    # MP3_PKG_GAME=1 (v00.51): the one-file package. $GAME goes in as game/ (the disc's dashboard extras left out, as
    # upload-data.py leaves them) and TU6's disc001 files (MP3_UPDATE, default ~/mp3-build/stage-tu/update) as
    # update/; the app reads them from /app0 before /data/MP3 (mp3_ps4_app.h). Such a package holds your game: it goes
    # to your own console and nowhere else.
    VERSION="${MP3_VERSION:-00.00}"
    B="${MP3_APP_BUILD:-$MP3/build-app$([ "${MP3_RENUT:-0}" = 1 ] && echo -renut)}"
    EBOOT="$B/mp3_eboot/eboot.bin"
    [ -f "$EBOOT" ] || { echo "no $EBOOT: run '$0 app' first" >&2; exit 1; }
    STAGE="$MP3/stage"
    rm -rf "$STAGE"
    mkdir -p "$STAGE/sce_sys"
    cp "$EBOOT" "$STAGE/eboot.bin"
    [ -f "$HERE/sce_sys/icon0.png" ] || python3 -I "$HERE/scripts/make-icon.py" "$HERE/sce_sys/icon0.png"
    cp "$HERE/sce_sys/icon0.png" "$STAGE/sce_sys/"
    [ -f "$HERE/sce_sys/pic1.png" ] && cp "$HERE/sce_sys/pic1.png" "$STAGE/sce_sys/"
    if [ "${MP3_PKG_GAME:-0}" = 1 ]; then
        TU="${MP3_UPDATE:-$MP3/stage-tu/update}"
        [ -f "$GAME/default.xex" ] || { echo "no $GAME/default.xex" >&2; exit 1; }
        [ -f "$TU/default.xexp" ] || { echo "no $TU/default.xexp" >&2; exit 1; }
        mkdir -p "$STAGE/game"
        for entry in "$GAME"/*; do
            case "$(basename "$entry")" in '$SystemUpdate' | nxeart) continue ;; esac
            # hard links where the stage shares the game's disk: 7.6 GB not copied
            cp -al "$entry" "$STAGE/game/" 2>/dev/null || cp -a "$entry" "$STAGE/game/"
        done
        cp -al "$TU" "$STAGE/update" 2>/dev/null || cp -a "$TU" "$STAGE/update"
        echo "game in the package: game/ $(du -sh "$STAGE/game" | cut -f1), update/ $(du -sh "$STAGE/update" | cut -f1)"
    fi
    PKG="$(bash "$PS4_KIT/scripts/make-pkg.sh" "$STAGE" MAXP00003 "Max Payne 3" "$VERSION" MP3 "$PSB/out" | tail -1)"
    mkdir -p "$HERE/out" "$MP3/oelf"
    cp "$PKG" "$HERE/out/MP3-v$VERSION.pkg"
    cp "$B/mp3" "$MP3/oelf/v$VERSION.elf" 2>/dev/null || true
    ls -la "$HERE/out/MP3-v$VERSION.pkg"
    ;;
*)
    echo "usage: $0 sdk|host|codegen|app|captures|shaders|pkg" >&2
    exit 2
    ;;
esac
