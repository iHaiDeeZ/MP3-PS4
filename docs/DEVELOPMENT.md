# Development

How the PS4 build is put together, what the patches change, and what was learned on the way. For building, see the
[README](../README.md).

## The pieces

| Piece | Where | What |
|---|---|---|
| mp3-nx | `~/mp3-build/src/mp3-nx` (branch `ps4`) | VasilkovND's Switch port at `patches/BASE.txt`'s commit, Renut copied in from the MGR port, then `patches/mp3-ps4.patch` |
| its `sdk/` | the submodule, branch `ps4` | rexglue-sdk-nx with `patches/sdk-ps4.patch`: mp3-nx's own SDK patches, the PS4 platform layer from the MGR port, and this port's runtime changes |
| mgr-nx-deko | `~/mp3-build/src/mgr-nx-deko` | the Metal Gear Rising port with MGR-PS4's patch: where `mp3/renut` comes from (`scripts/renut-seed.sh`) |
| rexglue-sdk v0.10.0 | `~/mp3-build/src/rexglue-sdk` | the third-party sources `sdk/` doesn't carry, and the host code generator's tree |
| ps4-kit | `~/ps4-kit` | toolchain setup, runtime (heap, threads, crash log, profiler), Mesa RADV for the PS4, the VideoOut swapchain, packaging |

`scripts/clone-mp3.sh` puts all of it in place; `scripts/save-patch.sh` writes your changes back into the two
patches (in a temporary worktree and index: neither checkout is touched). The game's files, the code generated from
them and the translated shaders live outside the trees or are ignored by mp3-nx's `.gitignore`: never commit them.

## The build

1. **`sdk`**: the SDK's runtime libraries for the PS4.
2. **`host`**: the code generator (ReXGlue v0.10.0 with mp3-nx's host patch and SDL3's dummy drivers) and
   XenosRecomp (the shader translator, run with renderbag's DXC).
3. **`codegen`**: mp3-nx's `tools/codegen.sh` with `BARRIERS=0 PS4=1` and this repository's `codegen/` (function
   entries and hook names for 0.0.6.6; mp3-nx's are for 0.0.9.6, whose addresses all differ). Its passes rewrite the
   generated C++: guest registers as locals, inlining, stack accesses, branch traps, and for the PS4 the multiply-adds
   unfused (`ps4_unfused_fma.py`) and the physical window's offset taken per base register (`patch_phys_base.py`).
4. **`app`**: the eboot. `tools/make_ps4_pch.py` makes the PS4's precompiled header for the generated code
   (`REX_LOAD_U32_B` and the other base-register accesses); the generated sources are built `-O3 -march=btver2
   -ffp-contract=off -ffunction-sections`, linked with lld and `mp3/ps4/hot_functions.txt` as a symbol ordering file.
5. **`captures`** and **`shaders`**: the console's shader captures, translated into Renut's shader library
   (`shaders/renut_gpu/shader_cache.cpp`, ~7 MB of SPIR-V for 3,824 shaders).
6. **`pkg`**: the fake package; `MP3_PKG_GAME=1` adds `game/` and `update/` (hard links into the stage). Packages over
   4 GB need ps4-kit's fixed PkgTool (PlayGo hash sizing).

Every generated function is a weak alias of its `__imp__` body, so a hook (`REX_HOOK_RAW(sub_X)`) replaces it at link
time without generating code again. The code generator does read the hook names in `mp3/src`, `mp3/ps4` and `sdk`
(hooked functions are kept as calls, and their callers take every volatile register as changed): after adding or
removing a hook name there, run `codegen` again for the tightest code.

## Renut in MP3

Renut draws the game's Direct3D 9 calls itself instead of emulating the Xenos GPU. MP3's Direct3D (2.0.21076) has
the device layout Renut was written for: all 32 of the functions it hooks or calls were found in MP3 with the same
offsets, and its 24 hooks moved to MP3's addresses. What MP3 needed beyond that:

- **Direct3D's primary ring.** MP3 writes it from paths Renut doesn't hook: each device gets a 32 KB dummy ring.
- **Deferred batches.** `BlockUntilIdle` waits for a flag only a GPU reset clears; with no GPU interrupts under
  Renut, the flag is cleared before it.
- **HDR.** The 7e3 and 16-bit float targets, the exponent biases of targets, resolves and texture fetches, applied in
  the shaders per resolve and per bind; small `k_32_FLOAT` resolves written back to guest memory a frame late (the CPU
  reads them).
- **GPU-loaded constants.** The tonemap's `gAdaptedLum` is loaded by the GPU from the adaptation's 1x1 resolve
  (`LOAD_ALU_CONSTANT`, built by `sub_8304A068`): a hook copies guest memory into the device's constants and marks
  them dirty. Look for packets like this in any game Renut takes on: a D3D call Renut doesn't hook, whose packet
  matters.
- **Predicated tiling.** The G-buffer is drawn in two 1280x384 tiles and resolved per tile from the game's own list
  of rectangles, clearing after each: the tiles are kept, with targets of the full size.
- **A 4x alias.** The luminance chain halves the HDR scene by resolving its EDRAM as a 640x360 4x-aliased surface:
  that resolve reads the newer 1x twin, halved by a blit, which needed a new opcode in Renut's command recorder.
- **The vertex inputs.** Morph-target shaders read `NORMAL1`, `TANGENT1` and `BINORMAL1`: XenosRecomp places them at
  locations 23-25.

Renut's diagnostics: `banjo_renut_diag_resolve_trace` (one traced frame every 30 s) and the menu's Renderer HDR log.

## Threads and sound

- The SDK ignored the game's thread priorities and affinities by default, and its PS4 `set_priority` mapped Windows'
  values onto the wrong range. The PS4 doesn't take turns between threads of one priority, so a busy thread keeps its
  core: applying both took busy fights from 4-5 to 13-17 fps. Game threads use PS4 priorities 640-760, the host's
  service threads 600.
- A balancer places the busy game threads on the seven cores every second, by the CPU time they note at each wait;
  Renut's render thread is alone on the seventh core.
- The game's per-frame audio update waited, in `Sleep(0)` steps, for RAGE's audio thread to take the last update
  (`sub_82C42610`), and that thread waited for XAudio2's lock: the main thread spent ~30 % of busy fights there. The
  game's own switch for going on without the wait (the byte at `0x83705DF8`) is set before each call
  (`mp3_audio_no_wait`): ~12 to ~18.5 fps in busy fights.
- XAudio2's mono-to-5.1 mixer (`sub_82FEE438`) runs in SSE (`mp3_audio_native_mix`), checked bit for bit against
  the generated code over 200,000 random calls on the PC.
- XMA is decoded by FFmpeg on a worker thread that polls for work every 200 us instead of being woken for each of
  the ~10,000 kicks a second.

## Performance

Busy fights run at 15-25 fps, held by the main thread's own work: ~40-55 ms a frame of world update (the entity
update ~30 %, physics with two substeps a frame ~26 %), spread over hundreds of functions with none above 3 %. The
converted code runs 4-7 x86 instructions per PowerPC one; ~11 % of its time goes to moving guest registers to and
from the context around calls. The physical window's check on every guest load and store cost 4-6 % of the
instructions until v00.47 took it once per base register.

Tried without a measurable gain: floating the light threads over free cores, raising RAGE's task workers (their
waits are 2-7 % of the main thread), `-O2`/`-Os`, and a denser function order (v00.50; a fight's frame rate varies
more from run to run than the layout moved it). Left to try: a liveness-based trim of the context traffic around
calls (what each caller reads after a call), and profile-guided optimisation.

## Diagnostics

- `/data/MP3/logs/mp3_NNN.log`: the version on its first line; `[renut]` lines every 10 s (frames, render-thread and
  GPU time, draws), `[cores]` lines (each core's load and the threads moved), `[io]` and `[xma]` statistics.
- `hang.log`: the freeze report (`mp3_freeze_report`) and every thread's stack; symbolize with `llvm-symbolizer
  --obj=<the eboot's ELF>`.
- CPU profiles (`profiles/profile_N.txt`, numbered per run): every running sample's stack (leaf and four callers),
  waits marked.
- The live console (`mp3_ps4_live.cpp`: a TCP port for `tools/live.py`'s stats, settings, thread dumps, profiles and
  pad input) and RAGE's task hooks (`mp3_ps4_tasks.cpp`) are kept in the source but left out of the build since
  v00.51: set `MP3_LIVE_CONSOLE` / `MP3_TASK_HOOKS` to 1 in `mp3/ps4/mp3_ps4_switches.h` to build them again.

## The game's files

The app reads `game/` and `update/` from its package (`/app0`) when the package holds them, and from `/data/MP3`
otherwise (`mp3_ps4_app.h`, `PackagedFolder`). `/app0` is read-only: the settings, logs, caches and saves always go
to `/data/MP3`.
