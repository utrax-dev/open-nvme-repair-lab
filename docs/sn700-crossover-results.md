# SN700 comparison: UGREEN baseline verified

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

The Creator Pro / primary UTRAX remained connected and mounted, excluded from device-targeted commands. Only the SN700/UGREEN has been ejected for the next swap.

## What remains

Stage A is complete. SN700 in the original SanDisk board, SN700 returned to UGREEN, and slow SN850XE in the original board have not yet been measured in this crossover. A fixed approximately 330 MB/s ceiling across every SSD on the retained host/UGREEN path is contradicted by the SN700 result. SN850XE-specific media, firmware, initialization, power behavior, or compatibility with the retained path remains to be separated. No throughput-limiter code path or manufacturer intent has been verified.
