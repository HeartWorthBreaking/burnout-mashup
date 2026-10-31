# Security

## Native plugins are native code
A Burnout Mashup plugin is a native module (a DLL loaded into the game process). It runs with **your user's rights** and can
do anything your account can. The host therefore starts a plugin only after you **approved that exact file**: approvals are
bound to the plugin's **sha256** (a changed file is "not approved" until you approve it again) and are stored in
`%APPDATA%\BurnoutMashup\plugin-approvals.toml` (override: `BMASHUP_PLUGIN_APPROVALS`). The approvals of a separate Takedawn
install are never read or changed; the `tools/migrate` tool can copy them on request (it states what that grants).
Only approve plugins whose source you have read or whose author you trust. Data-only mods contain no code.

## Tools
The tools read your game data and write only into folders you name. Their outputs from your game stay on your PC.

## Reporting a vulnerability
Open a private security advisory on the repository (preferred) or an issue that does not contain exploit details, and say
which component is affected. Do not send game files. Issues of upstream Takedawn go to the upstream project.
