# D700 SN850X exclusion and relevance to SN850XE

## Verified restriction; technical reason unresolved

The owner supplied [Amazon ASIN B0F62NG7K3](https://www.amazon.com/dp/B0F62NG7K3). Its product details identify model/part number **55316**, and its branded product-description section states:

> This product is not compatible with WD SN850X SSD

This was independently verified in the rendered page and the fetched product-description text on 23 October 2026. It is a product-description statement, rather than a customer review. Earlier checks of UGREEN's regional product/download pages missed this relevant restriction. The listing does not explain its technical cause, specify affected firmware or capacities, name SN850XE, or identify a fixing update.

The listing separately warns that some SSDs can be too thick and suggests thinner thermal pads. It does **not** explicitly connect that fit warning to the SN850X exclusion. Its advertised double-sided cooling fins are also not a specification for underside SSD-component clearance. The owner reports this particular SN850XE sat flat and the cover closed freely. Physical fit/contact has not been independently inspected.

## What can and cannot explain the observed ceiling

| Candidate explanation | Evidence | Status for this case |
| --- | --- | --- |
| Insufficient clearance / pad pressure | The listing contains a general thickness warning; owner reports flat, free fit | Possible, but not demonstrated or established as the reason for the SN850X exclusion |
| Ordinary reported SSD thermal throttling | Latest first read remained around 330 MB/s at reported 40 C; thermal transition/time counters stayed zero | Weakened for the tested workload; unreported component/bridge limits remain possible |
| Universal ASM2464PD inability to operate with SN850X | A first-person [Framework report](https://community.frame.work/t/details-on-exact-level-of-support-of-usb4-ports-on-13th-gen/31986/3) measured SN850X at about 3.8 GB/s read in a Zike enclosure and similar results in an Airusan, both using ASM2464PD | Counterexample to a universal chipset prohibition; not proof D700 is compatible |
| D700-specific firmware, configuration, hardware or power interaction | Product exclusion is specific evidence against assuming compatibility; current native feature/vendor access is incomplete | Remains a serious candidate; no identified failing command, power event or fixing release |
| SN850XE-specific firmware/initialization behavior | Same model/firmware is reported slow in native NVMe slots and other enclosures; our factory reset did not lift the ceiling | Also remains a serious candidate; not yet a decoded causal mechanism or evidence of intent |

The SN700 comparison proves the existing UGREEN/host path can exceed 2 GB/s with **SN700**. It does not validate that path for SN850X or SN850XE. Both captured SSDs report vendor ID 0x15b7, so the evidence does not support a blanket rejection of all Western Digital devices.

The saved Identify descriptors advertise maximum power of **9.0 W** for the SN850XE's highest operational state versus **5.5 W** for the SN700's. These are supported-state maximum descriptors, not measured draw, current selected state, delivered power or proof of an inadequate supply. They make the SN700 an incomplete power-demand control. No power-state write or thermal-policy change was made to test this interpretation.

## Additional local checks after keeping the support request as a draft

The saved installed UGREEN code image contains its 250717850000 version at code offset 0x200. Its code SHA-256 is f069ce8c435eb3bb2649255a45d57a8b258589ee7555c99d5d3c3fff6a9c8cd0. The reviewed image/bank copies have no literal ASCII SN850 model string. No named SN850X exclusion path was identified in this bounded screen. This is **not** a complete blacklist audit: firmware can match numeric PCI identifiers, capabilities or other fields without a readable model name, and an interoperability defect need not involve intentional rejection. The firmware was inspected offline; none was modified, loaded or flashed.

The current saved topology uses the native macOS NVMe driver over USB4 PCIe tunneling. Consequently, the present path is not the USB/SCSI-to-NVMe translation path used for the earlier diagnostic guest. The bridge still participates in PCIe link, power and reset behavior, while the host driver controls the normal NVMe queues. A missing original-enclosure initialization sequence remains technically relevant to SN850XE, but its effect has not been demonstrated on those active queues.

The listing also contains an owner's uncontrolled report of a controller-side pad change improving writes with a **Hynix P41**, rather than SN850X. That does not explain UGREEN's exclusion. It is a reason to retain bridge cooling as an unmeasured variable: the SSD's 40 C SMART temperature is not a measurement of the ASM2464PD temperature. No thickness, pad or cooling change was requested or performed on John's enclosure.

Creator Pro was not queried for new drive state. The power comparison above uses the saved secondary/SN700 captures. The support request remains unsent at the owner's direction.

## More closely matched SN850XE reports

The [ThinkPad thread](https://thinkpad-forum.de/threads/nvme-wd-sn850xe-4tb-ssd-aus-sandisk-extreme-v2-portable-l%C3%A4uft-langsam-ideen.246536/) records approximately 323 MB/s read / 265 MB/s write in a native laptop PCIe 3.0 x4 slot. The poster later qualified an initially fast UGREEN read as possibly cached. Another contributor, naming SN850XE 4000GB / 624131EX, reports slow Unitek and OWC paths and restored ordinary portable-drive speed in the original SanDisk enclosure. These are independent owner accounts with incomplete controls; they are corroborating leads rather than lab-verified results on John's SSD.

A separate [Framework owner report](https://community.frame.work/t/notes-from-attempting-to-extract-wd-pc-sn740-firmware-from-dell-updater-exe/58376/9) describes the same SN850XE firmware running near 250 MB/s in a regular NVMe slot and an unsuccessful attempt to activate retail SN850X firmware. Its attribution of the slowdown to firmware is the author's interpretation. The thread does not establish a safe crossflash or a successful performance repair. No retail SN850X firmware was sent to John's SSD.

These reports weaken the proposition that replacing D700 alone is guaranteed to solve the SN850XE ceiling. They also prevent treating the retail SN850X warning and the SN850XE's behavior as one proven defect.

## What would identify the reason

No inspected UGREEN/ASMedia technical note explains the D700 exclusion. The prepared support request now asks whether the restriction is mechanical, power/thermal, PCIe reset/link behavior, APST/ASPM, or an SSD/bridge-firmware issue, and asks for affected revisions and any validated correction. It has not been sent.

On the current physical connection, the remaining software gap is still access to current administrative features and exact vendor-profile write/readback while retaining the normal data queues. A same-SSD comparison through another known-supported controller would answer a different question from the completed SN700 test, but no new physical change is requested here. Creator Pro remains connected and excluded.

**The restriction is confirmed. Its engineering cause, its applicability to SN850XE, and a resulting fix are not yet established.**
