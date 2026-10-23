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
- The original empty SanDisk controller's firmware was readable. It was not tested with the NVMe reinstalled during this phase, so its exact original failure remains unproven.

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
