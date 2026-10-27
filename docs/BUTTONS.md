# Controls of the Micro Color Panel

Generated from devices/micro_color_panel.json by tools/build_buttons_doc.py. Do not edit by hand.

52 buttons and knob presses (decoded, bindable except the two shift keys), 18 rotary elements (decoded, not bindable yet), 55 free bindings.

## Buttons and knob presses (report 0x02)

| Name | Type | Byte | Bit | Bindable | Free combinations |
|---|---|---|---|---|---|
| auto_color | button | 2 | 4 | yes | - |
| offset | button | 2 | 5 | yes | shift_down |
| copy | button | 2 | 6 | yes | shift_down |
| paste | button | 2 | 7 | yes | shift_down |
| undo | button | 3 | 0 | yes | shift_up, shift_down |
| redo | button | 3 | 1 | yes | shift_up, shift_down |
| delete | button | 3 | 2 | yes | - |
| reset | button | 3 | 3 | yes | - |
| bypass | button | 3 | 4 | yes | shift_up, shift_down |
| disable | button | 3 | 5 | yes | shift_up, shift_down |
| user | button | 3 | 6 | yes | plain, shift_up, shift_down |
| loop | button | 3 | 7 | yes | - |
| shift_up | button | 4 | 0 | modifier only | - |
| shift_down | button | 4 | 1 | modifier only | - |
| play_still | button | 4 | 2 | yes | - |
| wipe_still | button | 4 | 3 | yes | shift_down |
| grab_still | button | 4 | 4 | yes | shift_up, shift_down |
| h_lite | button | 4 | 5 | yes | shift_down |
| viewer | button | 4 | 6 | yes | - |
| cursor | button | 4 | 7 | yes | shift_up, shift_down |
| select | button | 5 | 0 | yes | shift_up, shift_down |
| reset_lift | button | 5 | 1 | yes | - |
| reset_gamma | button | 5 | 2 | yes | - |
| reset_gain | button | 5 | 3 | yes | - |
| add_node | button | 5 | 4 | yes | - |
| add_window | button | 5 | 5 | yes | - |
| add_keyframe | button | 5 | 6 | yes | shift_down |
| prev_still | button | 5 | 7 | yes | - |
| next_still | button | 6 | 0 | yes | shift_down |
| prev_keyframe | button | 6 | 1 | yes | - |
| next_keyframe | button | 6 | 2 | yes | - |
| prev_node | button | 6 | 3 | yes | shift_up |
| next_node | button | 6 | 4 | yes | shift_up |
| prev_frame | button | 6 | 5 | yes | shift_up |
| next_frame | button | 6 | 6 | yes | shift_up |
| prev_clip | button | 6 | 7 | yes | - |
| next_clip | button | 7 | 0 | yes | - |
| backward | button | 7 | 1 | yes | shift_up |
| forward | button | 7 | 2 | yes | shift_up |
| stop | button | 7 | 3 | yes | shift_up |
| ylift_knob_press | knob press | 1 | 0 | yes | shift_up, shift_down |
| ygamma_knob_press | knob press | 1 | 1 | yes | shift_up, shift_down |
| ygain_knob_press | knob press | 1 | 2 | yes | shift_up, shift_down |
| contrast_knob_press | knob press | 1 | 3 | yes | shift_up, shift_down |
| pivot_knob_press | knob press | 1 | 4 | yes | shift_up, shift_down |
| mid_detail_knob_press | knob press | 1 | 5 | yes | shift_up, shift_down |
| color_boost_knob_press | knob press | 1 | 6 | yes | shift_up, shift_down |
| shadows_knob_press | knob press | 1 | 7 | yes | shift_up, shift_down |
| highlights_knob_press | knob press | 2 | 0 | yes | shift_up, shift_down |
| saturation_knob_press | knob press | 2 | 1 | yes | shift_up, shift_down |
| hue_knob_press | knob press | 2 | 2 | yes | shift_up, shift_down |
| lum_mix_knob_press | knob press | 2 | 3 | yes | shift_up, shift_down |

## Knobs, trackballs and rings

| Name | Type | Axis | Report | Byte | Width | Positive | Bindable |
|---|---|---|---|---|---|---|---|
| ylift_knob_turn | knob turn | turn | 0x06 | 1 | 32 bit | right | not yet |
| ygamma_knob_turn | knob turn | turn | 0x06 | 5 | 32 bit | right | not yet |
| ygain_knob_turn | knob turn | turn | 0x06 | 9 | 32 bit | right | not yet |
| contrast_knob_turn | knob turn | turn | 0x06 | 13 | 32 bit | right | not yet |
| pivot_knob_turn | knob turn | turn | 0x06 | 17 | 32 bit | right | not yet |
| mid_detail_knob_turn | knob turn | turn | 0x06 | 21 | 32 bit | right | not yet |
| color_boost_knob_turn | knob turn | turn | 0x06 | 25 | 32 bit | right | not yet |
| shadows_knob_turn | knob turn | turn | 0x06 | 29 | 32 bit | right | not yet |
| highlights_knob_turn | knob turn | turn | 0x06 | 33 | 32 bit | right | not yet |
| saturation_knob_turn | knob turn | turn | 0x06 | 37 | 32 bit | right | not yet |
| hue_knob_turn | knob turn | turn | 0x06 | 41 | 32 bit | right | not yet |
| lum_mix_knob_turn | knob turn | turn | 0x06 | 45 | 32 bit | right | not yet |
| lift_trackball | trackball | x | 0x05 | 2 | 24 bit | left | not yet |
| lift_trackball | trackball | y | 0x05 | 6 | 24 bit | down | not yet |
| lift_ring | ring | turn | 0x05 | 10 | 24 bit | right | not yet |
| gamma_trackball | trackball | x | 0x05 | 14 | 24 bit | left | not yet |
| gamma_trackball | trackball | y | 0x05 | 18 | 24 bit | down | not yet |
| gamma_ring | ring | turn | 0x05 | 22 | 24 bit | right | not yet |
| gain_trackball | trackball | x | 0x05 | 26 | 24 bit | left | not yet |
| gain_trackball | trackball | y | 0x05 | 30 | 24 bit | down | not yet |
| gain_ring | ring | turn | 0x05 | 34 | 24 bit | right | not yet |
