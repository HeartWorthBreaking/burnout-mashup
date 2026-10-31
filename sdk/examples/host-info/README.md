# Example (h): host-info probe (bmashup.host 1)

`bm_sdk_host_info.asi` reads the `bmashup.host` table a Burnout Mashup platform host offers FIRST and logs:

```
[PLUGIN bmashup-sdk.host-info] host info: Burnout Mashup platform 0.1.1 (0.1.1), Takedawn <version>, build bmp-0.1.1+b56e33b66dc3, game D0FC2EF4E9B2A86F
[PLUGIN bmashup-sdk.host-info] host info: build identity bmp-0.1.1+b56e33b66dc3 = the SDK's reference host (burnout3_bmp_p3.exe sha256 6f008b21...)
[PLUGIN bmashup-sdk.host-info] host info: 14 services: bmashup.host 1, takedawn.race 1, bmashup.autopilot 1, ...
[PLUGIN bmashup-sdk.host-info] host info: wants bmashup.events >= 5: offered 5 (ok)
[PLUGIN bmashup-sdk.host-info] host info: wants bmashup.weather >= 1: not offered (missing)
[PLUGIN bmashup-sdk.host-info] host info: offers over: the host says 14, this plugin saw 14
```

What it shows: `bmsdk_host()` / `bmsdk_host_offers(name)` (the whole need list is known at the first offer), the build
identity check against `BMSDK_REFERENCE_BUILD` (the platform version stays the compatibility contract; the identity names
one exact build), `takedawn_plugin_services_done` with `bmsdk_services_done`, and the fallback on older hosts: no
`bmashup.host`, no end-of-offers call - the plugin says so at shutdown, with the SDK's `bmashup.host: missing` line (an
optional need: WARN).

Host values: on `burnout3_bmp_p3.exe` the `build` field is `bmp-0.1.1+b56e33b66dc3` (SDK 0.3.0's reference). On
`burnout3_bmp_p2.exe` it is `bmp-0.1.0+b8710764485c` (SDK 0.2.0's reference; RT launch 55: "= the SDK's reference host");
this 0.3.0 build logs the p2 identity as "not the SDK's reference build" (informational: the platform version decides
compatibility). On `burnout3_bmp_p1.exe` it read `unknown`. The game signature `D0FC2EF4E9B2A86F` is the retail NTSC-U image. The kit's offline test hosts do not set a build,
so there it reads `unknown` and the probe logs the "not the SDK's reference build" line.
Offline evidence: the kit's verification, binding scenarios `hostinfo` (p3 loader), `hostinfo_kit010` (the kit 0.1.0
module on the p3 loader) and `hostinfo_cand2` (the older cand2 loader: the fallback). The SDK 0.3.0 build was not launched.
