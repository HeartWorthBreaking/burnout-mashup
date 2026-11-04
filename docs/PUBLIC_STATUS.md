# PUBLIC_STATUS - open questions and decisions (summary of the project's question matrix)

This page is an engineering and project record. **It is not legal advice and not a legal clearance.** "Decided" means the
project's maintainers made a project decision; it does not answer a legal question. "Unresolved" needs the rights holder,
counsel or upstream; a decision of the project does not close it.

| Q | topic | project decision | state |
|---|---|---|---|
| Q1 | distribution of game code | no host exe, translated objects, generated files, retail assets or retail-derived output in the public tree or its history; no prebuilt | implemented for this source tree; for any binary: **unresolved** |
| Q2 | LGPL route with statically linked game code | document linkage, licences and the change notice; no claim that this resolves anything | documented (`NOTICE.md`); binary: **unresolved** |
| Q3 | licences and copyright | MIT code / SDK / tools; CC-BY-4.0 own documentation; CC0-1.0 own example assets where the authority exists; upstream and third-party licences preserved; copyright stays with the authors; DCO for future contributions | decided; the copyright line wording (D1) awaits the owner's confirmation |
| Q4 | the name "Burnout Mashup" | keep the working name with non-affiliation wording and original artwork; own application / folder / window / update identity; saves preserved, migration explicit and optional | disclaimers in place; **trademark clearance unresolved** |
| Q5 | relationship to upstream Takedawn | credit and link upstream; "independently maintained fork, not an endorsed upstream release"; `takedawn_*` headers and ABI kept with attribution; update action off | implemented; upstream's informal view is a courtesy question, not a licence condition; **unresolved** as a courtesy |
| Q6 | LGPL section 6 vs the game code | stays open | **unresolved** (binary only) |
| Q7 | local recompilation | a technical distribution model (you build from your own copy), not a legal conclusion | **legality unresolved** |
| Q8 | reverse-engineering notes and hand-edited generated lines | hooks as address anchors + own text; no generated code published; provenance kept visible; the RE research notes are held back | **unresolved** (counsel) |
| Q9 | outputs built from retail data | local only; the tools say so | implemented in tool texts; exchange of derived outputs **unresolved** |

Defaults chosen while assembling (to be confirmed by the owner): D1 copyright line wording; D2 research notes excluded; D3 icon CC0 (the earlier icon; since 0.2.0-alpha.3 the icon is project artwork, `LICENSES/LicenseRef-BurnoutMashup-Artwork.txt`);
D4 names BurnoutMashup / Burnout Mashup; D5 update check off; D6 migration by the copy-only tool; D7 hook marks in the macro form;
D8 the three generated test fixtures excluded; D9 ps2look included as a tool (no outputs); D10 game-container demo files excluded;
D11 Windows-only scope; D12 no courtesy message to upstream has been sent.
