---
name: slow-usb-enclosure
description: "Diagnose a Mac external disk that is slower than USB 2: negotiated link speed, parent controller, and a synced write."
---

# Slow USB enclosure on macOS

Use when an external disk is connected but transfers slower than USB 2 (~30–40 MB/s), including a USB-C cable that "should" be 10 Gbps.

## Check the negotiated link first

1. `diskutil list external` for the BSD disk and volume.
2. `ioreg -r -n <USB product name> -l` and read:
   - `USBSpeed`: what macOS requested (3 = SuperSpeed+).
   - `Device Speed`: 2 = High Speed (USB 2), 3 = SuperSpeed, 4 = SuperSpeed+.
   - `UsbLinkSpeed`: 480000000 is 480 Mbps. 5000000000 is 5 Gbps. 10000000000 is 10 Gbps.
   - `USBPortType` 5 is a USB-C port. A direct attach to `AppleT6000USBXHCI` is not a hub.
3. `ioreg -p IOUSB -w 0` to see whether the device sits behind a USB 2 hub.

A new USB-C cable is often charge-only: power and USB 2 data, no SuperSpeed pairs. That matches requested SuperSpeed+ with a 480 Mbps link.

## Measure, then interpret

Synced write on the mounted volume:

```bash
dd if=/dev/zero of="/Volumes/<name>/.speedtest" bs=1048576 count=128 conv=fsync
```

Delete the file after. Do not trust a cached read of a file just written; it can report GB/s from the page cache.

- ~10 MB/s with `UsbLinkSpeed` 480000000 and 0 I/O retries: USB 2 fallback, and the chipset is not filling the 480 Mbps pipe. Not a disk error storm.
- `IOBlockStorageDriver` `Statistics` `Errors` and `Retries` at 0 rules out a retry storm.
- Fix the link before judging RAID mode or a second bay. `ASM1352R-Safe` is the RAID-mode product string (mirror), not the cause of a USB 2 link.

## Known device

Zach's Mediasonic Duo 10G is ASMedia ASM1352R, USB name `ASM1352R-Safe`, serial `20200409R5000001`. On MacBookPro18,2 it attaches to `AppleT6000USBXHCI@02000000` at location `0x02100000`. On 2026-11-05 and 2026-11-08 it requested SuperSpeed+ and negotiated 480 Mbps; a synced write was 9.9 MB/s with 0 errors. Recheck `Device Speed` after a 10 Gbps cable in a different Mac USB-C port. If it is still 2, the enclosure jack failed.
