# Current USB4 state and profile-test feasibility

The slow SN850XE is back in UGREEN on the normal USB4 connection, with UTRAX Secondary Drive mounted. Creator Pro / primary UTRAX remains connected and excluded. The diagnostic Linux guest is stopped. No controller/transport reset, vendor write, Set Features or self-test was sent during this USB4 state capture and read-curve investigation. The long self-test was declined and was not started.

## Completed return and read tests

| Observation | Result |
| --- | --- |
| First 4 GiB retained-file read after crossover | 331.4 MB/s, 12.9602 seconds |
| Physical counters for that read | Exactly 4,294,967,296 bytes / 8,192 reads; zero writes, added errors or retries |
| Full 4 GiB SHA-256 after return | Matched |
| Subsequent curve, first pass | 329.0 MB/s of read time; 310.9 MB/s including health-sampling time |
| Curve first-pass physical counters | 4,294,971,392 bytes / 8,193 reads; zero writes, added errors or retries |
| First-pass 4 MiB read latency | p50 12.434 ms; p95 13.655 ms; p99 18.012 ms; maximum 42.937 ms |
| First-pass read calls above 100 ms | Zero |
| Sampled first-pass SSD temperature | 40 C throughout reported samples |
| First / final quarter median 64 MiB-window throughput | 334.0 / 333.8 MB/s |
| Complete file hash after curve | Matched |

The first 64 MiB window measured 329.4 MB/s. Individual windows ranged from 266.9 to 338.2 MB/s; there was no sustained temperature-linked collapse across the pass. This is a bounded, host-loaded file test, not a certification of the full surface or all workloads. The reported intermittent freezing was not reproduced in these reads.

Three subsequent passes appeared to read at 875–976 MB/s, but their physical read-byte counts covered only about 1.13–1.32 GB of each 4 GiB pass. Those passes are cache-assisted and excluded from media-throughput conclusions. Requested file I/O totaled 16 GiB, not 16 GiB of verified physical reads.

A separate 30-second wait produced no host block reads or writes in the physical counters. The following 4 MiB file-read call took 15.117 ms. Its own physical counter delta was not separately captured, so this does not independently measure a media wake or prove the SSD entered a particular internal power state.

## Fresh native state without reset

An exact-target helper used Apple's documented NVMe SMART interface to read Identify Controller/Namespace, SMART, error and command-effects logs. It verified the secondary's SSD serial privately before reading; no undocumented function slot was called. Individual serials and disk contents are omitted from public evidence.

| Field | Result / interpretation |
| --- | --- |
| SSD identity / firmware | WD_BLACK SN850XE 4000GB / 624131EX |
| SSD link | Gen4 x4, 16 GT/s, reported by native driver |
| APST / host-controlled thermal management | Advertised as supported; current settings not obtained |
| Composite warning / critical temperature thresholds | 364 K / 367 K, approximately 91 / 94 C |
| HCTM supported threshold range | 273–358 K; supported limits, not current TMT1/TMT2 settings |
| Additional temperature sensors | Eight zero fields, meaning not reported here |
| Raw SMART before / after captures | 311 K / 313 K, approximately 38 / 40 C |
| T1/T2 thermal transition counts and total times | All zero in both captures |
| Warning / critical temperature time | Both zero in both captures |
| Media errors | Zero in both captures |
| Cumulative error-log count | One in both captures, unchanged |

These fields provide no reported thermal-throttling or growing-error explanation for this bounded test. They do not exclude unreported SSD/bridge thermal limits, an unusual firmware operating mode or intermittent faults. macOS IORegistry CurrentPowerState=2 is a driver power state and must not be presented as NVMe power-state index 2.

## Exact missing software interface

The decisive comparison requires **Get/Set Features and the exact original vendor FD/FE commands while normal USB4 data reads continue through the same controller queues**, followed by readback both before and after the benchmark. No validated interface providing that combination has been found in the installed software path.

- The documented native NVMe SMART API and smartmontools' Darwin backend expose Identify and log reads, rather than general NVMe administrative passthrough. Get Features, Set Features and FD/FE could not be captured through that documented interface. Unsupported access is an interface limit, not evidence that the SSD command failed.
- Read-only inspection of the installed driver's generic controller user-client dispatcher found its single accepted selector dispatching to Sanitize. It was not called or probed as a possible passthrough.
- The separate SMART user's ProductionTunnel path checks `com.apple.nvmetunnel.allow` and an Apple-specific controller type. It has not been validated for this third-party SSD and was not invoked. Administrator/FDA access does not itself supply this interface.
- The existing Linux/USB diagnostic route reinitializes the NVMe controller and constructs temporary administrative queues. It therefore cannot satisfy the owner's same-queue comparison requirement. A faster cable alone would not remove that limitation.

The known parameters 1=41 and 2=28 were **not** replayed during this USB4 investigation. Prior tests showed successful write/readback and survival of a controlled controller reset, but did not pair a meaningful data benchmark with independently confirmed active values before and after it. Their performance effect remains unresolved. Standard power/APST setting changes were likewise not attempted through an unvalidated interface, and thermal protection was left active.

Private Apple driver binaries/disassembly, vendor firmware and credentials are not distributed. These are findings about the inspected software, not a claim that no possible macOS implementation can ever provide passthrough. The current [enclosure firmware check](ugreen-firmware-findings.md) identifies the separate missing model-approved update evidence.
