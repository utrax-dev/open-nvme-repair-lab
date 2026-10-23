# Open NVMe Repair Lab

A Mac-based investigation of a WD_BLACK SN850XE 4 TB removed from a SanDisk Extreme Pro portable SSD.

**Validated: recover the credential from the original bridge firmware, authenticate as Admin1/SID, and perform the standard factory reset without a PSID.**

**Not fixed: the tested SSD still transfers at approximately 270 MB/s write and 330 MB/s first read in its UGREEN/dock setup after that reset. This repository is not a full-speed unlock claim.**

## What this project provides

- An offline extractor for the exact reviewed original bridge code image. It writes the reconstructed 32-byte challenge to a new private file and never prints it.
- A restricted TCG packet codec and experimental Linux/libusb transport for the tested UGREEN firmware. It can query OPAL state, authenticate with the extracted challenge, and issue one separately authorized factory reset.
- Target, firmware, approval and completion guards for the reset and subsequent macOS APFS recreation.
- Bounded file benchmarks with full-file integrity checks. The parallel test also records physical-device I/O counters to expose cache effects.
- Sanitized authentication, reset and benchmark evidence, including the local result-writer error discovered after the reset and its tested correction.

No vendor firmware, vendor decompiled code, credential bytes or individual device serials are distributed.

## Tested hardware

| Component | Exact tested value |
| --- | --- |
| SSD | WD_BLACK SN850XE 4000GB |
| SSD firmware | 624131EX |
| Capacity | 4,000,787,030,016 bytes |
| UGREEN USB VID:PID | 174c:2463 |
| Owner-identified UGREEN SKU / model | 55316 / D700 |
| UGREEN bridge firmware bytes | 250717850000 |
| Original code image size | 65,368 bytes |
| Original code SHA-256 | 0468b822080cc3b26de98b935175495120c1ad5046e505d4325e73a412ddac20 |
| Host / diagnostic guest | Apple Silicon Mac / Alpine ARM64 in OrbStack |

The hardware-command prototype deliberately rejects other identities/firmware and is intended for advanced, supervised repair research. It changes volatile bridge RAM and NVMe administrative queues. It requires unbound Linux storage drivers and a physical reconnect after a completed diagnostic session. **The separately enabled factory-reset mode destroys all target SSD data.**

## Results

| Observation | Verified result |
| --- | --- |
| Initial Blackmagic | 255.6 MB/s write; 317.2 MB/s read |
| Firmware-derived Admin1 authentication | Accepted; privileged range tables readable |
| Firmware-derived SID authentication | Accepted in AdminSP |
| Factory reset without PSID | Accepted once; TCG method status 0 |
| Independent post-reset state | LockingSP lifecycle 8, locking disabled, SID equal to MSID |
| New APFS volume/container verification | Passed, exit code 0 |
| Post-reset sequential file test | 268.3 MB/s write with full flush; 334.2 MB/s first read |
| Post-reset 8-worker first read | 330.4 MB/s; physical counters confirmed about 4.30 GB read |
| Integrity | Both complete post-reset 4 GiB hashes matched |
| Added read errors/retries in parallel test | 0 / 0 |
| Original vendor profile replay | Accepted; values 41/28 read back and survive controlled NVMe reset; later 0/0 after broader reconnect path |
| USB-C test after profile replay | 266.0 MB/s write; 331.9 MB/s first read; full hash matched |
| SN700 500GB control in the same UGREEN path | 1,018.2 MB/s write; 2,337.6 MB/s first read; exactly 4 GiB physical reads and full hash match |
| SN700 after original-board exposure, back in UGREEN | 2,032.0 MB/s first read; exactly 4 GiB physical reads, full hash match, captured security/power fields unchanged |
| Original SanDisk board with factory SN850XE | Exact SSD identified and capacity exposed; offset-zero reads fail with EIO, physical snapshot has zero read bytes / 24 read errors; throughput unmeasurable |
| SN850XE returned to UGREEN USB4 | 331.4 MB/s; exactly 4 GiB physical reads; full hash matched |
| Current USB4 bounded read curve without reset | 329.0 MB/s first pass; no added errors/retries or reported thermal-throttling counts; full hash matched |
| UGREEN firmware update lead | 55316 listing has conformity documents only; located CM642 package is 240417850000, older than installed 250717850000; D700 applicability unverified |
| Exact D700 Amazon listing | Explicitly excludes WD SN850X; cause and SN850XE applicability unspecified; the fast SN700 control does not validate this pairing |
| Full-speed repair / intentional anti-shucking cap | Not established |

The repeated file read reached 975.9 MB/s, but it may include cache effects and is not a demonstrated media-transfer maximum. A 40 Gb/s USB4 link itself has a raw ceiling of 5,000 MB/s before overhead; 7,000 MB/s cannot traverse that link.

## Use and evidence

- [Reproduction procedure](docs/reproduction.md)
- [Detailed case report and limitations](docs/diagnostic-report.md)
- [SN700 crossover: same path exceeds 2 GB/s before and after original-board exposure; SN850XE original-board reads fail](docs/sn700-crossover-results.md)
- [LinkedIn draft](docs/linkedin-draft.md)
- [Original bridge vendor initialization: decoded table, accepted write/readback, and persistence limits](docs/vendor-initialization.md)
- [Current USB4 state, latency/temperature curve and exact missing administrative interface](docs/current-usb4-diagnostics.md)
- [Official UGREEN firmware package and model check](docs/ugreen-firmware-findings.md)
- [Verified SN850X restriction, physical-fit question and SN850XE-specific reports](docs/sn850x-compatibility-investigation.md)
- [Draft UGREEN support request, not sent](docs/ugreen-support-request.md)
- [Admin1 authentication](evidence/firmware-admin1-authentication.txt)
- [SID authentication](evidence/firmware-sid-authentication.txt)
- [Authenticated range audit](evidence/authenticated-range-audit.txt)
- [Accepted factory reset, including result-writer error](evidence/approved-factory-reset.txt)
- [Independent post-reset query](evidence/post-reset-security-query.txt)
- [Post-reset sequential file test](evidence/post-reset-file-benchmark.txt)
- [Post-reset parallel test and physical counters](evidence/post-reset-parallel-benchmark.txt)
- [18 passing reset safeguards in the private lab](evidence/post-reset-safety-tests.txt)
- [26 portable safeguard checks: 25 pass, one private fixture skipped](evidence/portable-vendor-safety-tests.txt)
- [Factory values survive controlled NVMe reset](evidence/factory-profile4-controller-reset-persistence.txt)

Run the offline checks with Python 3:

```sh
python3 -m unittest discover -s tools -p 'test_*.py' -v
```

The fixture containing the owner's firmware and recovered challenge is deliberately absent from the repository, so its one private-fixture comparison is skipped in a clean checkout. The remaining tests cover the bounded vendor-command sequence and reset-test ordering, packet encodings, malformed responses, one-time reset arming, approval scope/age, private completion-record writes, and rejection of an internal, primary, ambiguous or wrong-serial device.

## Why a PSID was not required

The original bridge's 8051 startup initializer at code offset 0x091E provides five bytes to XDATA 0x0CA4. Its session constructor places them in a zero-filled 32-byte challenge. That exact challenge authenticated to this SSD as both Admin1 and SID. Standard AdminSP.Revert can then use the accepted SID authority; a PSID is an alternative recovery authority, not a prerequisite when SID access is available.

The global range was already unlocked. A second configured range covered about 32 MiB near the device end. We did not present RevertSP with KeepGlobalRangeKey=true as preserving every sector: it preserves the global key, while other range keys can be erased.

## Right to repair

Owners should have documented diagnostics, reset access and the information needed to reuse their storage after an enclosure fails. Recovering an administrator credential should not require reverse engineering a failed bridge. Open tools and reproducible evidence can reduce avoidable replacement and e-waste.

That position does not require an unsupported claim about manufacturer intent. This case proves a credential-recovery and reset route. Its performance result also shows that removing the observed OPAL configuration did not remove the measured slowdown.

## References and credit

- [TCG Opal specification](https://trustedcomputinggroup.org/wp-content/uploads/TCG-Storage-Opal-SSC-v2p02-r1p0_pub24jan2022.pdf)
- [Drive Trust Alliance sedutil](https://github.com/Drive-Trust-Alliance/sedutil), especially its [reset implementation](https://github.com/Drive-Trust-Alliance/sedutil/blob/master/Common/DtaDevOpal.cpp) and [command semantics](https://github.com/Drive-Trust-Alliance/sedutil/blob/master/Common/DtaOptions.cpp)
- [ASMedia USB-to-PCIe research](https://github.com/cyrozap/usb-to-pcie-re)
- [OrbStack USB passthrough](https://docs.orbstack.dev/features/usb)
- [dex6/sed-opal-unlocker](https://github.com/dex6/sed-opal-unlocker), an OPAL frontend that needs an existing password and does not recover this case's credential or transport

The Python code here is an independent implementation of protocol structures and the case-specific bridge route. Referenced upstream source and vendor firmware are not bundled.
