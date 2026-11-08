#!/usr/bin/env bash
# The parts of the MGR port's app tree that mp3-nx/mp3/renut starts from: Renut (the Direct3D-level renderer), its
# portable glue headers, plume and XenosRecomp, as tuancapoo/mgr-nx-deko has them at patches/BASE.txt's commit with
# iHaiDeeZ/MGR-PS4's patch applied. patches/mp3-ps4.patch holds MP3's changes on top of these copies (its hooks at
# MP3's addresses, the HDR, tiling and resolve work, the vertex input locations), so the patch carries no third-party
# tree. Sourced by scripts/clone-mp3.sh and scripts/save-patch.sh:
#   source scripts/renut-seed.sh; seed_renut <mgr-nx-deko checkout> <mp3-nx checkout>
seed_renut() {
    local app="$1/app" renut="$2/mp3/renut"
    [ -d "$app/src/renut_engine" ] || { echo "no $app/src/renut_engine: the MGR port's tree is needed" >&2; return 1; }
    mkdir -p "$renut/src/cpu" "$renut/src/me" "$renut/thirdparty"
    rsync -a --exclude=.git "$app/src/renut_engine/" "$renut/src/renut_engine/"
    cp "$app/src/cpu/sa2_enhancements.h" "$renut/src/cpu/"
    cp "$app/src/me/me_platform_compat.h" "$app/src/me/sa2_render_mode.cpp" "$app/src/me/sa2_render_mode.h" "$renut/src/me/"
    cp "$app/src/sa2_capture.h" "$renut/src/"
    rsync -a --exclude=.git "$app/thirdparty/plume/" "$renut/thirdparty/plume/"
    # XenosRecomp's DXC binaries (renderbag/dxc-bin, 200 MB) are copied in by scripts/build-mp3.sh host.
    rsync -a --exclude=.git --exclude=/thirdparty/dxc-bin "$app/thirdparty/reblue-XenosRecomp/" \
        "$renut/thirdparty/reblue-XenosRecomp/"
}
