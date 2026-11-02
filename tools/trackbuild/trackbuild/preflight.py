"""trackbuild.preflight - 0.2.0 input checks that run BEFORE the build, so that unsupported input is refused with a reason
that names the feature and the supported alternative (0.1.6 accepted some of it silently: unknown material keys were
ignored, transparent PNG alpha was dropped). A valid description passes unchanged: the build bytes do not depend on it."""
import os

from .io import SourceError, need, read_png_alpha

MATERIAL_KEYS = {"texture": "PNG path relative to the source folder", "surface": "retail collision word, e.g. \"0x0001\"",
                 "collide": "true = the faces are collision", "car_solid": "false only for non-solid back faces",
                 "retail_material": "0.3.2: {track, material, static_sha256} - copy a retail material + textures verbatim "
                                    "(cut-outs / blended; LOCAL ONLY); 'texture' is then only the editor preview"}
UNSUPPORTED_MATERIAL = {"alpha", "alpha_test", "blend", "additive", "transparent", "opacity", "shader", "type", "flags",
                        "animated", "animation", "uv_scroll", "reflection", "specular", "normal_map", "emissive", "water",
                        "decal", "textures", "lightmap"}
MAX_ROWS = 83


def check_desc(src_dir, desc):
    mats = desc["materials"]
    need(isinstance(mats, dict) and mats, "'materials' must be a non-empty object {name: {texture, surface, collide}}")
    rows = desc["rows"]
    need(isinstance(rows, list) and rows, "'rows' must list the materials in render order")
    if len(rows) > MAX_ROWS:
        from .capacity import rows_note
        need(False, "%d material rows; a unit block holds at most %d in the game's per-block material table (every centre block "
             "lists one entry per row for itself and its 16 PVS neighbours). %s. Capacity \"auto\" does not change this limit."
             % (len(rows), MAX_ROWS, rows_note(len(rows))))
    from .capacity import mode_of
    mode_of(desc)                                                # 0.3.4: "capacity" must be "auto" (default) or "game"
    for r in rows:
        need(r in mats, "row %r is not a described material" % r)
    need(isinstance(desc["obj"], str) and os.path.isfile(os.path.join(src_dir, desc["obj"])),
         "the OBJ %s named by the description is not in %s" % (desc["obj"], src_dir))
    if desc.get("retail_objects") is not None:                  # 0.3.2: verbatim retail instance models / props
        from .retailobj import check_entries
        check_entries(desc["retail_objects"])
    alpha_of = {}
    for name, m in mats.items():
        need(isinstance(m, dict), "material %s must be an object" % name)
        unk = sorted(set(m) - set(MATERIAL_KEYS))
        if unk:
            feat = [k for k in unk if k in UNSUPPORTED_MATERIAL]
            raise SourceError("material %s: %s %s not supported by trackbuild (PNG materials are opaque, one DXT1 texture, retail "
                              "type 0 / flags 0; no alpha / additive / animated / reflective PNG materials; 0.3.2: see-through "
                              "looks come from a retail material copied verbatim with retail_material). Supported keys: %s."
                              % (name, ", ".join(unk), "is" if len(unk) == 1 else "are",
                                 "; ".join("%s (%s)" % kv for kv in MATERIAL_KEYS.items()))
                              + (" Remove %s and bake the look into the texture / vertex colours." % ", ".join(feat) if feat else ""))
        if "retail_material" in m:                               # 0.3.2: verbatim retail material (trackbuild.retailmat)
            from .retailmat import check_spec
            check_spec(name, m["retail_material"])
        else:
            need(isinstance(m.get("texture"), str) and m["texture"], "material %s: 'texture' (a PNG path) is required" % name)
        need(isinstance(m.get("surface"), str), "material %s: 'surface' must be a hex string such as \"0x0001\"" % name)
        try:
            w = int(m["surface"], 16)
        except ValueError:
            raise SourceError("material %s: surface %r is not a hex word such as \"0x0001\" (tarmac)" % (name, m["surface"]))
        need(0 <= w <= 0xFFFF, "material %s: surface 0x%X does not fit 16 bits" % (name, w))
        if name not in rows or "retail_material" in m:          # only rendered PNG materials have their texture read
            continue
        tp = os.path.join(src_dir, m["texture"])
        need(os.path.isfile(tp), "material %s: texture %s not found (paths are relative to the source folder %s)"
             % (name, m["texture"], src_dir))
        need(m["texture"].lower().endswith(".png"), "material %s: texture %s is not a .png (8-bit RGB / RGBA PNG only)" % (name, m["texture"]))
        if tp not in alpha_of:
            alpha_of[tp] = read_png_alpha(tp)[3]
        need(alpha_of[tp] == 255, "material %s: texture %s has transparent pixels (alpha down to %d); trackbuild 0.2 writes opaque DXT1 "
             "only, so transparency would be lost. Make the texture opaque (or RGB)." % (name, m["texture"], alpha_of[tp]))
