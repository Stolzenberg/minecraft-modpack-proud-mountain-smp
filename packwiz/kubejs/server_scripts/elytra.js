// Keine Elytren auf dem Server: weder im End noch sonst wo zu finden, nicht herstellbar.
//
// Loot, Item-Frames in Strukturen und Inventare räumt Proud Mountain Tweaks (BannedItems) über den Item-Tag
// proudmountain_tweaks:banned ab, Lootr übernimmt die Frames nicht (config/lootr-common.toml und Item-Tag
// lootr:convert/item_frame_blacklist). Vanilla hat kein Elytra-Rezept, hier fällt jedes weg, das eine Mod mitbringt.
// Ausgeblendet in JEI per Tag (kubejs/data/c/tags/item/hidden_from_recipe_viewers.json).

ServerEvents.recipes((event) => {
  event.remove({ output: '#proudmountain_tweaks:banned' })
})
