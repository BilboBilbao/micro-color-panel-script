"""LED write test, stage 1 (decision D22). Throwaway script, NOT part of the program.

Sends ONLY output report 4 (id 4 plus 6 data bytes) to the panel over USB. Nothing else is sent: no report 2,
no feature reports, no requests. Bit n of report 4 is in byte 1 + n // 8, mask 1 << (n % 8) (docs/HARDWARE.md).

Steps, each one after you press Enter: bit on for 3 seconds, then all bits off.
  1. bit 2 (control: Resolve sends this bit for Offset, expected: Offset turns green)
  2. bit 1 (never seen in the recording)
  3. bit 9 (never seen in the recording)
Look at the panel and write down which button shows which color.

Before you start: panel connected by USB cable, Resolve running on the Color page (the LEDs are only bright then).
Stop: Ctrl+C (all bits are switched off first). If something looks wrong: stop the script and unplug the cable.
"All bits off" also switches off the colors Resolve set; press Offset or Bypass in Resolve to see them come back.

Start (from the project folder): python tools\\led_test_stage1.py
"""
import time

VID, PID, USAGE_PAGE = 0x1EDB, 0xDA0F, 0xFF00
USB = 1                                    # hidapi bus_type value for USB
REPORT_ID, DATA_BYTES, BIT_COUNT = 4, 6, 48
STEPS = [(2, "bit 2 (Offset, control)"), (1, "bit 1"), (9, "bit 9")]
ON_SECONDS = 3


def report4(bits):
    """Report 4 as bytes (id plus 6 data bytes) with the given bits set. Bits outside 0 to 47 raise ValueError."""
    data = bytearray(DATA_BYTES)
    for bit in bits:
        if not 0 <= bit < BIT_COUNT:
            raise ValueError(f"bit {bit} is outside 0 to {BIT_COUNT - 1}")
        data[bit // 8] |= 1 << (bit % 8)
    return bytes([REPORT_ID]) + bytes(data)


def send(dev, bits):
    """The only write of this script. Prints what the call returned; -1 means the write failed."""
    report = report4(bits)
    result = dev.write(report)
    print(f"   sent {report.hex(' ')} ({len(report)} bytes), the call returned {result}")
    if result < 0:
        raise OSError(f"write failed: {dev.error()}")


def open_usb_panel(hid):
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == USAGE_PAGE:
            if d.get("bus_type") != USB:
                raise SystemExit("The panel entry is not reported as USB. This test runs over the USB cable only.")
            dev = hid.device()
            dev.open_path(d["path"])
            return dev
    raise SystemExit("Panel not found. Is it connected by USB cable?")


def main():
    import hid
    dev = open_usb_panel(hid)
    print("Panel opened. Resolve should be open on the Color page.")
    try:
        for bit, label in STEPS:
            input(f"\nPress Enter to switch on {label} for {ON_SECONDS} seconds (Ctrl+C stops) ... ")
            send(dev, [bit])
            time.sleep(ON_SECONDS)
            send(dev, [])
            print("   Which button showed which color? Does the panel still react normally?")
        print("\nDone. In Resolve press Offset or Bypass once: do the colors come back?")
    except KeyboardInterrupt:
        print("\nStopped.")
    except OSError as error:
        print(f"\nError: {type(error).__name__}: {error}")
    finally:
        try:
            send(dev, [])                  # always leave with all bits off
        except Exception as error:         # noqa: BLE001  (last resort, the result is printed)
            print(f"   final all-off failed: {type(error).__name__}: {error}")
        dev.close()


if __name__ == "__main__":
    main()
