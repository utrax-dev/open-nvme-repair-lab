# Draft request to UGREEN support

Draft only; not sent.

I am investigating low throughput with a UGREEN D700, SKU 55316, ASMedia ASM2464PD, USB VID:PID 174c:2463. A direct bridge-version query returned 250717850000 (250717_85_00_00).

The SSD is a WD_BLACK SN850XE 4000GB, firmware 624131EX, removed from a SanDisk Extreme Pro enclosure. Through this UGREEN on an Apple Silicon Mac, reads plateau around 330 MB/s. The link reports USB4 40 Gb/s and SSD PCIe Gen4 x4. A WD Red SN700 control on the same UGREEN/cable/dock path read at 2,338 MB/s before, and 2,032 MB/s after, exposure to the original board, with physical read counters and full-file integrity checks. The SN850XE's reported thermal-throttling counters and media-error count did not increase during the latest bounded read test.

Your Download Center's 55316 record currently lists conformity documents. The firmware package under 15976 / CM642 contains the older AS_USB4_240417_85_00_00.bin. We have not flashed it onto the D700.

Please confirm:

1. Is 250717_85_00_00 the current approved D700/55316 firmware? Is there a newer or model-specific build addressing WD/SanDisk NVMe compatibility, especially SN850XE with firmware 624131EX?
2. Please provide the approved image, updater, release notes, checksum and applicable board/hardware revisions. Does the CM642 package apply to D700 at all?
3. What configuration must be retained or supplied so an update preserves D700-specific USB4/TBT, PCIe, power, thermal, identity and other board settings? Can those settings be read and compared without flashing?
4. Is there a supported macOS/Linux administrative-command path while the enclosure remains in USB4 PCIe-tunneling mode, allowing NVMe Get/Set Features and diagnostic vendor commands without resetting the SSD or rebuilding queues?

I can provide a sanitized diagnostic report. Please identify any additional device-specific information needed privately.
