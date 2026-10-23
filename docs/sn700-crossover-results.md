# SN700 crossover: fast before and after original-board exposure

The WD Red SN700 500GB reached **2,337.6 MB/s first-read throughput** and **1,018.2 MB/s write throughput including full flush** in the same UGREEN / USB-C / Brydge path used for the slow SN850XE. This is direct evidence that the retained path can exceed the SN850XE's approximately 330 MB/s read ceiling with a different SSD.

| Measurement | SN700 in UGREEN |
| --- | --- |
| Identity | WD Red SN700 500GB; firmware 111150WD; 500,107,862,016 bytes |
| NVMe / host links | PCIe Gen3 x4 at 8 GT/s; UGREEN USB4 reports 40 Gb/s |
| 4 GiB write with full flush | 1,018.2 MB/s |
| First sequential 4 GiB read | 2,337.6 MB/s |
| Physical reads during first read | Exactly 4,294,967,296 bytes / 8,192 operations |
| Added physical read errors / retries | 0 / 0 |
| Full-file SHA-256 | Matched across the complete 4 GiB test file |
| Health after test | 39 C, critical warning 0, media errors 0; cumulative error log count remained 1 |

A repeat parallel file read appeared to reach 11,977.4 MB/s, but only 1,128,251,392 of its 4,294,967,296 file bytes appeared in the physical read counter. That result is cache-assisted and is excluded from drive-throughput claims.

Before the SN700's first connection to the original SanDisk board, information-only queries captured TCG locking as supported, disabled and unlocked. Power Management current, default and saved queries returned DWORD0=0; the supported-capabilities query returned DWORD0=4. APST current, default and saved returned DWORD0=0. Every query completed with status zero. These power values were read after diagnostic NVMe controller reinitialization, so they do not establish the earlier USB-C operating state. The original controller register configuration was restored and verified. No Security Send, authentication, vendor opcode, Set Features or erase command was included in that capture.

The original NAS partition metadata, Identify and health evidence were retained privately. The owner reported a completed NAS backup and block verification, then explicitly approved replacing only the SN700's NAS partitions with the APFS comparison volume. Raw reads were blocked by macOS even under the attempted administrator context; this is the reason for the file-test format, not a claim that raw reads are impossible on macOS generally.

The Creator Pro / primary UTRAX remained connected and mounted, excluded from device-targeted commands throughout the crossover.

## Stage B: original SanDisk board does not expose usable capacity

With the same owner-confirmed SN700 installed, the original 0781:55af board negotiated a **10 Gb/s USB-C connection** but exposed no physical disk or mounted comparison volume. Its first bridge firmware-version read timed out before completion. Returning from diagnostic USB passthrough to normal macOS handling still produced no disk.

A USB-A connection negotiated 480 Mb/s and also exposed no disk. Its first standard Request Sense read timed out. After preserving both failures, a single USB Bulk-Only Transport recovery completed successfully and both endpoint-halt clears succeeded. The following commands then completed:

| Command after the one transport recovery | Result |
| --- | --- |
| Test Unit Ready | SCSI/BOT success |
| Request Sense | Success; sense key 0, ASC 0, ASCQ 0 |
| Inquiry | Success; SanDisk Extreme Pro 55AF, revision 4060 |
| Read Capacity(10) | Timed out before data/status completion; no retry or second recovery |

The diagnostic commands sent no SSD erase, security change, firmware write or NVMe reset. The transport recovery was a USB class request; the bridge's own automatic initialization behavior remains untraced. The underlying SN700 identity could not be read through this board, so its installation is owner-confirmed rather than independently identified through the failed path. No throughput measurement through the original board was possible.

This demonstrates successful USB enumeration and, after recovery, basic command handling, followed by failure to return usable storage capacity for this SSD in the tested setup. It does not identify a specific failed chip or separate a board fault from SN700 compatibility. Stage D below subsequently confirmed that this board can expose its factory SN850XE; the SN700 result must therefore retain the compatibility/initialization qualification.

The USB recovery shape follows the [Linux USB-storage implementation](https://kernel.googlesource.com/pub/scm/linux/kernel/git/printk/linux/+/afdf0fb340948a8c0f581ed1dc42828af89b80b6/drivers/usb/storage/transport.c). Hardware outcomes above come from the retained local transcripts.

## Stage C: SN700 returns at more than 2 GB/s with matching state and data

After returning the SN700 to the UGREEN, fresh controller and namespace Identify bytes matched the stage-A captures exactly. Security protocol/discovery bytes, captured locking flags, Power Management current/default/saved/capability completions and all three APST tables were identical. Locking remained disabled and unlocked. As in A, these power queries followed diagnostic controller reinitialization; transient runtime state and unqueried vendor settings remain outside this comparison.

The same retained 4 GiB file read at **2,032.0 MB/s** on its first USB-C read, with exactly 4,294,967,296 physical read bytes across 8,192 operations, no added errors/retries and a full SHA-256 match. Post-test health reported 34 C, critical warning 0, media errors 0 and cumulative error-log count 1, unchanged. The repeat parallel read was cache-assisted and excluded.

Both A and C exceed 2 GB/s. Host load was higher in C, and temperature/load were not controlled tightly enough to attribute the approximately 13% difference to the original-board exposure. The crossover provides no evidence that the original board transferred a persistent, generic 330 MB/s ceiling to this spare SSD.

## Stage D: original SN850XE is exposed, but initial reads fail

With its original slow SN850XE installed, the original SanDisk board negotiated the same 10 Gb/s USB-C path and exposed a 4 TB physical disk. macOS Identify independently matched the approved slow SSD's exact serial, model and firmware. Public evidence omits the individual serial. This differs materially from the SN700 result and prevents attributing that result to a generally dead original board.

The board reports **4,000,753,467,904 bytes**, which is **33,562,112 bytes less** than the full 4,000,787,030,016-byte NVMe namespace exposed through UGREEN. No partition map or APFS volume appeared. The capacity difference is verified, but failed reads at offset zero prevent checking the actual GPT. It cannot currently explain the missing volume by itself. No format, partition repair or SSD configuration change was performed.

A macOS full SMART request returned exit bit 4 because the NVMe health-log request failed; Identify succeeded. Stock Linux passthrough could not use UAS because the guest's virtual USB controller lacks streams. Its USB-storage fallback did not expose a block disk and performed transport retries/resets during probing. This is a guest-path limitation; it is not a valid original-board throughput measurement or proof of SSD failure. The guest was stopped and only the original board was returned to macOS. The owner power-cycled the board and its physical disk reappeared. Both macOS block and raw-device opens returned EPERM even in the administrator context. The owner reports ChatGPT Full Disk Access was already enabled. The owner ran the same guarded reader from an interactive Terminal. Both 4 KiB offset-zero reads failed with errno 5, Input/output error, rather than the helper's errno 1 permission denial. No header bytes were returned or captured. The exact original-board IOBlockStorageDriver snapshot then reported 24 read operations, 24 read errors and zero bytes read; those totals include system probing and are not all attributed to the two explicit reads. The original-board secondary was safely ejected afterward.

## Stage E: SN850XE restored to USB4 and its data verified

After returning the slow SN850XE to UGREEN on the normal USB4 connection, fresh exact SSD identity, firmware, capacity, APFS volume UUID and physical-store binding were verified. Its retained 4 GiB file read at **331.4 MB/s** in 12.9602 seconds, with exactly 4,294,967,296 physical read bytes across 8,192 operations, no writes, no added errors/retries and a complete SHA-256 match. The secondary APFS volume is mounted and usable. The diagnostic Linux guest is stopped.

A subsequent first-pass read curve measured 329.0 MB/s, with the ceiling present from the first 64 MiB window, SSD temperature samples at 40 C, no growing media-error count and zero reported thermal-management transition counts/times before and afterward. This weakens ordinary reported thermal throttling as the explanation for this bounded workload. It does not resolve SSD/bridge compatibility or an unreported profile. The [current USB4 findings](current-usb4-diagnostics.md) record latency, cache exclusions and why a same-queue vendor-profile comparison is still not feasible through the validated interface.

## What remains

Stages A through E are complete within the reported access limits. Stage D verified original-board capacity and exact SSD identity, then recorded failed offset-zero reads. No original-board throughput measurement was possible. This establishes a failing read path in the tested setup; it does not identify a failed chip, distinguish hardware from initialization/compatibility, or prove how the post-reset SSD state affects this board. A fixed approximately 330 MB/s ceiling across every SSD on the retained host/UGREEN path is contradicted by the SN700 results. SN850XE-specific media, firmware, initialization, power behavior, or compatibility with the retained path remains to be separated. No throughput-limiter code path or manufacturer intent has been verified.
