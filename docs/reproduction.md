# Reproducing the validated reset route

This is an experimental procedure for the exact hardware/firmware listed in the README. The factory-reset step irreversibly erases all target SSD data. Back up first, identify the intended SSD and enclosure by their individual serials, and keep unrelated storage outside the diagnostic guest. The procedure does not promise a performance improvement.

## 1. Preserve the baseline

Save the SSD model, firmware, capacity, serial, SMART data, volume identity and host connection. Record a benchmark before intervention. Check the SSD's identity again after every physical reconnect; do not assume a prior disk number still identifies it.

The case used a dedicated Alpine ARM64 OrbStack guest with Python 3 and libusb. macOS exposes Identify and log reads, but the tested native interface does not provide the NVMe security command path used here. USB-A made the enclosure available to Linux USB passthrough. It is a command-access connection, not the speed-test connection.

## 2. Supply the owner's original firmware image

Obtain a read-only saved firmware image from the owner's original bridge using tools appropriate to that controller. [The upstream ASMedia research project](https://github.com/cyrozap/usb-to-pcie-re) documents its flash-read interface. This repository does not include a vendor image or an automatic dumper for every original enclosure.

The case's reviewed code image is 65,368 bytes with SHA-256:

```text
0468b822080cc3b26de98b935175495120c1ad5046e505d4325e73a412ddac20
```

In this case only, that image began at offset 0x82 of the saved 65,536-byte raw flash image. If using that exact raw layout, extract the 65,368-byte code slice locally and verify its SHA-256. An image with a different hash is unsupported; do not patch the guard simply to make it run.

Extract the challenge without displaying it:

```sh
umask 077
python3 tools/extract_firmware_challenge.py   --code-image /private/local/path/original-controller-code.bin   --output tools/private-firmware-auth-challenge.bin
```

The output must be a new file. It is created with mode 0600. Keep it private and outside version control. It is the authentication material, not an ordinary diagnostic log.

## 3. Prepare the dedicated USB guest

1. Safely unmount the intended secondary SSD on macOS. Keep the primary and unrelated drives out of the guest.
2. Connect the UGREEN over USB-A. Use OrbStack's USB inventory to locate the exact 174c:2463 enclosure serial.
3. In the dedicated guest, load usb-storage, save its existing quirk string, and add the enclosure-specific ignore flags before attaching the device. The case used 174c:2463:iu so neither UAS nor usb-storage bound to it. Preserve any pre-existing settings for cleanup.
4. Pass only that exact USB bus/serial into the guest. Verify all of its storage interfaces are unbound. The Python transport refuses to detach a live kernel driver itself.

Define the owner-verified enclosure and SSD serials locally; never copy someone else's values. These serials are not the recovered password. Resolve the repository's shared guest path: on this Mac, the host checkout was visible under /mnt/mac followed by its absolute host path.

## 4. Verify the recovered authority

Run from the guest, as root, replacing the placeholders with the exact locally verified serials:

```sh
python3 /mnt/mac/absolute/path/to/repository/tools/ugreen_tcg_session_probe.py   ENCLOSURE_SERIAL SSD_SERIAL --query-anonymous --firmware-sid-check
```

The first mode name selects a fresh Identify route; the additional flag starts an authenticated SID session. Require the exact tested firmware, successful SID method status and a valid lifecycle-table response. No reset is requested by this command.

For the Admin1/range audit, the separate option is --firmware-admin1-check. Every completed diagnostic run restores the saved controller registers, but stock I/O queue cursors need a physical reconnect before another fresh Identify run. Close/detach the diagnostic interface, replug and repeat the identity checks between runs. The private same-attachment continuation option is not a reset route; an erasing reset always requires fresh Identify.

## 5. Explicitly authorize the full erase

After reviewing the exact physical target and backing up, create tools/private-reset-authorization.json locally with mode 0600. The schema is:

```json
{
  "approved": true,
  "target_usb_serial": "YOUR_ENCLOSURE_SERIAL",
  "target_ssd_serial": "YOUR_SSD_SERIAL",
  "firmware": "624131EX",
  "scope": "erase_all_secondary_data_and_recreate_apfs",
  "approved_at_unix": 0
}
```

Replace the serial placeholders and set approved_at_unix to the actual current Unix time when the owner approves. Zero is intentionally expired. The lab guard requires a matching explicit approval less than 24 hours old. An approval file is an accident-prevention mechanism, not protection against a privileged person editing the code.

Reconnect the enclosure over USB-A so the following run can make a fresh Identify. Unmount on macOS and attach only the verified unbound enclosure to the dedicated guest again.

## 6. Send the reset once

```sh
python3 /mnt/mac/absolute/path/to/repository/tools/ugreen_tcg_session_probe.py   ENCLOSURE_SERIAL SSD_SERIAL --query-anonymous --erase-secondary-and-reset-opal
```

The tool requires a fresh SSD identity, the exact bridge firmware, the private challenge, matching approval and an accepted SID session. It sends only the fixed AdminSP.Revert reset body, at most once. It requires a successful method response and waits for inactive/unlocked Discovery0 state before recording completion.

**If it reports RESET OUTCOME UNKNOWN, do not automatically retry or power-cycle.** The prototype preserves live controller state in that case so completion can be investigated. This is an advanced repair-research tool; there is no generic unattended recovery for an ambiguous hardware result.

The case's first live reset succeeded, but its original completion writer then raised TypeError. The raw transcript records that error. A separate information query corroborated lifecycle 8, SID equal to MSID and locking disabled. The completion record was recovered from that evidence; the writer was corrected and tested. No second reset was sent.

## 7. Restore normal access and recreate APFS

After verified completion, require the tool's original-register restoration/readback message. Detach only the intended enclosure, restore the guest's prior storage-driver quirk string and stop only the dedicated diagnostic guest. Reconnect the enclosure using USB-C/USB4.

On macOS, the case-specific format helper requires both matching owner approval and a successful private reset record. It finds the physical SSD by model/serial, then checks firmware, capacity, unique identity and external whole-device status before erasing the partition map:

```sh
python3 tools/ssd_reset_format.py --format-approved-secondary
```

This helper recreates GUID/APFS with the case's volume name UTRAX Secondary Drive. It validates the new APFS physical-store mapping and saves tools/secondary-after-reset-volume.json. The private authorization and result files belong next to these scripts. Do not fabricate a successful reset record to get past the guard.

## 8. Verify the result and report its limits

Verify APFS and SMART, stop other benchmarks, and retain the connection topology and host-load context. The bounded file benchmark checks the new volume UUID and live physical identity before creating its own temporary file:

```sh
python3 tools/ssd_post_reset_benchmark.py
python3 tools/ssd_parallel_file_benchmark.py
```

Run these sequentially, never concurrently. They create and remove only their own random-name files and verify the complete 4 GiB data hash. The parallel test also measures physical-device read counters. A repeated-read number can include cache effects; do not advertise it as the SSD's sustained speed.

In the documented case, the standard reset succeeded but did not lift the approximately 270/330 MB/s write/first-read ceiling. The freezing symptom was not established as repaired. Publish the measured outcome rather than calling this a universal anti-shucking unlock.
