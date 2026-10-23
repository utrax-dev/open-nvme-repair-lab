# LinkedIn draft

Draft only. No post has been published. Add the repository link after publication.

---

A failed SSD enclosure should not turn a reusable NVMe module into e-waste.

When the controller in my SanDisk Extreme Pro appeared to fail, I moved its 4 TB NVMe into a UGREEN enclosure. The initial benchmark was about 256 MB/s write and 317 MB/s read. The bare module had no visible recovery PSID.

Working from my Mac, we built a diagnostic route through a small Linux guest and the replacement bridge to the NVMe administrative queue. Then we traced the original SanDisk controller's firmware and recovered the credential its OPAL session code used.

That credential authenticated successfully as both Admin1 and SID. We performed the standard factory reset without a PSID, verified that the security provider returned to its factory state, and recreated APFS. The code, safeguards and evidence are being packaged openly.

The result that matters: the reset worked, but it did not fix throughput. First reads still measured about 330 MB/s, including a parallel test whose physical-device counters confirmed more than 4 GB read from the SSD. Both full-file integrity checks passed.

I am publishing that negative result alongside the recovery method. It prevents the next owner from repeating a claim that an OPAL reset automatically unlocks 7 GB/s.

My stance is straightforward: owners deserve documented diagnostic access, usable reset procedures and the information required to reuse the hardware they bought. Recovering a working administrator credential should not require reverse engineering a failed enclosure's firmware.

Right to repair means practical access. Open tools and reproducible evidence extend hardware life, reduce avoidable replacement and keep reusable components out of the waste stream. Manufacturers should build that access into their products.

#RightToRepair #NVMe #OpenSource #EWaste #HardwareRepair
