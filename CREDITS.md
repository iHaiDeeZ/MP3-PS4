# Credits and licences

This repository holds build scripts, two patches against
[VasilkovND/mp3-nx](https://github.com/VasilkovND/mp3-nx) at the commits in `patches/BASE.txt`
(`patches/mp3-ps4.patch` for its tree, `patches/sdk-ps4.patch` for its `sdk/` submodule), the PS4 configuration of
FFmpeg (`patches/ffmpeg/`), the code generator's configuration for the game's version 0.0.6.6 (`codegen/`) and
development tools (`tools/`). `scripts/clone-mp3.sh` copies the Renut renderer, plume and XenosRecomp from the Metal
Gear Rising port (tuancapoo/mgr-nx-deko with [iHaiDeeZ/MGR-PS4](https://github.com/iHaiDeeZ/MGR-PS4)'s patch) into
mp3-nx before `patches/mp3-ps4.patch` changes them. The patched files keep their own licences.

| Part | Where | Licence |
|---|---|---|
| mp3-nx (VasilkovND), built on gta4-nx, ds2-nx, gears2-nx and dantes-inferno-nx (VasilkovND), [NFSMW-NX](https://github.com/StevensND/nfsmw-nx) (StevensND), [Liberty Recompiled](https://github.com/OZORDI/LibertyRecomp) and [LibertyRecompAndroid](https://github.com/vaduur/LibertyRecompAndroid) | the upstream repository; the patch adds `mp3/ps4/`, `mp3/renut/` and the PS4 passes in `mp3/tools/`, and changes its build and code generation | GPL-3.0 (upstream `LICENSE`) |
| [rexglue-sdk-nx](https://github.com/nx-mod/rexglue-sdk-nx) (nx-mod) on the [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) v0.10.0 (Tom Clay), with portions from [Xenia](https://xenia.jp) (Ben Vanik and the Xenia contributors) | upstream's `sdk/`; the patch adds the PS4 platform layer (from the MGR port) and changes the runtime | BSD-3-Clause (upstream `sdk/LICENSE`) |
| [mgr-nx-deko](https://github.com/tuancapoo/mgr-nx-deko) (tuancapoo), built on [sa2-nx](https://github.com/chanseyisthebest/sa2-nx) (ChanseyIsTheBest), masseffect-nx (NebadasSwifty), nfsmw-nx (StevensND) and NFSMW Recompiled (madelrandel-blip): Renut's glue headers | copied into `mp3/renut/src` (`cpu/`, `me/`, `sa2_capture.h`) | GPL-3.0 (its `LICENSE`) |
| [Renut](https://github.com/masterspike52/reNut) (masterspike52), with the adaptations of banjo-nx and sa2-nx | mgr-nx-deko's `app/src/renut_engine`, copied into `mp3/renut/src/renut_engine`; MGR-PS4's patch adds the PS4 branches, this port's patch MP3's hooks and HDR, tiling and resolve work | no licence file upstream; sa2-nx documents a project-specific permission from its author (mgr-nx-deko's `THIRD_PARTY_NOTICES.md`) |
| [plume](https://github.com/renderbag/plume) (renderbag) | mgr-nx-deko's `app/thirdparty/plume`, copied into `mp3/renut/thirdparty`; MGR-PS4's patch adds the PS4 surface to its Vulkan back end | MIT |
| [XenosRecomp](https://github.com/hedge-dev/XenosRecomp) (hedge-dev and contributors; reblue fork) | mgr-nx-deko's `app/thirdparty/reblue-XenosRecomp`, copied into `mp3/renut/thirdparty`, run at build time; this port's patch places MP3's extra vertex inputs | MIT |
| DirectXShaderCompiler binaries ([renderbag/dxc-bin](https://github.com/renderbag/dxc-bin)) | build host only (XenosRecomp) | University of Illinois/NCSA, with LLVM's terms |
| [FFmpeg](https://ffmpeg.org) (the XMA and WMA decoders) | `sdk/thirdparty/FFmpeg`, from rexglue-sdk's submodule; `patches/ffmpeg/` is the PS4 configuration | LGPL-2.1-or-later (configured without GPL parts) |
| The SDK's other libraries (fmt, spdlog, toml++, Dear ImGui, xxHash, SIMDe, glslang, SPIRV-Tools, Vulkan Memory Allocator and the rest) | `sdk/thirdparty`, from rexglue-sdk v0.10.0 (`c94f5eb`) and its submodules | their own licences, listed in upstream's `THIRD_PARTY_NOTICES.md` |
| [Lato](https://www.latofonts.com) (Łukasz Dziedzic) | `mp3/ps4/fonts/`, added by the patch: the quick menu's type | SIL Open Font License 1.1 (`LICENSE-Lato.txt`) |
| ps4-kit (iHaiDeeZ): toolchain setup, runtime, Mesa RADV for the PS4, VideoOut swapchain, crash log, profiler, packaging | linked at build time, not in this repository | not published yet |
| [Mesa](https://mesa3d.org) RADV | built by ps4-kit | MIT |
| [OpenOrbis](https://github.com/OpenOrbis) toolchain ([PacBrew](https://github.com/PacBrew)) | build host | GPL-3.0 (tools), the C library under its own licences |

This port's own code in the patches (the files in `mp3/ps4/`, `mp3/renut/src/mp3_renut_glue.cpp`,
`mp3/renut/mp3_renut.cmake`, `mp3/tools/make_ps4_pch.py`, `mp3/tools/patch_phys_base.py`,
`mp3/tools/ps4_unfused_fma.py`, and the PS4 branches in upstream files) is under the licence of the folder it is in:
BSD-3-Clause in `sdk/`, MIT in plume and XenosRecomp, GPL-3.0 elsewhere. The build scripts, tools and the rest of
this repository are GPL-3.0 (`LICENSE`).

The game itself (code, art, sound, text) belongs to its owners. Nothing from it is in this repository or its
releases: the build reads your `default.xex`, Title Update 6 and the shaders your console captured, on your own
machine. The PlayStation button icons (`mp3/ps4/mp3_ps4_icons.inc`) are drawn by `tools/ps_icons.py`; only hashes of
the game's Xbox icons are kept, to find the ones to replace. The package's icon is made by `scripts/make-icon.py`
unless you put your own `sce_sys/` in this folder. The banner of this README is original art drawn by
`scripts/make-banner.py`.
