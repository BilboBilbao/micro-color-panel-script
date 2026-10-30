"""LED write test, stage 2a (decision D23). Throwaway script, NOT part of the program.

Goes through the 48 bits of output report 4 one at a time: Enter, the bit is on for 2 seconds, then all bits off.
Only report 4 is sent (through send() of led_test_stage1.py), nothing else. Same conditions as stage 1:
panel connected by USB cable, Resolve running on the Color page.
Write down for every bit: which button lights up, in which color. Nothing visible is also an answer.
Stop: Ctrl+C (all bits are switched off first). If something looks wrong: stop the script and unplug the cable.

Start (from the project folder): python tools\\led_test_stage2a.py
"""
import time

from led_test_stage1 import open_usb_panel, send

STEPS = list(range(48))
ON_SECONDS = 2


def main():
    import hid
    dev = open_usb_panel(hid)
    print("Panel opened. Resolve should be open on the Color page.")
    try:
        for bit in STEPS:
            input(f"\nBit {bit}: press Enter to switch it on for {ON_SECONDS} seconds (Ctrl+C stops) ... ")
            send(dev, [bit])
            time.sleep(ON_SECONDS)
            send(dev, [])
            print(f"   bit {bit}: which button, which color?")
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
