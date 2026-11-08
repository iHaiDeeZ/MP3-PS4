# Renut inventory for the Max Payne 3 PS4 port

What Renut (the Direct3D-level renderer of the MGR PS4 port) consists of, what of it is really compiled and reached in
MGR's PS4 eboot, and what moving it into the MP3 tree needs. Read-only survey, 2026-11-07.

Sources: MGR tree `~/mgr-build/src/mgr-nx-deko` (Renut in `app/src/renut_engine`, plume in `app/thirdparty/plume`,
XenosRecomp in `app/thirdparty/reblue-XenosRecomp`), `E:\PS4 Projects\MGR\scripts\build-mgr.sh`,
`E:\PS4 Projects\MGR\patches\mgr-ps4.patch`, MGR's DESIGN.md; MP3 tree `~/mp3-build/src/mp3-nx` (SDK in `sdk/`, game app
in `mp3/`, PS4 project `mp3/ps4/CMakeLists.txt`), `E:\PS4 Projects\MP3\codegen\names.toml`.

How the "compiled / reached" answers were established (not only by reading the sources):

- `~/mgr-build/build-app/build.ninja`: the object list of the PS4 app (which `.cpp` files are built at all).
- MGR's v00.05-v00.09 eboots were built in `~/mgr-build/build-app-opt` from `~/mgr-build/src/mgr-opt`; `diff -rq` of
  `app/src`, `app/mgr_src`, `app/cmake`, `app/thirdparty/plume`, `app/CMakeLists.txt`, `sdk/include/rex`,
  `sdk/src/{ui,system,kernel}` between `mgr-opt` and `mgr-nx-deko` is empty, so the objects there are the objects of
  these sources.
- `llvm-nm-21` on those objects: which guest symbols each object defines (`sub_X`, `renut_native_sub_X`) and which it
  needs (`__imp__sub_X`, kernel exports, SDK symbols).
- `llvm-objdump-21 -d` on those objects: which hardcoded guest addresses survive as x86-64 immediates, and in which
  function; `llvm-objdump-21 -r`: whether anything calls the functions that carry them.
- The two loaded images (`out/default_image.bin`, `mp3/out/codegen/image.bin`) compared function by function with
  scripts (scratchpad `cmp_images.py`, `offsets.py`, `patterns.py`, `listing.py`, `calls.py`, `tiling.py`, `slots.py`).

Address notation: MGR address -> MP3 address. All 32 pairs below are the ones already matched (shape score 1.00).

---

## 0. Short answers

- **Active hooks in MGR's PS4 build: 24 Renut hook bodies** (21 strong `sub_X` definitions in Renut's object library
  plus 3 "shared" bodies `renut_native_sub_X` that MGR's own hooks at Swap, DrawVertices and DrawIndexedVertices call),
  plus 2 originals Renut calls (`__imp__sub_826C0C48`, `__imp__sub_826C0278`). MGR's app glue adds 10 more strong
  guest definitions: the 3 dispatchers of the shared hooks, 2 Direct3D diagnostics (off by default), 2 shader-dump hooks
  (off by default), 1 Wwise DSP leaf, 2 missing-function bodies. Everything else (state.cpp's 255 macros, widescreen,
  photo capture, SA2's hook files, the N&B "native" hook functions) is not compiled or not reached.
- **The only hardcoded guest data address in reached Renut code is the VdGlobalDevice import slot, 0x820005F8 ->
  0x820008CC** (the same load in three matched functions, and the same slot content in both images, section 2.1). Everything else Renut reaches is a CDevice offset, and every offset it
  uses is the same in MP3 (section 2.4). Plus MGR's `kGuestCodeGuards` table, which must be regenerated (MP3 values in
  section 6).
- **Name collisions with MP3's names.toml:** CBlocker_Check 0x8304A1E0 is `mp3_D3D_WaitStep` (Renut hooks it), and
  EngineSwapProgress 0x83058958 is `mp3_D3D_QueryFramesInFlight` (only MGR's glue hooks it). Two more strong-symbol
  clashes come from MP3's own code: `sub_83053808` / `sub_83052950` in `mp3/ps4/mp3_ps4_shader_capture.cpp`.
- **SDK gaps:** `rex/input/read_hook.h` (`rex::input::SetReadHook` and its call in `InputSystem::GetState`) is missing
  in MP3's SDK; `rex::cvar::LoadConfigString` and `ReXApp::BuiltInConfig()/DefaultConfigFile()` are missing (optional);
  MGR glue that Renut drags in needs `rex/sys_counters.h` and `rex/ppc/diet_ops.h` (missing; stub the glue instead).
  Everything else Renut touches has the same signature in MP3's SDK.

---

## 1. Guest-function hooks

### 1.1 The macros and how they are selected

`app/src/renut_engine/gpu/banjo_renut_select.h`:

| Macro | Line | What it emits |
|---|---|---|
| `BANJO_RENUT_HOOK(sub, fn)` | 31-39 | `REX_EXTERN(__imp__sub)` + strong `extern "C" sub()`: `HostToGuestFunction<fn>` when `Active()`, else the original |
| `BANJO_RENUT_HOOK_SHARED(sub, fn)` | 42-45 | only `extern "C" renut_native_sub(ctx, base)`; the app's own hook at `sub` calls it |
| `BANJO_RENUT_HOOK_RAW(sub) { body }` | 48-58 | strong `sub()`: raw body when `Active()`, else `__imp__sub` |
| `BANJO_RENUT_HOOK_RAW_SHARED(sub)` | 60-61 | raw shared body (not used by any compiled file) |
| `BANJO_RENUT_YIELD_SHARED / _YIELD` | 65-74 | first line of an app hook: run Renut's side / the original when `Active()` |
| `SA2_RENUT_YIELD_SHARED` | `gpu/sa2_renut_yield.h:7-15` | = `BANJO_RENUT_YIELD_SHARED` when `SA2_RENUT_RENDERER`, else nothing |
| `RENUT_NOOP(_RETURN)` | `gpu/d3d/hooks/hooks_common.h:13-24` | silent no-ops (used only in state.cpp) |
| `REX_HOOK_RAW(name)` / `REX_EXTERN(x)` / `REX_IMPORT` | `sdk/include/rex/hook.h:66`, `ppc/func.h:46`, `hook.h:246` | SDK's raw hook, declaration, typed import |

Runtime gate: `banjo::renut_gpu::Active()` = cvar `sa2_renderer == "renut"` (default `"renut"`, kInitOnly), latched once
(`banjo_renut_select.cpp:17-23, 30-50`). With it false every hook calls the original.

Selection is **by source list, not by `#if`**. `state.cpp` has no preprocessor guard; `gpu.cmake`'s `renut_gpu_setup`
simply does not list it (`gpu.cmake:263-264`: "not d3d/hooks/state.cpp (N&B's state setters natively, at N&B's
addresses: SA2's own setters write the device the draws read)"), nor `guest/photo_capture.cpp` and
`guest/widescreen.cpp` (`gpu.cmake:269-270`, replaced by `guest/sa2_screen.cpp`: `GuestScreenWidth() = 1280`). Inside
the compiled hook files only the macros of the "sa2-nx: SA2's hooks" section at the end of each file are
instantiated; the N&B "native" hook functions above them are internal-linkage and unreferenced, so the compiler drops
them (confirmed: the objects define and need only the symbols in 1.2).

### 1.2 Hooks compiled into MGR's PS4 eboot (nm of `build-app-opt` objects)

Renut proper (`mgr_renut_gpu` OBJECT library; OBJECT on purpose so the strong definitions are linked,
`app/cmake/mgr_renut_gpu.cmake:8-9`):

| # | MGR | Role | File:line | Macro / body | MP3 | MP3 symbol, notes |
|---|---|---|---|---|---|---|
| 1 | 826B2418 | Direct3D_CreateDevice | device.cpp:1437 | RAW -> `Sa2CreateDevice` (1319-1414): guard check, original with type 2, title-device fields, original InitializePresentationParameters + InitializeApiState | 8304AA58 | sub_8304AA58 |
| 2 | 826B59B0 | D3DDevice_InsertCallback | device.cpp:1440 | HOOK -> `D3DDevice_InsertCallback_hook` (988-994) | 83055AC0 | sub_83055AC0 |
| 3 | 826B3050 | SynchronizeToPresentationInterval | device.cpp:1441 | HOOK -> `Sa2SynchronizeToPresentationInterval_hook` (1429-1433): only the pending flag | 830589E8 | sub_830589E8; replaces the function that queues the swap callback 83058080 |
| 4 | 826B5688 | CDevice::KickOff | device.cpp:1442 | HOOK -> `KickOff_hook` (512-522) | 83055798 | sub_83055798 |
| 5 | 826B5348 | CDevice::KickOffSegment | device.cpp:1443 | HOOK -> `KickOffSegment_hook` (525-532) | 83055410 | sub_83055410 |
| 6 | 826B58C0 | CDevice::BeginRingBig | device.cpp:1444 | HOOK -> `BeginRingBig_hook` (536-543) | 830559D0 | sub_830559D0 |
| 7 | 826B4078 | RingBufferDeviceAllocate | device.cpp:1445 | HOOK -> `RingBufferDeviceAllocate_hook` (566-568) | 830540E0 | sub_830540E0 |
| 8 | 826B44C0 | CDevice inline data allocation | device.cpp:1446 | HOOK -> `AllocateInlineData_hook` (572-574) | 83054588 | sub_83054588 |
| 9 | 826B45A8 | ring segment allocator (NewSegment) | device.cpp:1447 | HOOK -> `Sa2NewSegment_hook` (1418-1425) | 83054670 | sub_83054670 |
| 10 | 826B5A08 | D3DDevice_SetRingBufferParameters | device.cpp:1448 | HOOK -> no-op S_OK (579-581) | 83055B18 | sub_83055B18 |
| 11 | 826B3510 | D3DDevice_Swap | device.cpp:1449 | SHARED -> `D3DDevice_Swap_hook` (878-978) | 83058EA8 | sub_83058EA8; dispatcher in MGR glue (row 25) |
| 12 | 826B42A8 | CDevice::BlockOnFence | device.cpp:1450 | HOOK -> `BlockOnFence_hook` (590-619) | 83054310 | sub_83054310 |
| 13 | 826B1C88 | CBlocker::Check | device.cpp:1451 | HOOK -> returns 0 (642-644) | 8304A1E0 | **named `mp3_D3D_WaitStep`** (names.toml:25-26); also hooked by `mp3/src/mp3_perf_hooks.cpp:106-140` |
| 14 | 826B57C8 | D3DDevice_IsFencePending | device.cpp:1452 | HOOK -> `IsFencePending_hook` (625-637) | 830558D8 | sub_830558D8 |
| 15 | 826BC928 | D3DDevice_DrawVertices | draw.cpp:602 | SHARED -> `D3DDevice_DrawVertices_hook` (107-118) | 8304B000 | sub_8304B000; dispatcher row 27 |
| 16 | 826BCD40 | D3DDevice_DrawIndexedVertices | draw.cpp:603 | SHARED -> `D3DDevice_DrawIndexedVertices_hook` (122-136) | 8304B418 | sub_8304B418; dispatcher row 26 |
| 17 | 826BC468 | D3DDevice_BeginVertices | draw.cpp:606 | HOOK -> `D3DDevice_BeginVertices_hook` (209-235) | 8304AB40 | sub_8304AB40 |
| 18 | 826B5FC8 | window/scissor register writer | draw.cpp:611-619 | RAW: mirrors the 3 WindowPacket words, then original | 83046A00 | sub_83046A00 |
| 19 | 826BC260 | D3DDevice_ClearF | draw.cpp:623-632 | RAW: queue host clear, then original | 8304C9D0 | sub_8304C9D0 |
| 20 | 826BB0D0 | D3DDevice_Resolve | draw.cpp:640-654 | RAW: queue host resolve (stencil from `r1+92`), then original | 8304F300 | sub_8304F300 |
| 21 | 826ACD00 | XGRegisterVertexShader | shader.cpp:476-480 | RAW: original, then `RegisterGuestShader` | 83053808 | sub_83053808; **also defined by `mp3/ps4/mp3_ps4_shader_capture.cpp:140-145`** |
| 22 | 826AC3D8 | XGRegisterPixelShader | shader.cpp:483-487 | RAW: original, then `RegisterGuestShader` | 83052950 | sub_83052950; **also defined by `mp3_ps4_shader_capture.cpp:148-153`** |
| 23 | 826AC938 | D3DDevice_CreateVertexDeclaration | shader.cpp:490-496 | RAW: original, then `RegisterGuestDeclaration` | 83052EB0 | sub_83052EB0 |
| 24 | 826AAF80 | D3DResource_Destroy | resource.cpp:1696-1705 | RAW: queue host releases, then original | 8305C968 | sub_8305C968 |
| - | 826C0C48 | InitializePresentationParameters (original called) | device.cpp:1312, 1398 | `REX_EXTERN(__imp__)` | 830614E8 | __imp__sub_830614E8 |
| - | 826C0278 | InitializeApiState (original called) | device.cpp:1313, 1406 | `REX_EXTERN(__imp__)` | 83060B18 | __imp__sub_83060B18 |

Kernel exports the same objects need: `__imp__KeQueryPerformanceFrequency`, `__imp__RtlInitializeCriticalSection`
(device.cpp:75-76; both `REX_EXPORT`ed by MP3's SDK too, `xboxkrnl_threading.cpp:1463`, `xboxkrnl_rtl.cpp:617`).

MGR app glue (`sa2` target), compiled with `MGR_RENUT_RENDERER=1`, `MGR_NATIVE_RENDERER=0`:

| # | MGR | Role | File:line | Active | MP3 | Needed for MP3 |
|---|---|---|---|---|---|---|
| 25 | 826B3510 | Swap dispatcher: `mgr_fps_limit` sleep, `mgr_dump_memory`, then `SA2_RENUT_YIELD_SHARED` | mgr_src/mgr_me_hooks.cpp:205-254 | yes | 83058EA8 | yes (the dispatcher; the diagnostics are optional) |
| 26 | 826BCD40 | DrawIndexedVertices dispatcher (+ `mgr_renut_diag_original_draw`) | mgr_me_hooks.cpp:256-274 | yes | 8304B418 | yes |
| 27 | 826BC928 | DrawVertices dispatcher | mgr_me_hooks.cpp:276-294 | yes | 8304B000 | yes |
| 28 | 826CB580 | draw-time shader load: shader-object dump (`mgr_dump_shaders`, off) | mgr_me_hooks.cpp:177-200 | yes, pass-through | 8305E978 | no |
| 29 | 826B2FC0 | engine GPU wait: 50 us sleep (`mgr_gpu_wait_sleep`, off) | mgr_me_hooks.cpp:332-342 | yes, pass-through | 83058958 | no; **named `mp3_D3D_QueryFramesInFlight`**, MP3 already hooks it (`mp3_perf_hooks.cpp:86-100`) |
| 30 | 826ACDF8 | D3DDevice_CreateVertexShader container dump (off) | mgr_src/mgr_shader_dump.cpp:114-118 | yes, pass-through | 83053900 | no |
| 31 | 826ACC10 | D3DDevice_CreatePixelShader container dump (off) | mgr_shader_dump.cpp:120-124 | yes, pass-through | 83053718 | no |
| 32 | 825B4070 | Wwise DSP leaf (MGR audio) | mgr_src/mgr_wwise_dsp.inc:232-233 | yes | - | no (MGR game code) |
| 33 | 824410D8, 824410F0 | functions MGR's code generator missed | mgr_src/mgr_missing_functions.cpp:22, 32, 49-50 | yes | - | no (MGR game code) |

Label correction: 826ACDF8 is **CreateVertexShader** (it clears 872 bytes, `li r5,872`, and calls XGRegisterVertexShader
826ACD00) and 826ACC10 is **CreatePixelShader** (it calls XGRegisterPixelShader 826AC3D8); MP3's 83053900 calls
83053808 and 83053718 calls 83052950. The pairs given in the task are right, their two labels are swapped
(`mgr_shader_dump.cpp:4-7` has it right; mp3-nx's names.toml, by the distance rule, gives the same).

### 1.3 Compiled out, or other games'

| Where | What | Why not in MGR's eboot |
|---|---|---|
| `gpu/d3d/hooks/state.cpp` | 247 `BANJO_RENUT_HOOK` + 8 `BANJO_RENUT_HOOK_SHARED`, N&B's (Banjo-Kazooie: Nuts & Bolts, XDK 2.0.7645) render/sampler state setters and getters, Set*/Get* at N&B addresses | not in `gpu.cmake`'s source list (263-264); no `#if` |
| `gpu/guest/widescreen.cpp:228-276` | 6 RAW hooks at N&B game addresses (823ED828 screen size, 823191B8 pools, 82364C78 XPhysicalAlloc, 82239C40 / 82236148 camera aspect, 82205C88 XuiRenderSetViewTransform) | not in `gpu.cmake` (269) |
| `gpu/guest/photo_capture.cpp:124` | `BANJO_RENUT_HOOK(sub_82535F20, PhotoCapture_hook)` (N&B's photo mode) | not in `gpu.cmake` (269) |
| `gpu/d3d/hooks/device.cpp` 180-467, 473-492, 546-549, 660-862, 1006-1238 | N&B "native" bodies: XenonGpuInitialize, InitializeApiState, InitializePresentationParameters, InitializeTitleDevice, Direct3D_CreateDevice_hook; Release; BeginRingManual; ConfigureForOnePassZPass, Begin/End/RunCommandBuffer; AddRef, Acquire/ReleaseThreadOwnership, GetDeviceCaps, GetDisplayMode, D3DDevice_BlockOnFence, SynchronizeToPresentationInterval (N&B), GetDevice, IsFusion, gamma tables, SetGammaRamp, SetPWLGamma and the D3D_* internals (the rest of the file between them is reached by the hooks in 1.2) | compiled, internal linkage, never referenced: dropped |
| `gpu/d3d/hooks/draw.cpp` 138-202, 237-561 | N&B bodies: DrawIndexedTessellatedVertices, DrawVerticesUP, DrawIndexedVerticesUP, Clear() / Resolve() and the N&B ClearF/Clear/Resolve hooks, BeginTiling/EndTiling, BeginExport/EndExport, Present, Set{Vertex,Pixel}Shader | same |
| `gpu/d3d/hooks/shader.cpp` 253-280, 328-443 | N&B bodies: CreateShaderRecord, XGRegister*_hook (native), Create{Vertex,Pixel}Shader, CreateVertexDeclaration (native), D3DVertexShader_Bind (`RegisterGuestShader` 284-326 is reached) | same |
| `gpu/d3d/hooks/resource.cpp` 47-1685 | N&B's native resource layer (creation, locks, layouts, AddRef/Release, XMemFree/MmAllocatePhysicalMemoryEx imports) | same; external `native::CreateSurface` / `native::AddRefResource` are linked but nothing calls them (no relocation anywhere) |
| `gpu/d3d/d3d_native_state.cpp` | N&B's state layer (`native::InitializeStateTables`, `SetRenderState`, `Resolve`, `BeginExport`...) | linked (external), never called: only relocations are its own internal calls |
| `app/mgr_src/mgr_me_hooks.cpp:296-322` | 826CA7E8, 826CA450, 826CA690 (constant / register / fetch flushes, MP3 8305DBE0 / 8305D848 / 8305DA88) | `#if MGR_NATIVE_RENDERER` (0 with Renut) |
| `app/mgr_src/mgr_d3d_census.cpp` | ~1,035 counting hooks over the D3D range | `MGR_D3D_CENSUS` OFF (`app/CMakeLists.txt:55-58`) |
| `app/src/me/sa2_me_hooks.cpp`, `sa2_d3d_api.cpp`, `sa2_api_*.cpp`, `src/cpu/sa2_hot_guest.cpp` (80), `sa2_gpu_wait.cpp`, `src/sa2_d3d_trace.cpp`, `sa2_debug_hooks.cpp`, `src/main.cpp` | SA2's hooks, SA2's native D3D layer and SA2's entry point | not in MGR's source lists (`app/CMakeLists.txt:82-86` says so) |

---

## 2. Hardcoded guest addresses

Code constants only (comments ignored); the large counts in the task (91 in d3d_native_state.cpp, 11 in
texture_layout.h, ...) are mostly N&B function addresses in comments. "Reached" = present as an immediate in a function
the program can reach (objdump + relocations, section 0).

### 2.1 The one that matters: VdGlobalDevice

`device.cpp:127` `kVdGlobalDeviceImportSlot = 0x820005F8` - the XEX import slot holding the address of the kernel
variable `VdGlobalDevice` (xboxkrnl ordinal 0x01BE; MP3's SDK allocates it in the 4 KB-page physical heap,
`xboxkrnl_video.cpp:532-537`). Reached from `Sa2CreateDevice` (device.cpp:1385-1386, stores the title device there) and
`native::GlobalDevice` (1260-1263, used by `IsFencePending_hook` 630). MGR-specific value.

**MP3: 0x820008CC.** Evidence:

- Same instruction in three matched functions: HardwareDeviceSetup +0x74 (`lis r11,0x8200; lwz r11,1528(r11)` ->
  MP3 `lwz r11,2252(r11)`), IsFencePending +0x3C, D3DResource_Destroy +0x34. The XDK's pattern there is
  `KeGetCurrentProcessType(); cmpwi 2`: process type 2 uses the next slot (MGR 0x820005FC / MP3 0x820008D0, the
  system-process device), the title uses this one.
- The dumped images hold the resolved variable addresses: MGR [0x820005F8] = MP3 [0x820008CC] = 0xFFCAE000,
  MGR [0x820005FC] = MP3 [0x820008D0] = 0xFFCAD000; no other slot in the first 128 KB holds 0xFFCAE000.

(Writing through it needs the PS4 4 KB host offset for 0xE0000000+, which Renut's `GuestPtr` adds,
`guest/guest_memory.h:49-54`; MP3's SDK has the same `PhysicalHostOffset`, `rex/system/xmemory.h:43-49`.)

### 2.2 By file

| File:line | Constant | What | Reached in MGR | MGR-correct? | MP3 equivalent |
|---|---|---|---|---|---|
| device.cpp:118 | 0x834FB7E0 `kGlobalQwordVa` | D3D global qword copied into every device (+11008) | no (native CreateDevice only) | yes (XenonGpu_Initialize +0x20 `ld` reads 0x834FB7E0) | **0x831D3BA8** (same instruction) |
| device.cpp:127 | 0x820005F8 | VdGlobalDevice import slot | **yes** | yes | **0x820008CC** |
| device.cpp:1002 | 0x82183B00 `kDeviceCapsVa` | N&B's constant D3DCAPS9 for GetDeviceCaps | no | N&B's | not needed; would be the copy source in MP3's D3DDevice_GetDeviceCaps (not matched) |
| device.cpp:1004 | 0x82F597B4 `kFusionVa` | N&B's "Fusion GPU" flag, D3D::IsFusion | no | N&B's | not needed; the word D3D::IsFusion loads |
| device.cpp:74-78 | `__imp__rex_GetCurrentThreadId`, `__imp__KeGetCurrentProcessType`, `__imp__VdGetCurrentDisplayGamma` | REX_IMPORTs for the native path | no | - | `__imp__rex_GetCurrentThreadId` exists in **neither** SDK: only the optimizer's dead-code removal keeps it out of the link (a -O0 build would fail) |
| draw.cpp:52 | 0x820018DC `kFullViewport` | N&B's D3DVIEWPORT9 {0,0,0xFFFF,0xFFFF,0,1} (BeginTiling/EndTiling) | no | N&B's (MGR's is 0x8213B474) | **0x8212D658** (found by content) |
| resource.cpp:50 | `__imp__sub_82715A90` (GameXMemFree) | the game's XMemFree | no (resource.obj has no reference) | yes (D3DResource_Destroy calls 82715A90) | **0x821E05D8** (same call in MP3's D3DResource_Destroy and both Create*Shader); fix or delete |
| resource.cpp:97 | 0x82F39E34 `kGameNoLargePagesVa` | XPhysicalAlloc's "no large pages" flag | no | N&B's | not needed; the global XPhysicalAlloc tests |
| resource.cpp:122 | 0x820052F8 `kFormatTable` | GPU format table (u16 per D3D format, low byte = bpp) | linked, unreachable (`native::CreateSurface`) | N&B's (MGR's is 0x8213AEE0) | **0x8212D838** (found by content: the 64 low bytes equal `texture_layout.cpp:14-20`'s table) |
| resource.cpp:134 | 0x82FA36C8 `kHiZOwnerVa` | word set while a depth surface owns HiZ | linked, unreachable | N&B's | not needed; the global CreateDepthStencilSurface tests |
| d3d_native_state.cpp:730-731 | 0x82E506F0 / 0x82E50BD0 | N&B's render / sampler state tables {getter, setter, default} | linked, unreachable (`native::InitializeStateTables`) | N&B's (MGR's: 0x834FB228 / 0x834FB6E8, InitializeApiState +0x20/+0x80) | **0x831D3598 / 0x831D3A58** (same instructions; 12-byte stride confirmed) |
| d3d_native_state.cpp:1365 | 0x820052F8 | format table again (`native::Resolve`) | linked, unreachable | N&B's | 0x8212D838 |
| d3d_native_state.cpp:1612-1613 | 0x82FAD204 / 0x82FAD208 | N&B's switches for the memexport GPU workarounds | linked, unreachable | N&B's | not needed |
| texture_layout.h:8-19 | (comments only) | N&B function addresses | - | - | none; `texture_layout.cpp` uses a host table |
| photo_capture.cpp:49 | 0x82FAC7C0 `kDevicePointer` | N&B's D3DDevice global | not compiled | N&B's | not applicable (N&B game code) |
| widescreen.cpp:39-61 | 0x82FADD20, 0x82FADDE8, 0x82F835E8, 0x82F835B0, 0x82F835B4, 0x82F835B8, 0x82F835D0, 0x82F8336C, 0x82F833A0, 0x82F833D4, 0x82F83408 | N&B camera, aspect, screen-pool globals | not compiled | N&B's | not applicable |
| render/draw.cpp:848-853 | 0xE0000000, 0xE0001000, 0xA0000000, 0x7F000000 | Xbox 360 memory-map (VA -> GPU physical) | yes | generic | same |
| mgr_me_hooks.cpp:117, 180-188 | 0x40000000-0x7F000000 | heap range check (diagnostics) | yes | generic | same |
| mgr_me_hooks.cpp:222 | 0x098EC000... | MGR's diagnostic pages (`mgr_dump_memory`) | yes, off | MGR's | not needed |
| mgr_hook_map.h:6-36 | 29 MGR addresses + FNV-32 of their first 32-64 bytes | `kGuestCodeGuards`, checked by `Sa2CreateDevice` (device.cpp:1322-1339): a mismatch makes CreateDevice return E_FAIL | **yes** | MGR's | MP3 table in section 6 |

### 2.3 Other D3D data the matched functions reference (for reference; Renut does not read them)

| Function (+offset) | MGR | MP3 | Probably |
|---|---|---|---|
| CBlocker_Check +0xA8 | 0x834FB220 | 0x831D3B48 | blocker setting word |
| KickOff +0xA8, Swap +0x570, HardwareDeviceSetup +0x240 | 0x836A4A14 | 0x8385BE68 | D3D global (r/w) |
| Swap +0x204 | 0x836A4A08 | 0x8385BE74 | D3D global |
| D3DResource_Destroy +0xB4 | 0x836A4A04 | 0x8385BE70 | D3D global |
| CreatePixelShader / CreateVertexShader +0x14 | 0x836A49F8 / 0x836A49FC | 0x8385BE5C / 0x8385BE60 | the "global filter" of `mgr_shader_dump.cpp:64` |
| draw state setup +0x2A0..+0x2C4 | 0x836A5FA0 / 0x836A5FA4 | 0x8385BE98 / 0x8385BE9C | D3D globals |
| SynchronizeToPresentationInterval +0x134 | 0x826B26E8 | **0x83058080** | the swap callback it queues (= `mp3_D3D_SwapCallback`) |
| HardwareDeviceSetup +0x198 | 0x82000520 | 0x820007EC | another kernel variable slot (both hold 0x30002000) |
| DrawVertices / DrawIndexedVertices +0x268 / +0x274 | 0x8218C968 | 0x82000AE0 | a table |
| SetRingBufferParameters +0x298 | 0x8213B454 | 0x8212DB20 | a table |
| D3DResource_Destroy +0x54, +0x68 | 0x8213AED0, 0x826AAFF8 | 0x8212DDB0, 0x8305C9E0 | table; jump table |
| InitializePresentationParameters +0xDC, HardwareDeviceSetup +0x208, ClearF +0x11C | 0x820D0814, 0x820D0D98, 0x820D1A08 | 0x8202C5AC, 0x820BF6B0, 0x820A66CC | float constants |

Apart from these addresses (and branch displacements), the 32 function pairs are word-for-word identical: every other
differing word is the `lis` high half of one of these addresses.

### 2.4 CDevice offsets Renut's reached code uses, checked in MP3

`tools/mgr_renut_hooks.py`'s 87 instruction witnesses (device offsets, stack slots, calls) were re-checked against
MP3's functions: all 29 functions pass (calls translated through the call map). Separately (`offsets.py`), every
private offset the reached code writes or reads appears at the same instruction in both images:
11008, 11016, 11020, 11024, 11028, 11036, 11056, 11068, 11069, 13600, 14000, 15344, 15348, 15376, 15408, 16968, 16976,
17136, 21968, 21972, 21996, 24392 (plus the d3d.h / d3d_native.h ones the witnesses cover: 12812, 12816, 12832, 12904,
13084, 13088, 13844, 13920, 13948, 15232, 15236, 15308, 15320, 15332). MP3 links 21076, the layout `d3d.h` was written
for (SA2); the tile count 13124 (`native::off::TileCount`) is also MP3's (its BeginTiling 0x8304CEB8 stores there).

---

## 3. Renut's dependencies on the SDK

Exact list of what Renut's compiled objects need from outside (`nm -u`, demangled): `rex::GetLoggerRaw`,
`rex::RegisterLogCategory`, `rex::cvar::{FlagRegistrar::apply_, RegisterFlag, UnregisterFlag}`,
`rex::filesystem::GetExecutableFolder`, `rex::input::SetReadHook`, `rex::memory::Memory::{HostToGuestVirtual,
LookupHeapByType}`, `rex::runtime::ResolveIndirectFunction`, `rex::runtime::ThreadState::Get`,
`rex::system::shared_kernel_state_` (MGR's inline `kernel_state()`), `rex::ui::ImmediateDrawer::{Begin, End,
ScissorToRenderTarget}` + its typeinfo, `rex::ui::WindowedAppContext::CallInUIThreadDeferred`, kernel exports
`__imp__KeQueryPerformanceFrequency` / `__imp__RtlInitializeCriticalSection`, fmt v12 and spdlog, `o1heap*`; plus
plume, `vk*` (RADV), XXH3, ZSTD, smol-v; and from MGR's app: `g_sa2_game_frames`, `sa2::capture::RenutLockstep{On,
Frame}`, `sa2::enh::{CpuMaster, NonCpuMaster}`, `sa2::render::{Docked, OnPresented, RenderHeightOf}`.

| SDK piece | Renut's use | MP3 SDK |
|---|---|---|
| `rex/hook.h` | REX_IMPORT, REX_EXTERN, REX_HOOK_RAW, HostToGuestFunction (via the macros) | compatible; differs only by MGR's `REX_EXPORT_CENSUS` / `sys_counters.h` include (not used by Renut) |
| `rex/ppc/function.h`, `rex/ppc/func.h` | HostToGuestFunction / GuestToHostFunction, `REX_FUNC`, `rex::runtime::ResolveIndirectFunction` (guest callbacks) | same (func.h adds `ResolveModuleImport`) |
| `rex/system/kernel_state.h` | `REX_KERNEL_MEMORY()`, `kernel_state()` | compatible: `kernel_state()` is out of line in MP3 (MGR made it inline, `kernel_state.h:403-413`); recompiling is enough |
| `rex/system/xmemory.h` | TranslateVirtual / Physical, HostToGuestVirtual, LookupHeapByType, GetPhysicalAddress, `BaseHeap::Alloc`, `detail::PhysicalHostOffset` | compatible; `PhysicalHostOffset` identical including the PS4 (0x1000 for >= 0xE0000000); MP3's TranslateVirtual does a heap lookup (MGR: inline sum), Renut's own `GuestPtr` has the PS4 sum anyway |
| `rex/memory/utils.h` | (PhysicalHostOffset users) | same file |
| `rex/system/xvideo.h`, `rex/kernel/xboxkrnl/video.h` | `X_VIDEO_MODE`, `VdQueryVideoMode` (dead native path only) | compatible; MGR's extra `VdSwapCount / VblankPerSwap / WaitSwapForVblank` are not used by Renut |
| `rex/input/read_hook.h` | `render_thread.cpp:386-394`: `SetReadHook` -> `rex::latency::BeforeInputRead` (late input) + `NoteInputRead` (latency probe) | **missing**: header and the 4 lines in `InputSystem::GetState` (MGR `sdk/src/input/input_system.cpp:16, 260-264`) |
| `rex/cvar.h` | REXCVAR_* (Renut defines 148 cvars, none collides with MP3's 475) | compatible; MGR's `LoadConfigString` (cvar.h:124-126) **missing** |
| `rex/rex_app.h` | (MGR glue) detached mode: `OnPreSetup`, `OnCreateImmediateDrawer`, `OnFinalizePaths`, `OnWindowPixelSizeChanged`, `OnPostLaunchModule`, `OnCreateDialogs`, `OnShutdown` | all present, MP3's `SetupPresentation` handles `config.graphics == nullptr` (`rex_app.cpp:344-427`); MGR's `BuiltInConfig()` / `DefaultConfigFile()` **missing** (optional: Renut's defaults already give renut + vulkan + 720 lines on the PS4) |
| `rex/ui/presenter.h` | `RawImage`, `UIDrawContext`, `AppUIDrawContext` | compatible (MP3 renamed private members only) |
| `rex/ui/imgui_drawer.h` | `HasDialogs`, `Draw` (OverlayPump), drawer getter | compatible (MP3 adds `SetContinuousRepaint` / `RequestRepaint`) |
| `rex/ui/immediate_drawer.h`, `rex/ui/windowed_app_context.h` | `OverlayDrawer : ImmediateDrawer`, `CallInUIThreadDeferred` | same files |
| `rex/logging.h`, `rex/filesystem.h`, `rex/types.h`, `rex/ppc.h`, `rex/runtime.h`, `rex/platform.h` | logging, executable folder, be_u32 / mapped_u32, RuntimeConfig, REX_PLATFORM_PS4 | same or compatible |
| `rex/sys_counters.h` | not Renut: MGR glue `src/cpu/sa2_enhancements.cpp` / `sa2_codegen_checks.cpp` (`rex::syscount::Census*`, `ExportCensus`) | **missing** |
| `rex/ppc/diet_ops.h` | not Renut: MGR glue `src/cpu/sa2_forms_selfcheck.cpp` | **missing** |
| `RexSetGuestThreadCoreLayout` | device.cpp:71, 888, only under `REX_PLATFORM_SWITCH` | not needed on the PS4 (MP3's SDK does not have it) |
| third party | fmt v12, spdlog, o1heap (`rex::o1heap` alias made by `mgr_renut_gpu.cmake:38-41`), ImGui headers 1.92.5 | MP3's SDK thirdparty is copied from the same rexglue-sdk v0.10.0 (`build-mp3.sh`: `UP=~/mgr-build/src/rexglue-sdk`); o1heap target present; ImGui 1.92.5 in both |

Gaps to close: (1) `rex/input/read_hook.h` + the `GetState` call (or compile the late-input/latency hook out of
`render_thread.cpp`); (2) for MGR's app pattern only, `LoadConfigString` + `BuiltInConfig` (or drop the override);
(3) the glue's `sys_counters.h` / `diet_ops.h` users (do not port them: stub `sa2::enh`, section 4).

Behaviour differences that are not link gaps: MP3's SDK applies the game's thread priorities and affinities on the
PS4 (`xthread.cpp`: `ignore_thread_priorities/affinities` default false, `ps4_game_cores 7`, `ps4_service_thread_priority
600`), MGR's ignores them; MP3 renamed cvars (`input_rumble` -> `input_vibracion`).

---

## 4. The app-level glue Renut needs

### 4.1 What MGR's app provides (`app/mgr_src/mgr_main.cpp`, class `MgrApp : rex::ReXApp`)

| Hook / file | What it does for Renut | MP3 |
|---|---|---|
| `BuiltInConfig()` (186-213) | `sa2_renderer = "renut"`, `renut_gpu_backend = "vulkan"`, `sa2_renut_msaa = 0`, `sa2_render_height_* = 720` (PS4), `input_xbox_layout`, `mgr_shared_input` | optional: those are the defaults on the PS4 already (`backend/backend.cpp:62-65`: off Windows the backend is Vulkan unless the key says deko3d; `sa2_renderer` defaults to `"renut"`, `sa2_renut_msaa` to 0, and `sa2::render::Docked()` is false on the PS4, so the handheld height 720 applies) |
| `OnPostInitLogging` (217-242) | `sa2::enh::Resolve()`: latches the enhancement masters | **required in some form**: `CpuMaster()/NonCpuMaster()` are false until `Resolve()` runs (`sa2_enhancements.cpp:155-179`), and every `banjo_*` enhancement Renut checks (`sa2_compat/cpu/banjo_enhancements.h:12-14`) is then off |
| `OnPreSetup` (299-324) | input factory with `SharedAssignment` (MGR's single profile); `renut::gpu::ConfigureRuntime(config)`: `config.graphics = nullptr; config.gpu_plugin.clear()` (`overlay/app_integration.cpp:86-89`) | MP3's `OnPreSetup` sets `gpu_plugin = "xenos"` (`mp3/ps4/mp3_ps4_app.h:60-61`) and `mp3::fps::ApplyBeforeGraphics()`: must call ConfigureRuntime instead when Renut is on |
| `OnCreateImmediateDrawer` (392-395) | `renut::gpu::CreateOverlayDrawer()`: the plume ImmediateDrawer the SDK's ImGui draws through (detached mode) | add |
| `OnFinalizePaths` (402-409) | `renut::gpu::StartRenderer(app_context, imgui_drawer)` (app_integration.cpp:95-121): `Video::CreateHostDevice()` (plume Vulkan device + swapchain on VideoOut), overlay hook, `OverlayPump` thread recording the SDK menus every 16 ms on the UI thread and presenting overlay-only frames when the guest does not present | add |
| `OnWindowPixelSizeChanged` (397-400), `OnShutdown` (460-478) | `OnWindowResized()`, `ShutdownRenderer()`, `sa2::capture::Stop()` | add |
| `OnPostSetup` (416-458) | `mgr::RegisterMissingFunctions` (MGR), `sa2::enh::StartReport()`, `sa2::render::RegisterKeys()`, `sa2::capture::StartWithSource(CaptureFrame)` (test recorder) | only the report is useful |
| `OnPostLaunchModule` (380-390) | `thread->SetAffinity(1)`: MGR's job scheduler indexes by the guest PCR's CPU | MGR game logic; MP3's SDK applies the game's affinities itself |
| `OnCreateDialogs` (375-377), `mgr_ps4_menu.cpp` | L3+R3 menu over Renut's cvars (`sa2_render_height_handheld`, `renut_fsr`, `renut_fsr_sharpness`) and `renut::frame_stats::Get()` | MP3 has its own menu (`mp3_ps4_menu.cpp`); its frame counter counts `mp3_D3D_SwapCallback`, which never runs under Renut: switch it to `renut::frame_stats` |
| `mgr_me_hooks.cpp` | the 3 dispatchers (rows 25-27); diagnostics | port the dispatchers (or make the three Renut hooks non-shared) |
| `src/sa2_capture.cpp` | defines `g_sa2_game_frames` and `RenutLockstep{On,Frame}`, needs `sa2::profile::SnapshotThreadCycles` (`src/profiler/sa2_thread_cycles_pc.cpp`) | stub the three symbols |
| `src/cpu/sa2_enhancements.cpp` (+ `sa2_codegen_checks.cpp`, `sa2_forms_selfcheck.cpp`) | `sa2::enh::CpuMaster/NonCpuMaster/Register/Resolve/StartReport`, MGR's codegen self-checks; needs `rex/sys_counters.h`, `rex/ppc/diet_ops.h` | replace with a small `sa2::enh` (masters from the two cvars, `Register` a no-op) |
| `src/me/sa2_render_mode.cpp` | `sa2::render::Docked()` (false on the PS4), `RenderHeightOf()`, `OnPresented()`, cvars `sa2_render_height_handheld` (720) / `_docked`; `rex::ui::RegisterBind` | port as is (portable) |
| `mgr_src/mgr_sa2_stubs.cpp` | `sa2_cpu_verify` cvar, `sa2::api::Report()` stub | port |
| `mgr_src/mgr_ps4.cpp` | `PS4_DIAG_DATA_DIR("/data/MGR")` | MP3 has its own (`mp3_ps4.cpp`) |
| `src/renut_engine/sa2_compat/*` | `rex::latency` probe (`frame_latency.cpp`), `g_banjo_store_cards = false`, `RexStoreCardsHostBytes`, banjo/masseffect cvars (`sa2_compat.cpp:10-15`), `profiler/profiler.h` shim | part of Renut, port as is |
| headers Renut includes from the app | `cpu/sa2_enhancements.h`, `me/sa2_render_mode.h`, `sa2_capture.h`, `me/me_platform_compat.h` (Switch helpers, no-ops elsewhere; includes simde) | bring or shim |

### 4.2 How Renut runs inside the SDK

- **Activation:** `banjo::renut_gpu::Active()` (1.1). MGR builds without the Xenos plugin on the PS4
  (`app/CMakeLists.txt:66-72`: `rexglue_setup_target(sa2)` with no `GPU_PLUGINS`); MP3 links it whole
  (`mp3/ps4/CMakeLists.txt:129`).
- **Replacing the SDK graphics system:** `ConfigureRuntime` empties `config.graphics` and `config.gpu_plugin`, so
  ReXApp's detached mode creates no presenter and asks the app for an ImmediateDrawer. The kernel's Vd* calls run
  without a graphics system (`VdSetGraphicsInterruptCallback`, `VdInitializeRingBuffer`... warn once and return,
  same code in both SDKs). Consequence: **the guest gets no graphics interrupts at all** (no vblank, no swap retire
  through the interrupt callback).
- **Command ring:** a 4 MB sink that every kick rewinds (device.cpp:86-90, `native::RewindRing` 1244-1250); inline
  data from a 1 MB circle; nothing reads either.
- **Draws:** Renut reads the device's shadow state (kept by the game's own D3D: state setters, Clear's and Resolve's
  device work, the Present stay the game's code) at each Draw/DrawIndexed/BeginVertices and queues the draw to its
  render thread (`backend/queued.cpp`), which records plume commands (optionally replayed by the record worker).
- **Fences:** KickOff and Swap queue a fence completion that the render thread writes once it has read the batch
  (`KickFence` 158-164); BlockOnFence waits for it; InsertCallback's guest callbacks run on guest threads when the
  render thread has reached them (`guest/callbacks.cpp`).
- **Shaders:** XGRegister{Vertex,Pixel}Shader assemble the container (virtual part at +0x368 / +0x28, then the physical
  part), XXH3-64 it, look it up in the built-in cache (`render/shader_library.cpp:68-89`); a missing one is written to
  `<exe folder>/shader_capture/{vs,ps}_<hash>.bin` (`shader_library.cpp:169-193`, cvar `renut_shader_capture_dir`).
- **Presentation:** `D3DDevice_Swap_hook` (878-978): pacing (`sa2::renut::PaceSwap`, `sa2_renut_pacing.cpp:150-206`,
  60 Hz grid at the interval in device+14000), frame stats, latency probe, fence, then `render_thread::QueueFrame`:
  the front-buffer texture (the one the game resolved into) through `Video::Present` (`backend/present.cpp`: FSR 1 or
  bilinear, the game's gamma ramp from device+15408, the SDK's ImGui overlay), and **device+16976 = swap count after
  the present** (955-958) in place of the vblank handler, which is what MGR's engine and MP3's
  `QueryFramesInFlight` read.
- **Render thread and other threads:** all `std::thread`s on the PS4, default priority, not pinned
  (`banjo_renut_tuning.cpp:1311-1322` and `1351-1373` do priority/core only on the Switch): render thread
  (`render_thread.cpp:229`), record worker (`banjo_renut_record.cpp:616`), ring cleaner (`backend/video.cpp:586`),
  stream-check worker (`render/draw.cpp:981`), pipeline prebuild workers (`render/pipeline.cpp:907`), pipeline-cache
  saver (`banjo_renut_tuning.cpp:1455`), overlay pump (`overlay/app_integration.cpp:54`).
- **Input:** the SDK's own (scePad). Renut only adds the read hook (late input + latency probe).
- **Guest memory Renut takes** (64 KB-page physical heap, `guest/guest_records.cpp:40-56`): 8 MB record arena
  (`kHeapSize`, 21-27, under `MGR_RENUT_RENDERER`), 4 MB ring sink, 1 MB ring data, a 64 KB fence block, 4 MB vertex
  scratch per device that uses BeginVertices.

### 4.3 MGR or SA2 game logic MP3 does not need

`mgr_wwise_dsp.inc`, `mgr_missing_functions.cpp`, `mgr_shader_dump.cpp`, the `mgr_me_hooks.cpp` diagnostics
(`mgr_fps_limit`, `mgr_dump_memory`, shader-object dump, `mgr_gpu_wait_sleep`), `SharedAssignment` input, the
`SetAffinity(1)` workaround, `sa2_capture`'s recorder, the codegen self-checks, the `[mgr-state]`/`[mgr-surface]`
diagnostics and MGR shader-hash probes inside Renut (`render/draw.cpp:1330, 4360, 4814, 4945`,
`render/surfaces.cpp:259`, all behind `MGR_RENUT_RENDERER` and a diagnostic cvar). `graphics_options.cpp:121-133` already
turned off N&B's per-surface heuristics for MGR (keep that for MP3).

### 4.4 MP3 code that collides with Renut or depends on the SDK GPU

| MP3 file:line | What | Under Renut |
|---|---|---|
| `mp3/ps4/mp3_ps4_shader_capture.cpp:139-153` | strong `sub_83053808`, `sub_83052950` (v00.34 capture) | duplicate symbols with Renut rows 21-22: remove (Renut's `CaptureMissingShader` writes the same `{vs,ps}_<hash>.bin`) |
| `mp3/src/mp3_perf_hooks.cpp:106-140` | `mp3_D3D_WaitStep` (yield/sleep) | duplicate with Renut row 13 once Renut hooks it by that name; Renut's returns 0 (nothing to wait for) |
| `mp3/src/mp3_perf_hooks.cpp:86-100` | `mp3_D3D_QueryFramesInFlight` (sleep while 2+ in flight) | keep (Renut does not hook it; Renut feeds +16976) |
| `mp3/ps4/mp3_ps4_fps.cpp:74-95, 121-126` | 60 fps via `mp3_D3D_SwapCallback` or `vblank_rate_scale` | both dead: the callback is queued by SynchronizeToPresentationInterval, which Renut replaces, and there is no SDK vblank; 60 fps has to be done in `PaceSwap` (interval at device+14000) |
| `mp3/ps4/mp3_ps4_menu.cpp:112-133, 987` | frame counter from the swap callback | switch to `renut::frame_stats` |
| `mp3/ps4/mp3_ps4_icons.cpp:104` | PS button icons through `rex::graphics::TextureCache::SetLoadHook` | the Xenos texture cache is gone: needs a hook in Renut's texture upload (`render/textures.cpp`) |
| `mp3/ps4/mp3_ps4_live.cpp:78, 144-165` | `rex_gpu_stats_text`, presenter capture for "shot" | no graphics system: use `renut::gpu::CaptureFrame` and Renut's stats |
| `mp3/ps4/mp3_ps4_app.h:60-61`, `mp3/ps4/CMakeLists.txt:129` | Xenos plugin selected and linked | ConfigureRuntime; drop `GPU_PLUGINS xenos` from the Renut build (MGR does) |
| `E:\PS4 Projects\MP3\codegen\names.toml` | 4 names: `mp3_D3D_SwapCallback` 0x83058080, `mp3_SpinLockAcquire` 0x821FD8D0, `mp3_D3D_QueryFramesInFlight` 0x83058958, `mp3_D3D_WaitStep` 0x8304A1E0 | the generated code has no `sub_8304A1E0` / `sub_83058958` (it defines `mp3_D3D_WaitStep` / `__imp__mp3_D3D_WaitStep`): Renut must hook `BANJO_RENUT_HOOK(mp3_D3D_WaitStep, CBlocker_Check_hook)` (the macro pastes `__imp__` onto any name), or the name must leave names.toml and the codegen be rerun. A hook written as `sub_8304A1E0` would leave `__imp__sub_8304A1E0` undefined |

---

## 5. The build

### 5.1 `gpu.cmake` (`app/src/renut_engine/gpu/gpu.cmake`) and MGR's wrapper

| Part | Lines | What |
|---|---|---|
| plume | 36-39 | `add_subdirectory(thirdparty/plume)`: static `plume` = `plume_vulkan.cpp` + volk + Vulkan-Headers + VMA (`plume/CMakeLists.txt:65-99`; no PS4 block there, the app adds `${PS4_KIT_DIR}/gpu` to plume's includes, `app/CMakeLists.txt:254`, and links RADV with `ps4_kit_link_mesa`) |
| zstd | 41-56 | `renut_zstd`: zstd `common/` + `decompress/` from XenosRecomp's copy, `ZSTD_DISABLE_ASM`, `ZSTD_TRACE=0` on the PS4 (weak trace hooks became module imports) |
| xxHash | 58-63 | `renut_xxhash` (`xxhash.c`); its header goes ahead of the SDK's different `xxhash.h` (314) |
| smol-v | 65-68 | `renut_smolv` (`smolv.cpp`): the cache's SPIR-V is smol-v encoded |
| DXC | 73-79 | `thirdparty/reblue-XenosRecomp/thirdparty/dxc-bin/bin/x64/dxc-linux` (+ `lib/x64`) on a Linux host |
| host shaders | 84-130, 287-304 | `renut_host_shader`: 12 HLSL shaders (overlay vs/ps, present vs/ps, depth resolve, depth resolve MS, texture mip, resolve copy, rectangle-list GS, point-sprite GS, stream convert CS, target readback CS) + FSR EASU/RCAS (not on deko3d, defines `RENUT_FSR`), DXC `-spirv -fvk-use-dx-layout` (+ `-fvk-invert-y` for VS), into `${CMAKE_BINARY_DIR}/renut_gpu/host_shaders/<stem>.spirv.h` |
| Xenos shader cache | 145-243 | normally: ExternalProject XenosRecomp, optional dump, captured shaders merged (`cmake/collect_captured_shaders.cmake`), the early-alpha pass (`BANJO_RENUT_EARLY_ALPHA`, two translator runs + `tools/renut_early_alpha.py`), `renut_gpu/shader_cache.cpp`. MGR replaces all of it: `banjo_renut_shader_cache_override` (`app/cmake/mgr_renut_gpu.cmake:18-26`) adds the prebuilt `BANJO_RENUT_SHADER_CACHE_CPP` (148-149 return early). Required on the PS4: XenosRecomp is a host tool and cannot be built with the console toolchain |
| sources and flags | 246-347 | the backend/d3d/guest/overlay/render sources (not state.cpp, photo_capture, widescreen), include dirs, ImGui headers from `app/thirdparty/imgui` everywhere but its sources compiled only off the Switch and the PS4 (a second copy would duplicate every ImGui symbol of the SDK's in one static eboot, 323-336), `RENUT_RECOMP`, links plume, renut_zstd, renut_smolv, renut_xxhash, rex::o1heap; no X11 on the PS4. Backend choice: off Windows always Vulkan unless `renut_gpu_backend = "deko3d"` (`backend/backend.cpp:62-65`) |
| `app/cmake/mgr_renut_gpu.cmake` | 101-163 | includes gpu.cmake, makes the OBJECT library `mgr_renut_gpu` (banjo_renut_select/tuning/checks/record, display_sync, frame_stats, sa2_compat, sa2_renut_pacing), includes `${REXGLUE_ENTRYPOINT_INCLUDE_DIR}` (from MGR's generated `rexglue.cmake:60`; MP3's PS4 project has no such variable), links `rex::runtime`, `renut_gpu_setup`, defines `MGR_RENUT_RENDERER=1 SA2_RENUT_RENDERER=1`, `-ffp-contract=off -fno-strict-aliasing`, links it into `sa2` |
| `app/CMakeLists.txt` | 23-37, 179-203, 242-260 | `MGR_RENUT_RENDERER` ON on the PS4 (required), the glue sources, the PS4 block (mgr_ps4*, plume include, `ps4_kit_link_mesa`, `ps4_kit_app`, `--undefined=getaddrinfo`) |

### 5.2 MGR's `build-mgr.sh`

- `host` (77-82): XenosRecomp built standalone from `app/thirdparty/reblue-XenosRecomp` with clang-21,
  `-DXENOS_RECOMP_RENUT=ON -DXENOS_RECOMP_DXIL=OFF` into `~/mgr-build/build-xenos`; the binary is
  **`~/mgr-build/build-xenos/XenosRecomp/XenosRecomp`** (814,760 bytes, 2026-11-04 22:27). DXC comes from
  `~/mgr-build/src/dxc-bin` (renderbag/dxc-bin 737ac9f), copied into the XenosRecomp thirdparty (34-37).
- `shaders` (117-143): containers from `data000.cpk` (`tools/extract_mgr_cpk_shaders.py` + `cpk_shader_scan`) into
  `~/mgr-build/shaders/containers`, plus `~/mgr-build/shaders/captures/*.bin` (the console's `shader_capture`), then
  `BANJO_DEKO3D_SPIRV_DIR=~/mgr-build/shaders/spirv XenosRecomp <containers> ~/mgr-build/shaders/renut_gpu/shader_cache.cpp
  app/thirdparty/reblue-XenosRecomp/XenosRecomp/shader_common.h ~/mgr-build/shaders/hlsl`. Arguments: input directory
  (every file scanned for containers: flags & 0xFFFFFF00 == 0x102A1100, `field1C == field20 == 0`, keyed by XXH3-64 of
  virtualSize + physicalSize, the same hash Renut computes), output cpp, shader_common.h, HLSL dump directory.
  `BANJO_DEKO3D_SPIRV_DIR` only writes extra deko3d SPIR-V (not needed for Vulkan). No early-alpha pass. Result:
  `shader_cache.cpp` 3,294,532 bytes from 1,220 containers (1,202 + 18 captured). Cache layout 7 on both sides
  (`XenosRecomp/main.cpp:494`, `gpu/shaders/shader_cache.h:81`).
- `app` (151-157): `-DMGR_RENUT_RENDERER=ON -DBANJO_RENUT_SHADER_CACHE_CPP=<cache> -DRENUT_SHADER_DUMP_DIR=... 
  -DRENUT_ASSETS_DIR=...`.

For MP3 the containers come from a capture run (MP3's archives hold none; v00.34 already writes them in Renut's format),
then the same XenosRecomp call, then a rebuild.

### 5.3 What `mgr-ps4.patch` changed in Renut and plume

| File | Change |
|---|---|
| `gpu/backend/native_window.cpp` (+17/-1) | PS4 branch: the native window is the token `plume::kPS4VideoOut`, size `ps4kit::kScreenWidth/Height` (1920x1080) |
| `gpu/backend/present.cpp` (+168/-29) | FSR 1 at the scan-out (EASU into a back-buffer-sized R8G8B8A8 target, RCAS onto the back buffer with the gamma ramp), cvars `renut_fsr`, `renut_fsr_sharpness`; bilinear otherwise |
| `gpu/backend/video.cpp` (+46), `video.h` (+7) | `BuildFsrPipelines`, the FSR shader/pipeline members |
| `gpu/gpu.cmake` (+14/-2) | `ZSTD_TRACE=0` on the PS4, FSR host shaders + `RENUT_FSR`, no second ImGui copy and no X11 on the PS4 |
| `gpu/guest/guest_memory.h` (+6) | PS4 `GuestPtr` adds `PhysicalHostOffset` (the v00.04 VdGlobalDevice fix) |
| `gpu/overlay/app_integration.cpp` (+1/-1) | Renut's own overlay not started on the PS4 |
| `gpu/shaders/host/ffx_a.h`, `ffx_fsr1.h`, `fsr_easu_ps.hlsl`, `fsr_rcas_ps.hlsl` (new) | AMD FidelityFX FSR 1 (MIT) and the two passes |
| `thirdparty/plume/plume_render_interface_types.h` (+6/-1) | PS4 `RenderWindow` = `void*`, `kPS4VideoOut` |
| `thirdparty/plume/plume_vulkan.h` (+4/-1) | includes `ps4_vk_wsi.h` |
| `thirdparty/plume/plume_vulkan.cpp` (+30/-3) | `VK_EXT_headless_surface` instead of a platform surface, `vkCreateHeadlessSurfaceEXT`, window size 1920x1080, `volkInitializeCustom(ps4kit::vk_get_instance_proc_addr())` (RADV static, no loader) |
| app side | `app/CMakeLists.txt` (+40/-2), `mgr_main.cpp` (+23/-1: 720 lines on the PS4, the quick menu), new `mgr_ps4.cpp`, `mgr_ps4_menu.{h,cpp}` |

Plume, XenosRecomp (with its zstd/xxHash/smol-v/dxc-bin), `app/thirdparty/imgui` and `cmake/collect_captured_shaders.cmake`
do not exist in the MP3 tree; they have to be brought over with Renut.

---

## 6. Ready values for MP3

### 6.1 `kGuestCodeGuards` for MP3 (FNV-32 of the first N bytes of MP3's image, same N as MGR's table)

```cpp
  {0x8304AA58u, 64u, 0x626907A6u, "Direct3D_CreateDevice"},
  {0x830614E8u, 64u, 0x93507B29u, "InitializePresentationParameters"},
  {0x83060B18u, 64u, 0x3145F52Du, "InitializeApiState"},
  {0x830611D0u, 64u, 0xB7AC8472u, "XenonGpu_Initialize"},
  {0x83061768u, 64u, 0x9DD6AD21u, "HardwareDeviceSetup_reference"},
  {0x83055798u, 64u, 0xA196FB2Eu, "KickOff"},
  {0x83055410u, 64u, 0xB53ACBDBu, "KickOffSegment"},
  {0x830559D0u, 64u, 0xB208169Au, "BeginRingBig"},
  {0x830540E0u, 64u, 0xEB244F2Eu, "RingBufferDeviceAllocate"},
  {0x83054588u, 64u, 0x80D37DC0u, "AllocateInlineData"},
  {0x83054670u, 64u, 0xB7431A74u, "NewSegment"},
  {0x83055B18u, 64u, 0x4C352DEEu, "SetRingBufferParameters"},
  {0x83054310u, 64u, 0x99DBC979u, "BlockOnFence"},
  {0x8304A1E0u, 64u, 0xB2C0CA3Cu, "CBlocker_Check"},
  {0x830558D8u, 64u, 0x0918B0ACu, "IsFencePending"},
  {0x83055AC0u, 64u, 0xEEBD7FB7u, "InsertCallback"},
  {0x830589E8u, 64u, 0xAF051AF1u, "SynchronizeToPresentationInterval"},
  {0x83058EA8u, 64u, 0x0565E067u, "Swap_shared"},
  {0x8304B000u, 64u, 0x3EF23F60u, "DrawVertices_shared"},
  {0x8304B418u, 64u, 0xD6D1D3C8u, "DrawIndexedVertices_shared"},
  {0x8304AB40u, 64u, 0x2E6B97ABu, "BeginVertices"},
  {0x8304C9D0u, 64u, 0x23C41D21u, "ClearF"},
  {0x8304F300u, 64u, 0x86B498EDu, "Resolve"},
  {0x83053808u, 64u, 0x064F3A48u, "XGRegisterVertexShader"},
  {0x83052950u, 52u, 0x3B59C114u, "XGRegisterPixelShader"},
  {0x83052EB0u, 64u, 0xCEF02F60u, "CreateVertexDeclaration"},
  {0x8305C968u, 64u, 0x799C36CEu, "D3DResource_Destroy"},
  {0x83046A00u, 64u, 0xB651019Bu, "WindowScissor"},
  {0x83058958u, 32u, 0xA7B7C7A3u, "EngineSwapProgress_reference"},
```

Six are equal to MGR's (KickOff, AllocateInlineData, ClearF, XGRegisterPixelShader, CreateVertexDeclaration,
EngineSwapProgress): their first bytes are identical. The values are over `mp3/out/codegen/image.bin`, the loaded image
the code generator dumped (disc 1 + TU6); the check in `Sa2CreateDevice` hashes the guest's loaded image at run time,
so confirm the first boot logs "all 29 guest interface guards match".

### 6.2 MGR -> MP3 callees seen at the same instruction (useful ones)

82715958 -> 821E04A8 (XMemAlloc-like), 82715A90 -> 821E05D8 (XMemFree), 82715580 -> 8306EE28, 826B5938 -> 83055A48,
826BBBE0 -> 8304C350 (ClearF's core), 826B9F78 -> 8304E1A8 (Resolve's core), 826AC848 -> 83052DC0, 826B4D38 ->
83054E00, 826CA450 / 826CA690 / 826CA7E8 -> 8305D848 / 8305DA88 / 8305DBE0, kernel thunks 831FCxxx/831FDxxx ->
830DBxxx (`__imp__VdSwap` 831FD41C -> 830DBB3C, `__imp__KeGetCurrentProcessType` 831FCE4C -> 830DB1BC...). Full
list: scratchpad `cmp_images.txt`.

Also found: MP3's D3DDevice_BeginTiling is **0x8304CEB8** (880 bytes, stores its count at +13124 at +0x1C; the
address names.toml's distance rule gives). Renut's SA2/MGR hook set does not hook it.

---

## 7. Risks

1. **Thread priorities and cores.** Every Renut thread is a plain `std::thread` at the PS4 default 700 and unpinned
   (4.2). MP3's SDK now runs the game's threads at their own priorities (640-760, strict: the PS4 does not time-slice
   equal priorities) spread over all 7 cores, and raised its service threads to 600 for exactly this reason (v00.33).
   Renut's render thread and record worker below the game's busiest threads would stall presents and fences (every
   BlockOnFence waits for the render thread). They need a priority (at least the service threads') and a core plan.
2. **Features MGR never needed that RAGE uses.** Renut's SA2/MGR hook set has no occlusion queries
   (`render/pipeline.cpp:418`: "no occlusion queries here"; MP3 issues them for lights and coronas,
   `mp3_ps4_fps.cpp:50-56`), does not hook predicated tiling (MP3's G-buffer is tiled; BeginTiling 0x8304CEB8) or
   Direct3D command buffers (the N&B handlers exist but are dead code), and delivers no graphics interrupt: anything
   MP3 drives from Direct3D's interrupt callback 0x83054048 / vblank handler 0x83057F50 other than the swap retire
   (which Renut replaces by writing device+16976) will not happen. Memexport is handled by the draw path (results a
   frame later), which MP3's GPU particles depend on.
3. **Link-time clashes and dead MP3 features:** `mp3_D3D_WaitStep`, `sub_83053808`, `sub_83052950` defined twice;
   the 60 fps mode, the frame counter, the PS icons and the live console's GPU stats/shot all hang off the SDK GPU
   (4.4).
4. **The guard check** refuses any binary but MGR's (CreateDevice returns E_FAIL, device.cpp:1336-1338) until the
   table is replaced (6.1).
5. **Memory.** Renut takes ~17 MB+ of the guest's 64 KB-page physical heap before the game allocates its own, and its
   host textures, targets and upload rings live in RADV memory inside the PS4 app budget; MP3 is a bigger game than MGR.
6. **Shader coverage.** No container is on disc: a capture run, XenosRecomp and a rebuild come first, and a shader
   missing from the cache is captured but not drawn. XenosRecomp skips containers whose field1C/field20 are not 0;
   MGR's PS4 cache was also built without the early-alpha pass.
7. **Latent link failures** in non-optimized builds: the dead REX_IMPORTs `__imp__sub_82715A90` (not an MP3 function)
   and `__imp__rex_GetCurrentThreadId` (defined by no SDK) only vanish because -O2 drops the N&B code.
