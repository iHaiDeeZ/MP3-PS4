#!/usr/bin/env bash
# Fetch the sources the PS4 build needs into ~/mp3-build/src (run in WSL), at the commits in patches/BASE.txt:
#   src/mp3-nx        VasilkovND/mp3-nx, branch ps4: Renut from the MGR port (scripts/renut-seed.sh), then
#                     patches/mp3-ps4.patch; its sdk/ (nx-mod/rexglue-sdk-nx) with patches/sdk-ps4.patch
#   src/mgr-nx-deko   tuancapoo/mgr-nx-deko with iHaiDeeZ/MGR-PS4's patch: where that Renut comes from
#   src/rexglue-sdk   rexglue/rexglue-sdk v0.10.0: the third-party sources sdk/ does not carry, and the tree of the
#                     host code generator (scripts/build-mp3.sh host)
#   src/dxc-bin       renderbag/dxc-bin: the DXC that XenosRecomp runs
# Re-running keeps existing checkouts (MP3_SOURCE_RESET=1 starts mp3-nx and mgr-nx-deko over).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
S="$HOME/mp3-build/src"
# shellcheck source=renut-seed.sh
source "$HERE/scripts/renut-seed.sh"
base() { awk -v k="$1" '$1 == k { print $2 }' "$HERE/patches/BASE.txt"; }
commit() { git -C "$1" add -A && git -C "$1" -c user.name=mp3 -c user.email=mp3@localhost commit -q -m "$2"; }
mkdir -p "$S" "$HOME/mp3-build/logs"

if [ "${MP3_SOURCE_RESET:-0}" = 1 ]; then rm -rf "$S/mp3-nx" "$S/mgr-nx-deko"; fi

if [ ! -d "$S/rexglue-sdk/.git" ]; then
    git clone -q --recursive https://github.com/rexglue/rexglue-sdk "$S/rexglue-sdk"
    git -C "$S/rexglue-sdk" checkout -q "$(base rexglue-sdk)"
    git -C "$S/rexglue-sdk" submodule update -q --init --recursive
fi
if [ ! -d "$S/dxc-bin/.git" ]; then
    git clone -q https://github.com/renderbag/dxc-bin "$S/dxc-bin"
    git -C "$S/dxc-bin" checkout -q "$(base dxc-bin)"
fi

# The MGR port's tree: mgr-nx-deko with MGR-PS4's patch at the commits MP3's Renut was copied from.
if [ ! -d "$S/mgr-nx-deko/.git" ]; then
    git clone -q https://github.com/tuancapoo/mgr-nx-deko "$S/mgr-nx-deko"
    git -C "$S/mgr-nx-deko" checkout -q -b ps4 "$(base mgr-nx-deko)"
    curl -fsSL "https://raw.githubusercontent.com/iHaiDeeZ/MGR-PS4/$(base MGR-PS4)/patches/mgr-ps4.patch" \
        -o "$S/mgr-ps4.patch"
    git -C "$S/mgr-nx-deko" apply --whitespace=nowarn "$S/mgr-ps4.patch"
    commit "$S/mgr-nx-deko" "MGR-PS4"
fi

if [ ! -d "$S/mp3-nx/.git" ]; then
    git clone -q https://github.com/VasilkovND/mp3-nx "$S/mp3-nx"
    git -C "$S/mp3-nx" checkout -q -b ps4 "$(base mp3-nx)"
    git -C "$S/mp3-nx" submodule update -q --init sdk
    git -C "$S/mp3-nx/sdk" checkout -q -b ps4 "$(base rexglue-sdk-nx)"
    git -C "$S/mp3-nx/sdk" apply --whitespace=nowarn "$HERE/patches/sdk-ps4.patch"
    commit "$S/mp3-nx/sdk" "PS4 port"
    seed_renut "$S/mgr-nx-deko" "$S/mp3-nx"
    commit "$S/mp3-nx" "Renut from the MGR port"
    git -C "$S/mp3-nx" apply --whitespace=nowarn "$HERE/patches/mp3-ps4.patch"
    commit "$S/mp3-nx" "PS4 port"
fi
echo "sources ready in $S"
