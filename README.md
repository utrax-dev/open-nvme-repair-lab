# Open NVMe Repair Lab

Evidence and diagnostic research for a WD_BLACK SN850XE 4 TB removed from a SanDisk portable SSD and installed in a UGREEN enclosure on a Mac.

**Current outcome: NVMe/OPAL diagnostic access verified; performance repair unresolved.** This repository is not an unlock utility or a claim that an intentional speed limit has been proved.

## What was observed

| Observation | Evidence level |
| --- | --- |
| Initial Blackmagic result: 255.6 MB/s write, 317.2 MB/s read | User screenshot; target verified in the app |
| SSD: SN850XE 4000GB, firmware 624131EX | Identify Controller |
| Replacement bridge: 174c:2463, firmware bytes 250717850000 | USB identification and bridge reads |
| USB4 40 Gb/s topology and NVMe Gen4 x4 | macOS system profiler |
| SMART and APFS verification passed at inspection | Health and filesystem diagnostics; not a complete reliability test |
| OPAL enabled, media currently unlocked | Successful NVMe Security Receive / TCG Discovery0 |
| SID differs from factory MSID | TCG Block SID feature descriptor |
| Anonymous security sessions and factory MSID read work | Successful TCG method responses |
| One factory-value check did not obtain Admin1 access | TCG Authenticate response interpreted separately from transport status |
| Module has no label / visible PSID | Owner physical inspection |
| Removing OPAL restores full speed | **Not demonstrated** |
| Manufacturer deliberately imposed an anti-shucking speed cap | **Not established** |

The USB4 link's raw 40 Gb/s bandwidth is 5,000 MB/s before overhead. It cannot carry 7,000 MB/s. An achievable sustained maximum still needs measurement.

## Process used

1. Identify the exact secondary volume, SSD and bridge. Keep unrelated drives outside the diagnostic target.
2. Save health, filesystem, topology and performance evidence before changing anything.
3. On this Mac, run a small Alpine ARM64 guest in OrbStack and expose the UGREEN over USB-A. USB-A here is a command-access route, not a speed benchmark.
4. Exclude both UAS and usb-storage for the bridge VID/PID, then claim its Bulk-Only Transport interface with libusb.
5. Analyze the stock bridge diagnostic protocol. Ordinary ASMedia pass-through did not offer the required NVMe security commands on the tested firmware.
6. Through verified XDATA/PCIe request registers, temporarily configure isolated NVMe administrative queues in bridge RAM. Query Discovery0, TCG Properties and allowlisted information tables. Validate NVMe completion identity/status and TCG method status separately.
7. Restore and read back original controller registers, close sessions, detach the enclosure, restore driver quirks and stop only the diagnostic VM.
8. Reconnect over USB-C for normal I/O and a new performance comparison.

**The live bridge prototype remains private pending a safety review.** It changes volatile bridge/controller state and needs a physical reconnect afterward. A raw vendor-command script built for another firmware can corrupt controller state; this is not a generic copy-and-run recipe. This public-preparation folder contains only sanitized findings at present. It does not contain vendor firmware, decompiled code, device serial numbers, credentials or an erasing reset command.

## Why the linked unlocker does not solve this case

[`dex6/sed-opal-unlocker`](https://github.com/dex6/sed-opal-unlocker) is a useful Linux OPAL frontend. Its lock/unlock operations need an existing Admin1 password. It does not recover the password, provide a missing PSID, or remove a documented performance throttle. This drive was already unlocked during the verified query.

Its setup examples enable OPAL locking; applying those examples would not be a repair procedure for this case.

## Current reset barrier

The factory MSID was readable but did not obtain Admin1 access in a single check. The SID also differs from MSID. No printed PSID is available on the bare module. The standard reset route therefore lacks its required credential. A new operating system or an additional kernel permission does not supply that credential.

This does not rule out every future manufacturer or firmware-specific procedure. It describes the tested standard route and its concrete missing requirement. A supported alternative must be verified for firmware 624131EX before it is described as a solution.

## Evidence and publication status

- [Sanitized security-query transcript](evidence/security-session-query.txt)
- [Case report](docs/diagnostic-report.md)
- [LinkedIn draft](docs/linkedin-draft.md)

This is a local preparation repository. Publication and a working repair release remain pending. If later work restores performance, add the exact intervention, firmware, connection, reproducible benchmark and integrity result before changing that status.

## Sources and credit

- [Drive Trust Alliance sedutil](https://github.com/Drive-Trust-Alliance/sedutil): OPAL protocol and standard reset workflows.
- [TCG OPAL specification](https://trustedcomputinggroup.org/wp-content/uploads/TCG-Storage-Opal-SSC-v2p02-r1p0_pub24jan2022.pdf): session and security-provider behavior.
- [TCG Block SID specification](https://trustedcomputinggroup.org/wp-content/uploads/TCG_Storage_BlockIDAuth_v1p01_r1p14_13jan2021.pdf): SID/MSID state definition.
- [ASMedia USB-to-PCIe research](https://github.com/cyrozap/usb-to-pcie-re): documented bridge protocol research.
- [OrbStack USB documentation](https://docs.orbstack.dev/features/usb): Mac-hosted Linux USB passthrough.
- [SanDisk PSID/MSID guidance](https://support-en.sandisk.com/app/answers/detailweb/a_id/34411/related/1): printed PSID and OEM limitations.

## Right to repair

Owners should have documented ways to diagnose, reset and reuse storage hardware after an enclosure fails. Missing recovery information and restricted diagnostic transports increase repair costs and can turn reusable components into e-waste. Those are concrete reasons to demand better repair access; an allegation of deliberate performance throttling needs its own causal evidence.
