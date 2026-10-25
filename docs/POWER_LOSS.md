# What happens after a power cut, and what can be automated

Honest summary: **the phone cannot recover from a power cut on its own.** It is *semi-tethered*: after any reboot it
comes up as a normal, un-jailbroken iPhone (no SSH, no Tailscale, no sensors) until a computer re-runs checkra1n.

## What is already automatic once the jailbreak is back
After ``scripts/rejailbreak.py` from ios12-tailscale` succeeds, everything below starts by itself (launchd, no manual step):
* `com.local.tailscaled` -> the phone rejoins the tailnet
* `com.local.sensors` -> sensor readings flow to the broker and the hub

## What is not, and the options
| Piece | Problem | Options (none built or tested yet) |
|---|---|---|
| **Noticing** the outage | nobody is looking | The hub dashboard shows OFFLINE after 15 s with no data, and the broker's retained `sensors/iphone6/status` flips to `offline` by itself. A push alert (ntfy, email, Home Assistant) can be added on the homelab. |
| **Running checkra1n** | needs a computer with USB access and root | An always-on Linux box or Raspberry Pi permanently plugged into the phone, running `rejailbreak.py` (ios12-tailscale) (its USB library and `iproxy` are the only needs). |
| **DFU mode** | needs a button combination (Power+Home timed) on an iPhone 6 | Drive the two buttons from GPIO through relays/optocouplers wired to the button contacts, or a servo/solenoid rig. This means opening or modifying the phone. The timing is: Power+Home 8 s, release Power, hold Home 5 s. Not tested. |
| **Exploit failures** | `error -21/-31` happen now and then | The script waits and the phone can be put back into DFU and retried automatically, bounded to a few attempts. |
| **Boot loop risk** | a repeated failed boot on a phone with no battery | See below. |

## Battery eliminator: risks to check first
* iPhones normally expect a real battery with a temperature sensor and a gas gauge. A "battery eliminator" board
  usually fakes these, but some phones refuse to charge, boot, or report power properly without a believable
  gauge, and some show the "service" warning. Test on the bench before sealing anything.
* The phone currently reads a battery gauge of about 41 C and a charger junction around 51 C while powered over USB.
  Heat is the main long-term risk for an always-on phone. The dashboard graphs it; consider an alert threshold.
* Data in the feed that matters here: `power.*` (bus voltage, battery voltage, current) and `temp_c.*`.

## Suggested minimum
1. Watchdog alert on the homelab (cheap, do first).
2. A permanently attached always-on host that can run `rejailbreak.py` (ios12-tailscale) on command.
3. DFU hardware only if unattended recovery is really needed.
