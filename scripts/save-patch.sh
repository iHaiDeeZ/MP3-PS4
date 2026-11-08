#!/usr/bin/env bash
# Export the PS4 port's changes from the WSL checkouts into patches/ (run in WSL):
#   patches/mp3-ps4.patch   mp3-nx's tree against BASE.txt's commit with Renut seeded from the MGR port
#                           (scripts/renut-seed.sh), sdk/ left out
#   patches/sdk-ps4.patch   sdk/ (rexglue-sdk-nx) against its submodule commit, mp3-nx's own sdk-patches included
#                           (they are applied there as the first commit)
# Neither checkout's index is touched: mp3-nx's diff is made in a temporary worktree, sdk/'s with a temporary index.
# The game's files and everything made from them (generated code, shaders) are ignored by mp3-nx's .gitignore or live
# outside the tree.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${MP3_SRC:-$HOME/mp3-build/src/mp3-nx}"
MGR_SRC="${MP3_MGR_SRC:-$HOME/mp3-build/src/mgr-nx-deko}"
[ -d "$MGR_SRC" ] || MGR_SRC="$HOME/mgr-build/src/mgr-nx-deko"
# shellcheck source=renut-seed.sh
source "$HERE/scripts/renut-seed.sh"
base() { awk -v k="$1" '$1 == k { print $2 }' "$HERE/patches/BASE.txt"; }
BASE="$(base mp3-nx)"
SDK_BASE="$(base rexglue-sdk-nx)"

TMP="$(mktemp -d)"
cleanup() {
    git -C "$SRC" worktree remove --force "$TMP/tree" > /dev/null 2>&1 || true
    rm -rf "$TMP"
}
trap cleanup EXIT

# mp3-nx: the base, Renut seeded and committed, then the port's tree over it.
git -C "$SRC" worktree add -q --detach "$TMP/tree" "$BASE"
seed_renut "$MGR_SRC" "$TMP/tree"
git -C "$TMP/tree" add -A
git -C "$TMP/tree" -c user.name=mp3 -c user.email=mp3@localhost commit -q -m "Renut from the MGR port"
rsync -a --delete --exclude=.git --exclude=/sdk --exclude=/mp3/out --exclude=__pycache__ \
    --exclude=/mp3/renut/thirdparty/reblue-XenosRecomp/thirdparty/dxc-bin "$SRC/" "$TMP/tree/"
git -C "$TMP/tree" add -A
git -C "$TMP/tree" diff --cached --binary HEAD -- . ':(exclude)sdk' > "$HERE/patches/mp3-ps4.patch"

# sdk/: everything since the submodule commit, new files included.
export GIT_INDEX_FILE="$TMP/sdk-index"
git -C "$SRC/sdk" read-tree HEAD
git -C "$SRC/sdk" add -A
git -C "$SRC/sdk" diff --cached --binary "$SDK_BASE" > "$HERE/patches/sdk-ps4.patch"
unset GIT_INDEX_FILE

for p in mp3-ps4 sdk-ps4; do
    echo "patches/$p.patch: $(grep -c '^diff --git' "$HERE/patches/$p.patch") files, $(du -h "$HERE/patches/$p.patch" | cut -f1)"
done
