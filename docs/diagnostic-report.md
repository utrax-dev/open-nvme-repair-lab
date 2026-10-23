# SN850XE recovery: reset verified, speed problem unresolved

The firmware-derived credential recovered from the original SanDisk bridge authenticated successfully to the owner's WD_BLACK SN850XE 4000GB, firmware 624131EX, as both LockingSP/Admin1 and AdminSP/SID. A standard SID-authenticated factory reset then completed without a PSID. **That reset did not restore normal throughput in the tested setup.**

## Before and after

| Measurement | Result | Limit |
| --- | --- | --- |
| Initial Blackmagic screenshot | 255.6 MB/s write; 317.2 MB/s read | Owner screenshot; secondary target checked |
| Pre-reset 4 GiB file check | 207.5 MB/s write including full flush; 127.7 / 934.5 MB/s reads | Heavy host load; possible concurrent Blackmagic I/O; not a clean control |
| Post-reset 4 GiB file check | 268.3 MB/s write including full flush; 334.2 / 975.9 MB/s reads | File I/O; repeated read can include cache effects |
| Post-reset first read, 8 parallel workers | 330.4 MB/s | Physical-device counters increased by 4,297,048,064 bytes across 8,199 reads |
| Parallel-test write including full flush | 268.6 MB/s | Same bounded 4 GiB file method |
| File integrity | Both post-reset full 4 GiB SHA-256 comparisons matched | Limited test-file integrity; not a full-surface test |

No added physical read errors or retries were reported during the parallel read. The faster repeated-read number is not evidence of sustained NVMe media throughput. Parallelism did not lift the measured ceiling.

## Device and connection

- SSD: WD_BLACK SN850XE 4000GB, firmware 624131EX; 4,000,787,030,016 bytes.
- Replacement enclosure: UGREEN 174c:2463; stock bridge firmware bytes 250717850000.
- Connection used for speed tests: Mac → Brydge ProDock TB4 → UGREEN. macOS reports USB4 40 Gb/s and the SSD's PCIe link as Gen4 x4, 16 GT/s. PCIe link-status properties also report Gen4 x4 at the SSD and adjacent bridge.
- The same connection path was retained. A direct-to-Mac or other-host comparison was not performed.
- USB-A was used only for Linux administrative command access, not for these performance results.
- The original empty SanDisk controller's firmware was readable. The later crossover below tested it with SN700 and its original SN850XE; its exact original failure remains unproven.

A 40 Gb/s link has a raw ceiling of 5,000 MB/s before overhead and cannot carry 7,000 MB/s. The 40 Gb/s negotiation itself does not prove available end-to-end bandwidth.

## Credential recovery evidence

The extracted 8051 code image has SHA-256 0468b822080cc3b26de98b935175495120c1ad5046e505d4325e73a412ddac20. Offsets below refer to that code image, not the raw flash container.

1. The XDATA initialization record at 0x091E initializes five bytes at 0x0CA4.
2. The LockingSP/Admin1 path around 0x7FA1 and AdminSP/SID path around 0x7FB4 select that source.
3. The constructor around 0x88F3/0x8914 copies five bytes into a zero-filled 32-byte challenge.
4. An exact challenge constructed locally was accepted by both authenticated StartSession operations, with TCG method status zero. Privileged table reads independently corroborated Admin1 access.
5. A conditional initialization path at 0x33C8 through 0xF6B6 references SID setup and checks a FIX1 marker. Its execution with the original assembled drive was not traced; this path is not evidence of a speed-limiting instruction.

No credential bytes, vendor firmware, decompiled vendor source or individual device serials are included in this repository.

## Authenticated state and reset

Before reset, LockingSP lifecycle was 9 (manufactured-active). The global range was unlocked, with read/write locking disabled. An additional range of 65,535 512-byte sectors, approximately 32 MiB near the device end, was configured but also unlocked. Ranges 2–8 were unconfigured.

The owner explicitly approved erasing the entire secondary SSD and recreating APFS. The tool required exact enclosure and SSD identities, fresh Identify, one accepted SID session and a separate erase authorization. It sent **AdminSP.Revert once**. The method returned status zero and subsequent Discovery0 reported LockingEnabled=false and Locked=false.

A separate information query after restoring the original controller registers confirmed lifecycle 8 (manufactured-inactive), locking disabled and SID equal to MSID. The standard factory state was therefore corroborated separately from the reset response.

A local completion-record writer raised TypeError after the accepted reset and state readback. We recovered the record from the retained transcript, corrected the writer and added a regression test. The reset was not repeated. All 18 private lab checks then passed; the portable repository test run omits the unbundled private firmware fixture.

RevertSP with KeepGlobalRangeKey=true was not selected: it preserves only the global key, while this SSD had another configured range. AdminSP.Revert was treated as a full data erase. APFS/GUID was subsequently recreated as UTRAX Secondary Drive using fresh physical identity, capacity and external whole-device guards. The separate primary UTRAX drive was never a reset or format target.

## Health and reliability limits

Post-reset SMART passed: critical warning 0, 36°C, 100% available spare, 0% endurance used and zero media/data-integrity errors. The cumulative NVMe error-log counter changed from 0 to 1 during the diagnostic/reset phase; no detailed entry was present in the subsequent 16-entry error-log read, so its command/cause was not identified. This is retained rather than reported as a zero-error history.

The power-cycle count was already 41,422 before the reset phase and became 41,425 afterward. The unsafe-shutdown count changed from 81 to 84 as physical reconnects occurred. Those counters do not identify the original fault.

The new APFS volume and container passed diskutil verification with exit code 0. A 32 MiB read after a 60-second wait completed in 0.103 seconds, involved 33,558,528 physical read bytes, and matched its full hash with no new read errors/retries. Fifteen background physical reads and 38 writes occurred during the wait, so this was not a proven fully idle-device wake test. The reported intermittent freezing has not been reproduced and explained. These checks do not certify the SSD's entire surface or long-term reliability.

## What the evidence supports

- A credential from this original bridge firmware grants actual Admin1 and SID access to this SSD.
- A PSID is not required for the validated SID-authenticated factory reset.
- The simple claim that removing the observed OPAL configuration would restore speed is not supported by the result: the security state was reset, but throughput remained around 270 MB/s write and 330 MB/s first read.
- A remaining device, enclosure, host or connection-path bottleneck has not been isolated. There is no demonstrated full-speed repair and no proven manufacturer intent to impose an anti-shucking cap.

## Primary protocol references

- [Drive Trust Alliance reset implementation](https://github.com/Drive-Trust-Alliance/sedutil/blob/master/Common/DtaDevOpal.cpp)
- [Drive Trust Alliance command semantics](https://github.com/Drive-Trust-Alliance/sedutil/blob/master/Common/DtaOptions.cpp)
- [TCG Opal specification](https://trustedcomputinggroup.org/wp-content/uploads/TCG-Storage-Opal-SSC-v2p02-r1p0_pub24jan2022.pdf)
- [ASMedia bridge research](https://github.com/cyrozap/usb-to-pcie-re)
- [OrbStack USB passthrough](https://docs.orbstack.dev/features/usb)

## Vendor initialization investigation

A read-only query of the empty original bridge verified firmware 19062091e48a and found its vendor-init flag enabled. The runtime table selects two values according to USB link state. The highest populated selector uses parameter pairs 1→0x29 and 2→0x1C. Assembly reconstructs 0xFD with the parameter in CDW10 and value in CDW11, followed by 0xFE with that parameter. The units, purpose and persistence remain unknown.

A bounded experiment sent only the original 0xFE frames for parameters 1 and 2, once each. Both returned successful completion with DWORD0=0; this did not expose the current settings. Before/after health stayed approximately 39°C with zero critical warnings and media errors; the cumulative error-log count stayed at 1. Original controller registers were restored and verified. No 0xFD was sent in that probe. See the separate vendor initialization findings for the table and exact evidence limits.

The exact original profile-4 sequence was subsequently accepted, and the 0xFE followups read back the 0xFD values 41 and 28. The next USB-C test still measured 266.0 MB/s write and 331.9 MB/s first read, with exactly 4 GiB of physical reads, no added read errors/retries and a full hash match. A later 0xFE query returned 0/0 after the controller-reset/reconnect sequence. This confirms a configurable, nonpersistent-across-that-sequence mechanism, but not the specific clearing transition or a performance unlock.

A controlled follow-up established that the 41/28 values survived NVMe CC.EN reset and diagnostic queue reconstruction within one USB attachment. The later 0/0 state is associated with the broader reconnect/initialization route; the exact clearing action is not isolated. The USB-C speed result therefore cannot establish performance while those values remain active. Live hardware sequence/readbacks are retained separately from the 26 offline safeguards (portable checkout: 25 pass, one private-fixture test skipped).


## SN700 crossover control: host/UGREEN path exceeds 2 GB/s

A separate WD Red SN700 500GB, firmware 111150WD, measured **1,018.2 MB/s write with full flush and 2,337.6 MB/s first sequential read** in the retained UGREEN / USB-C / dock path. The first read produced exactly 4,294,967,296 physical read bytes across 8,192 operations, with no added errors/retries, and the complete 4 GiB SHA-256 matched. The repeat parallel result was cache-assisted and excluded from drive-throughput conclusions.

The SN700 security/power baseline was captured before first exposure to the original SanDisk board: TCG locking supported but disabled/unlocked, Power Management DWORD0=0, APST disabled. Those feature reads followed diagnostic controller reinitialization and do not establish the earlier USB-C runtime state. Original NAS partition metadata was retained privately before the owner explicitly approved an APFS comparison format. Creator Pro / primary UTRAX remained connected and excluded.

This control contradicts a fixed approximately 330 MB/s ceiling for every SSD on the retained host/UGREEN path. It narrows investigation to SN850XE-specific behavior or interaction with that path; it does not isolate media, firmware, initialization, power behavior or compatibility. SN700 did not expose usable capacity in the original board, then returned to UGREEN at 2,032.0 MB/s with identical captured security/power state and a full retained-file hash match. The original board does expose its factory SN850XE, but at 33,562,112 bytes less than the full namespace and without a mounted partition map. Both guarded offset-zero reads through the original board failed with EIO, and its physical counters reported 24 errors / 24 read operations with zero bytes. No throughput or raw GPT capture was possible. This proves a failing read path in the tested setup, without isolating a hardware component from initialization/compatibility or the effect of the SSD's post-reset state. See the [SN700 crossover results](sn700-crossover-results.md).

## Current USB4 investigation and enclosure firmware lead

The slow SN850XE has returned to UGREEN and its APFS volume is mounted. The retained 4 GiB file read at 331.4 MB/s with exactly 4 GiB physical reads and a full hash match. A subsequent read curve, without controller/transport resets or setting writes, reproduced 329.0 MB/s on its first pass. First-pass temperature samples were 40 C; raw SMART before/after showed zero thermal transition counts/times, zero media errors and an unchanged cumulative error-log count of one. Cache-assisted later passes were excluded. Intermittent freezes were not reproduced. See [current USB4 state and interface feasibility](current-usb4-diagnostics.md) for the latency and physical-counter evidence.

Current power/APST settings and vendor parameters could not be read through the documented native interface. Static inspection did not find a validated general administrative passthrough suitable for a profile write/readback/data-read/readback experiment on the same queues. No known profile or standard power feature was changed during this phase, and no long self-test was started.

The enclosure firmware lead was checked against UGREEN's official Download Center. SKU 55316 is D700; its record currently lists conformity documents only. A firmware package under 15976 / CM642 was downloaded and inspected without running its software. Its image contains version 240417850000, older than the enclosure's previously measured 250717850000. D700 applicability and a WD-specific compatibility fix were not established. No firmware was flashed. See the [firmware findings](ugreen-firmware-findings.md) and [unsent support request](ugreen-support-request.md).

The owner subsequently supplied the exact Amazon listing for SKU 55316, whose branded description explicitly excludes WD SN850X. That restriction is independently verified and was missed by the earlier regional-page search. It makes enclosure/SSD compatibility a more concrete investigative lead, while the exact reason and applicability to SN850XE remain unverified. The owner's reported flat/free physical fit and latest thermal evidence weaken simple pressure/overheating explanations. Independent SN850XE/624131EX owner reports also describe similar slowdown outside D700, including native laptop NVMe slots. See the [compatibility investigation](sn850x-compatibility-investigation.md) for source-specific limits and the still-unanswered engineering question.
