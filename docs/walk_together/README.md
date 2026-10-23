# Walk Together meadow screen captures

These are **desktop mock renders, not photos of a badge.** They are produced by
`tools/walk_screen_preview.py captures`, which runs the real
`walk_together/screen.py` draw code against a Pillow-backed stand-in for the
badge runtime. The stand-in uses Pillow's built-in font, so text widths differ
from the badge's `font.nope`; check text fit on hardware.

| State | HIRES 320x240 | Default 160x120 (shown 3x) |
| --- | --- | --- |
| In range | `in-range-hires-320x240.png` | `in-range-lowres-160x120-x3.png` |
| Out of range (last shared 1200, +300 own steps, 3 minutes apart) | `out-of-range-hires-320x240.png` | `out-of-range-lowres-160x120-x3.png` |
| Goal just reached | `goal-reached-hires-320x240.png` | `goal-reached-lowres-160x120-x3.png` |

There is no separate inverted capture: the firmware keeps the display upright
when the badge is inverted, and `screen.py` never reads the orientation
(`tests/test_screen.py` checks the drawing is identical either way).

The step count's size and position are provisional (the plan has not decided
them); they are constants at the top of `walk_together/screen.py`.
