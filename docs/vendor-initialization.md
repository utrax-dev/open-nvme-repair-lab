# Original SanDisk bridge: vendor initialization findings

The original bridge has an enabled configuration table that selects two parameter values according to its USB link mode. Its initialization code builds NVMe vendor commands `0xFD` and `0xFE` from that table. **This establishes an enclosure-specific initialization mechanism; its effect on SSD performance is not established.**

## Evidence and scope

The original controller was connected empty; the NVMe remained in the UGREEN enclosure. A fixed read-only XDATA probe verified original bridge firmware `19062091e48a`, then read the enable flag and table. It sent no NVMe commands through that empty controller.

| Observation | Location / result |
| --- | --- |
| Initialization enable flag | XDATA `0x0C00` = `1` |
| Runtime table | XDATA `0x0337`, 300 bytes read |
| Records inspected by the startup loop | First 14 three-byte records |
| Table read SHA-256 | `65c8f31ca02cb72fac187a47a60cbef600a2e6bb865c1a2ee3f9a0fa7745a980` |
| Reviewed 8051 code SHA-256 | `0468b822080cc3b26de98b935175495120c1ad5046e505d4325e73a412ddac20` |
| SSD command-effects evidence | Saved Admin Command Effects entries for `0xFD` and `0xFE` each equal `0x00000001` |

The command-effects entries advertise support. They do not document command semantics, guarantee that a particular parameter is valid, or certify read-only behavior.

## Actual table contents

Values are shown in hexadecimal. The selector numbers are the firmware's internal values; marketing link names and the units of the parameters have not been verified.

| Link selector | Parameter `1` | Parameter `2` |
| --- | --- | --- |
| `0` | `0x05` | `0x00` |
| `1` | `0x0C` | `0x05` |
| `2` | `0x1E` | `0x19` |
| `3` | `0x1E` | `0x19` |
| `4` | `0x29` | `0x1C` |

The remaining four records are `(selector, parameter, value)` = `(0xFF, 0x38, 0x19)`, `(0xFF, 0x40, 0x1C)`, `(0xFF, 0x48, 0x20)`, `(0xFF, 0x50, 0x23)`. The selector function returns `0` through `4`, so those four records do not match that function in the reviewed startup loop. Their separate purpose is unknown.

## Selection and command construction

Assembly at code `0xD1ED` checks the NVMe device-type state and the enable flag. Function `0xC2BA` derives a selector from USB hardware register fields at `0x9100` and `0x92B8`. The loop compares that selector with each record's first byte.

For a matching record, the builder at `0xEEB9` starts with a zeroed 64-byte command, sets opcode `0xFD`, puts the parameter number in `CDW10`, and the value in `CDW11`. The caller then invokes `0xAFA0`, which constructs opcode `0xFE` with the same parameter in `CDW10`. Namespace ID and data pointers remain zero in these command frames; the queue assigns a command ID.

For selector `4`, the reconstructed sequence is therefore:

```
0xFD: CDW10=1, CDW11=0x29
0xFE: CDW10=1, CDW11=0
0xFD: CDW10=2, CDW11=0x1C
0xFE: CDW10=2, CDW11=0
```

Both builders inspect completion status. The reviewed caller does not use their returned success booleans to establish a performance change. No runtime trace with the NVMe installed in the original bridge was captured.

## Executed factory-profile experiment

The two standalone `0xFE` frames initially completed successfully with result DWORD0 = 0 for both parameters. We then sent the exact four-frame selector-4 sequence above. All four completions reported status zero. The `0xFE` followups returned **41 (`0x29`)** and **28 (`0x1C`)**, matching the values just written by `0xFD`. This confirms a write/readback mechanism for these two parameters on this SSD; their engineering meaning is still unknown.

Health before and after remained approximately 38°C, critical warning 0, media errors 0, and cumulative error-log count 1. The original controller registers were restored and verified afterward.

After returning to USB-C, a fresh 4 GiB test measured **266.0 MB/s write including full flush and 331.9 MB/s first read with eight workers**. Physical counters confirmed exactly 4,294,967,296 read bytes across 8,192 operations, with no added read errors or retries. The full-file hash matched. Host load averages were approximately 20.2 / 16.2 / 18.7; this was not an isolated host.

After moving back to USB-A, a further two-command `0xFE` probe returned **0 and 0**. Values therefore did not survive the full controller-reset/reconnect sequence. Because diagnostic access itself resets the NVMe controller, this result does not identify which reset or power transition cleared them. It also does not test throughput while the settings are known to remain active.

## What remains to establish

The parameter units, meaning, persistence across controller reset/power loss, and effect on performance remain unknown. The pattern is compatible with a link-dependent operating profile, but it is not proof of a power limit, a thermal threshold, an authentication requirement, or an intentional anti-shucking restriction.

The already verified SID-authenticated OPAL reset did not fix the measured slowdown: first reads still measured about 330 MB/s afterward. That security finding must remain separate from this vendor-command investigation.

Any experimental command result needs to be recorded with its exact frame, completion status, health checks and connection state. A speed comparison after a USB-A to USB-C reconnect must also account for the intervening power cycle, which could clear a volatile setting.

No vendor firmware, decompiled vendor source, credentials or individual device serials are included here.

## Experimental reproduction tools

These commands are research tools for the exact tested firmware. They are separate from the validated OPAL reset procedure and do not constitute a speed fix. Vendor parameters have undocumented semantics. The replay changes SSD configuration and has no independently verified rollback beyond the observed reset/reconnect behavior.

Use the isolated Linux/libusb guest procedure in `reproduction.md`; leave all unrelated storage outside it. Verify the original controller is physically empty before using the table reader. With its exact USB serial and firmware `19062091e48a`, run:

```sh
python3 tools/original_bridge_table_probe.py ORIGINAL_CONTROLLER_USB_SERIAL
```

This reader permits only fixed XDATA reads and writes its binary results as new mode-0600 `private-original-*.bin` files next to the script. Keep those files private. The UGREEN probe also needs the included `original-vendor-init-table-decoded.json` metadata beside its script. The table-prefix, enable-flag and firmware guards reject other observed configurations.

After safely unmounting the secondary, reconnect it, attach only the verified UGREEN to the guest, and keep its Linux storage interfaces unbound. The two-command followup probe is:

```sh
python3 tools/ugreen_vendor_followup_probe.py ENCLOSURE_SERIAL SSD_SERIAL --probe-factory-followups
```

The separately selected four-frame replay is:

```sh
python3 tools/ugreen_vendor_followup_probe.py ENCLOSURE_SERIAL SSD_SERIAL --replay-original-profile4
```

The program verifies a fresh SSD Identify and exact UGREEN firmware, takes temporary administrative-queue control, checks live command-effects and SMART data, then sends only the fixed sequence. No caller-supplied opcode or parameter values are accepted. A successful replay requires the exact 41/28 readbacks. A failed or ambiguous submission is not retried. For an unknown completion, the live controller state is preserved for investigation. On known completion, saved controller registers are restored and verified; stock I/O requires physical reconnection afterward.

The `--check-controller-reset-persistence` mode additionally rebuilds the diagnostic NVMe queue after verified 41/28 readbacks, then reads parameters 1 and 2 again in the same physical USB attachment. Its sequencing and fail-closed guards have offline tests. Live results must be reported separately from those tests.

## Controlled controller-reset result

A further experiment isolated NVMe controller reset within a single USB attachment. It freshly identified the same SSD, replayed the exact four factory frames, required successful 41/28 readbacks, toggled NVMe CC.EN off/on and rebuilt the diagnostic administrative queue. **The subsequent 0xFE results were still 41 and 28.** No physical USB reconnect occurred between those writes and readbacks. Health remained approximately 36°C, critical warning 0, media errors 0 and cumulative error-log count 1.

Thus the tested NVMe controller reset alone did not clear these parameters. The zeros seen after the earlier physical reconnect were associated with that broader reconnect/initialization path, which also included power/link changes and a fresh bridge Identify route. The exact clearing action was not isolated. In particular, the USB-C benchmark does not measure throughput while the 41/28 values are independently known to be active. There is still no demonstrated full-speed repair or proof of manufacturer intent.
