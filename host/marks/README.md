# host/marks - hook marks as address anchors ("bm-anchors 1")

`anchors.json` holds, for each of the 512 marks: the guest address of the generated function, the anchor (a label or function
address and the sha256 of its line), the sha256 of every generated line the mark deletes, the sha256 of the neighbouring
lines, and **our own inserted text**. It contains no generated code. It is a representation of the Mashup's changes to the
user's locally generated code (the xboxrecomp output of the user's own game) and does **not** decide any copyright question.
`include/bm_gen_access.h` holds the accessor macros the inserted text uses (MIT; force-included through the build's
`BO3_GEN_OPT` list). `tools/anchors.py` emits / applies / checks the marks and refuses on any mismatch (exit 2, nothing written);
`tools/bm_rewrite.py` and `tools/demacro.py` are the rewrite rules and the token-equivalence proof.

Proofs and counts of the private workspace: the macro form expands to the identical tokens; the generated objects of the build
are byte-identical to the original form; the raw exe differs only by the identity text and the linker's build id. Marks that
stay in the original text form: m475, m511, m512 (not compiled by default builds).
