# Keep a BRAVO test host reachable through Tailscale

The host runs BRAVO locally; Funnel supplies its public HTTPS address. Viewers
use the owner's link and their individual BRAVO credentials. They do not install
Tailscale. Follow [lab access](lab-access.md) for viewing and
[local deployment](../local-deployment.md) for the application and data.

## Configure the host

Keep the host plugged in, awake, connected to the network and running its
container runtime. Turning off the display is compatible with hosting; putting
the computer to sleep is not. On macOS, setting the display timeout to Never does
not establish that system sleep is disabled. Check Battery > Options > Prevent
automatic sleeping on power adapter when the display is off. The Mac App Store
Tailscale app requires a desktop login after reboot. Do not promise unattended
reboot recovery from a login item alone.

Use one Tailscale installation. Check the installed version and the official
[macOS variants guide](https://tailscale.com/docs/concepts/macos-variants) before
changing variants; installing a second variant over the first is not a repair.
Do not disable institutional VPN or endpoint protection based on a guess.

For the Mac App Store variant, the official
[system-policy instructions](https://tailscale.com/docs/integrations/mdm/mac)
support these user preferences. Record any existing values before changing them:

```sh
defaults write io.tailscale.ipn.macos ReconnectAfter -string 1m
defaults write io.tailscale.ipn.macos AlwaysOn.Enabled -bool true
defaults write io.tailscale.ipn.macos AlwaysOn.OverrideWithReason -bool true
```

Always On prevents an ordinary disconnect. Override With Reason permits an
intentional temporary disconnect, and Reconnect After restores the connection
after one minute. These are Tailscale's own policies, not a separate polling job.
See [policy definitions](https://tailscale.com/docs/features/tailscale-system-policies).
The standalone variant uses a different preferences location; follow its official
instructions rather than copying this App Store example.

Confirm what the running client actually applied:

```sh
export TAILSCALE_BE_CLI=1
/Applications/Tailscale.app/Contents/MacOS/Tailscale syspolicy reload
/Applications/Tailscale.app/Contents/MacOS/Tailscale status
/Applications/Tailscale.app/Contents/MacOS/Tailscale funnel status
```

If the saved preferences are absent from the effective policy list, relaunch
Tailscale and check again. A successful `defaults write` alone is insufficient.
For planned maintenance, the CLI supports `down --reason "planned maintenance"`;
the reconnection timer still applies. To stop hosting for longer, deliberately
restore the previous policy values, verify the effective list, and then stop the
tunnel. Restore preexisting values rather than blindly deleting organization
settings. Configure launch at login and verify the actual login item separately.

After BRAVO's local checks and authenticated access tests pass, the owner can
enable the approved public service:

```sh
/Applications/Tailscale.app/Contents/MacOS/Tailscale funnel --bg 8080
```

Keep BRAVO authentication, viewer permissions and HTTPS cookie settings enabled.
Do not expose SSH, the database or a development server through Funnel.

## Verify reachability and recovery

Check all three layers independently:

1. Run `scripts/bravo-appliance check` and verify the intended local BRAVO URL.
2. Verify Tailscale reports Running and the other laptop can connect.
3. From a different device, verify the public HTTPS BRAVO page, normal login,
   viewer restrictions and logout. A tailnet device may resolve the hostname to
   its private address; verify that a public-route test actually uses a public
   Funnel relay, rather than treating private access as public acceptance.

Observe connectivity over time. A green menu icon or one HTTP response does not
prove persistent availability. Record any deliberate test interruption separately
from unsolicited failures. When testing recovery, verify the public service after
the VPN reconnects; the two may recover at different times. Keep dated evidence
outside Git, with the version, host, interval, failures and interventions.

If macOS logs report `stopTunnel: userInitiated` or `WantRunning=false`, that
identifies an explicit stop path, not necessarily a human action. Trace the caller
before attributing it to a person or another application. A test while an idle
sleep assertion is active can exclude idle sleep for that particular failure.
Do not claim the original cause is solved merely because automatic recovery works.

## Evidence boundary

On 09/05/2026, both test laptops were verified on Tailscale 1.102.3. The initial
post-update observation still encountered unsolicited stops while the primary Mac
was kept awake. The native one-minute timer reconnected Tailscale after 61 seconds;
the public BRAVO route recovered subsequently. After relaunching the app, the
effective policy list confirmed both Always On settings and the timer, and an
unreasoned CLI disconnect was refused. A subsequent ten-minute observation had
20 successful VPN/peer checks but only 18 successful public HTTP checks; native
extension restarts still occurred between samples. Automatic recovery is verified,
but persistent public hosting on this primary laptop is not accepted as stable.
Replacement-host acceptance requires its own dated results.
