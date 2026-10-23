# UTRAX Secondary Drive: diagnostic findings

Investigation date: 22 October 2026, America/New_York. This report concerns the secondary SSD. The separate primary UTRAX volume was not a diagnostic target.

## Current result

**NVMe security command access from this Mac is verified. A performance repair is not yet verified.** We built and exercised a route through the stock UGREEN bridge to the SSD's NVMe administrative queue. The SSD accepted restricted Security Receive/Send commands, TCG Properties, anonymous AdminSP and LockingSP sessions, and information GETs.

OPAL is enabled, but the SSD was **unlocked** when queried. That establishes its security configuration; it does not establish a speed restriction or explain the slowdown.

The SID differs from the factory MSID. An anonymous session could read the 32-byte MSID, but one authentication check with that value did not obtain Admin1 access. John reports that the bare module has no label, so no printed PSID is available. The standard OPAL reset route therefore lacks a valid administrator credential or physical reset credential. No alternative credential-free reset has been verified for this firmware.

## Hardware and performance

| Item | Observed result |
| --- | --- |
| SSD | WD_BLACK SN850XE 4000GB |
| SSD firmware | 624131EX |
| Replacement bridge | UGREEN, USB 174c:2463, ASMedia family |
| Bridge firmware bytes | 250717850000 |
| Filesystem | APFS, 4 TB, almost empty at initial inspection |
| Initial Blackmagic screenshot | 255.6 MB/s write, 317.2 MB/s read |
| Initial benchmark target | UTRAX Secondary Drive, verified in target selector |
| USB4 topology | Mac → Brydge ProDock TB4 → UGREEN; 40 Gb/s links reported |
| NVMe PCIe link | x4, 16.0 GT/s; TRIM supported |
| Earlier supplemental reads | 282.8 then 974.4 MB/s over 512 MiB; matching SHA-256; timings included hashing and are not a sustained maximum-speed result |
| Post-diagnostic USB4 benchmark | Queued; no completed result yet |

At the time the new benchmark was queued, host load averages were approximately 46.55 / 40.31 / 28.85 and macOS reported 29,452 MB of swap in use. This is a substantial confounder for both throughput and responsiveness; it is not proof that the SSD caused the load or that the load explains every historical symptom. The shared runner had other work ahead of this benchmark.

A 40 Gb/s link has raw bandwidth of 5,000 MB/s before overhead. It cannot deliver a 7,000 MB/s media transfer rate. Actual throughput needs measurement. USB-A was used for Linux command access; its low negotiated speed was not used to judge SSD performance.

The original SanDisk controller was connected **without the NVMe installed**. Its USB identification and bridge firmware were readable. Empty capacity in this condition does not independently prove why it failed with the SSD installed.

## Earlier health and filesystem evidence

Native macOS SMART reads returned PASSED, critical warning 0, 100% available spare, 0% endurance used, zero media/data-integrity errors, and zero NVMe error-log entries. Observed temperatures were approximately 36–39°C. A fresh read after USB-C reconnection again returned SMART PASSED, critical warning 0, 100% spare, 0% endurance used, zero media errors, zero NVMe error-log entries and 39°C. The recorded unsafe-shutdown counter was 81 at that read (77 at initial inspection); power removals/reconnections occurred during this investigation, and the count does not identify the original fault.

Volume verification with diskutil/fsck_apfs and partition-map verification passed. No full-surface test or complete hardware reliability certification was performed. The reported freezing has not been reproduced and explained.

## Direct security-query evidence

Interpreted data below came from successful NVMe completions. TCG method responses were checked separately from transport status.

| Query | Result |
| --- | --- |
| Security protocols advertised | 0x00, 0x01, 0x02; no ATA Device Server Password protocol 0xEF |
| LockingSupported / LockingEnabled | Yes / Yes |
| Locked | No |
| MediaEncryption | Yes |
| MBR shadowing enabled | No |
| OPAL V2 ComID | 0x7ffe |
| SID differs from MSID | Yes |
| SID blocked by Block SID command | No |
| Properties exchange | Successful; maximum command/response ComPacket size 2048 |
| Anonymous AdminSP session | Successful |
| LockingSP LifeCycleState | 9, manufactured active |
| Factory MSID GET | Successful, 32 bytes; credential not logged or saved |
| Anonymous LockingSP session | Successful |
| Global locking-range GET | Method succeeded but returned no named column values to the anonymous session; not evidence that the range is disabled |
| One factory-value Admin1 check | Access not obtained; no guessing loop |
| Get Features power state | PS0 after controller reinitialization; not the earlier benchmark's state |

The first session request used Write=False and returned INVALID_PARAMETER. OPAL support for that session type is optional. The standard Write=True request succeeded. Our tool restricted in-session operations to explicit GETs, EndSession and the separately enabled one-time factory-value authentication check. It did not set credentials or request a revert.

## How command access was obtained

1. Created a small Alpine ARM64 Linux machine in the existing OrbStack installation.
2. Passed only the UGREEN to that machine over USB-A, excluding UAS and usb-storage for its VID/PID.
3. Used libusb Bulk-Only Transport and the stock bridge's XDATA diagnostic interface. Ordinary ASMedia pass-through did not expose the required security commands.
4. Verified bridge/SSD identity and firmware. Privately analyzed bridge firmware to identify PCIe request registers, request tag, byte order and the NVMe BAR.
5. Temporarily configured isolated NVMe administrative queues in bridge RAM. Checked NVMe completions and TCG responses.
6. Closed successful sessions, restored and read back the original NVMe controller registers, detached the UGREEN, restored the empty USB-storage quirk setting, and stopped only the diagnostic Linux machine.
7. John reconnected the UGREEN over USB-C. macOS again reported the secondary APFS volume, NVMe Gen4 x4 and USB4 topology.

This changed volatile bridge RAM, PCIe request registers and NVMe controller/queue state. It was not a purely passive inspection. No drive firmware was flashed, no PIN was changed, and no format, sanitize or OPAL revert was requested. An unsuccessful authentication can affect the authentication retry counter. Physical reconnection rebuilt normal I/O queues after diagnostics.

Seven focused offline packet-codec checks passed, covering command restrictions, anonymous session construction, exact packet lengths/byte order, bounded factory-value authentication, method-status decoding, malformed/truncated responses and atom boundaries. These are protocol checks, not proof of a performance repair.

## Assessment of the supplied unlocker

[dex6/sed-opal-unlocker](https://github.com/dex6/sed-opal-unlocker) is a Linux frontend to the kernel OPAL interface. Its implemented operations use an existing Admin1 password to lock/unlock the global range, control MBR shadowing and save credentials for sleep support. It does not recover a password, supply a PSID, implement a performance-throttle removal operation, or provide this enclosure's missing transport path. Its setup examples enable OPAL locking; they are not an appropriate repair procedure here.

## What remains unresolved

- The reason for low sustained throughput and the reported freezes.
- Whether reverting/disabling OPAL would improve performance. No OPAL-disabled before/after comparison exists.
- A valid reset credential or a separately verified alternative procedure for this firmware.
- Manufacturer intent. OPAL being active, or a hypothetical successful software change, does not by itself establish an intentional anti-repair speed policy.

## Primary references

- [Unlocker implemented operations](https://github.com/dex6/sed-opal-unlocker/blob/master/sed-opal-unlocker.c)
- [TCG OPAL specification](https://trustedcomputinggroup.org/wp-content/uploads/TCG-Storage-Opal-SSC-v2p02-r1p0_pub24jan2022.pdf)
- [TCG Block SID specification](https://trustedcomputinggroup.org/wp-content/uploads/TCG_Storage_BlockIDAuth_v1p01_r1p14_13jan2021.pdf)
- [SanDisk PSID/MSID and OEM-label limitations](https://support-en.sandisk.com/app/answers/detailweb/a_id/34411/related/1)
- [Drive Trust Alliance PSID revert](https://github.com/Drive-Trust-Alliance/sedutil/wiki/PSID-Revert)
- [Drive Trust Alliance Remove OPAL](https://github.com/Drive-Trust-Alliance/sedutil/wiki/Remove-OPAL)
- [Drive Trust Alliance session/authentication implementation](https://github.com/Drive-Trust-Alliance/sedutil/blob/master/Common/DtaSession.cpp)
- [ASMedia USB/PCIe research](https://github.com/cyrozap/usb-to-pcie-re/blob/master/ASM2x6x/doc/Notes.md)
- [OrbStack USB passthrough](https://docs.orbstack.dev/features/usb)
