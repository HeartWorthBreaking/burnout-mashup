/* SPDX-License-Identifier: MIT
 * bm_gen_access.h - Burnout Mashup: the accessor macros our hook marks use inside the user's locally generated code.
 *
 * The marks (bm-anchors 1, marks/anchors.json) insert OUR text into the C files that the user's own xboxrecomp run generates
 * from the user's own game disc. The generated code addresses guest memory and the guest stack through the toolkit's
 * recomp_types.h (MEM8 / MEM16 / MEM32 / MEMF, PUSH32, RECOMP_ABI_CALL, g_ebp / g_seh_ebp). Our inserted lines call the
 * macros below instead of spelling those accesses out, so the mark file carries calls of ours, not statements in the
 * generated code's shape.
 *
 * Contract (checked by marks/tools/eqcheck.py with clang -E): every macro expands to EXACTLY the token sequence the mark
 * used before (no extra parentheses, no reordering), so the preprocessed translation unit and the compiled objects stay
 * identical. That is why the statement macros are unhygienic: arguments are pasted as written, and BM_GUEST_CALL /
 * BM_GUEST_RET / BM_CMP32 expand to two statements; each is used only as a full statement, followed by ';'.
 *
 * Force-included into the generated sources (BO3_GEN_OPT, -include), like the bo3_*_gen.h headers. The names it uses
 * (MEM32, esp, ebp, _fa, _fb, ...) are resolved at the point of use, inside a generated function.
 * This file is a representation choice for our own insertions; it does not decide any copyright question.
 */
#ifndef BM_GEN_ACCESS_H
#define BM_GEN_ACCESS_H

/* guest memory: read as a value */
#define BM_RD8(a) MEM8(a)
#define BM_RD16(a) MEM16(a)
#define BM_RD32(a) MEM32(a)
#define BM_RDF(a) MEMF(a)

/* guest memory: load into a guest register (statement) */
#define BM_LD8(r, a) r = MEM8(a)
#define BM_LD16(r, a) r = MEM16(a)
#define BM_LD32(r, a) r = MEM32(a)
#define BM_LDF(r, a) r = MEMF(a)

/* guest memory: store (statement) */
#define BM_ST8(a, v) MEM8(a) = v
#define BM_ST16(a, v) MEM16(a) = v
#define BM_ST32(a, v) MEM32(a) = v
#define BM_STF(a, v) MEMF(a) = v

/* guest stack and calls */
#define BM_PUSH(v) PUSH32(esp, v)
#define BM_GUEST_CALL(r, a, f) PUSH32(esp, r); RECOMP_ABI_CALL(a, f)   /* push the return address r, call guest function f at a */
#define BM_GUEST_RET(n) esp += n; return                                  /* return from the guest function, popping n bytes */
#define BM_ESP_ADD(n) esp = esp + n                                       /* drop n bytes of guest stack */

/* guest frame published for host code that calls back into the game */
#define BM_FRAME_EBP() g_ebp = ebp
#define BM_FRAME_SEH() g_seh_ebp = ebp

/* 32-bit compare operands for the flag helpers that follow (CMP_EQ / CMP_* of recomp_types.h) */
#define BM_CMP32(x, y) _fa = (uint32_t)(x) & 0xFFFFFFFFu; _fb = (uint32_t)(y) & 0xFFFFFFFFu

#endif /* BM_GEN_ACCESS_H */
