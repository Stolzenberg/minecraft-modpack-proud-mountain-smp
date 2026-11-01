package de.proudmountain.tweaks.hunger;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.logging.LogUtils;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffectInstance;
import net.neoforged.fml.loading.FMLPaths;
import org.slf4j.Logger;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;

/**
 * config/proudmountain_tweaks/food_buffs.json: welches Essen welche Buffs gibt.
 * Format: {"heal_multiplier": 1.0, "foods": {"minecraft:cooked_beef": [{"effect": "minecraft:resistance", "seconds": 90, "amplifier": 0}]}}
 * Gerichte, die nicht eingetragen sind, heilen nur.
 */
public final class FoodBuffConfig {
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final String FILE = "proudmountain_tweaks/food_buffs.json";

    private record Buff(Holder<MobEffect> effect, int ticks, int amplifier) {
    }

    private static volatile Map<ResourceLocation, List<Buff>> foods = Map.of();
    private static volatile float healMultiplier = 1f;

    private FoodBuffConfig() {
    }

    public static float healMultiplier() {
        return healMultiplier;
    }

    /** Neue Instanzen der Effekte für dieses Item (leer, wenn nicht eingetragen). */
    public static List<MobEffectInstance> effectsFor(ResourceLocation item) {
        List<Buff> buffs = foods.get(item);
        if (buffs == null) return List.of();
        List<MobEffectInstance> result = new ArrayList<>();
        for (Buff b : buffs) result.add(new MobEffectInstance(b.effect, b.ticks, b.amplifier, true, true, true));
        return result;
    }

    /** Liest die Datei neu ein und liefert die Zahl der Einträge (-1 bei Fehler, der alte Stand bleibt dann). */
    public static int load() {
        Path path = FMLPaths.CONFIGDIR.get().resolve(FILE);
        if (!Files.exists(path)) {
            LOGGER.warn("{} fehlt, Essen heilt nur ohne Buffs", path);
            foods = Map.of();
            return 0;
        }
        try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            JsonObject root = JsonParser.parseReader(reader).getAsJsonObject();
            float multiplier = root.has("heal_multiplier") ? root.get("heal_multiplier").getAsFloat() : 1f;
            Map<ResourceLocation, List<Buff>> parsed = new HashMap<>();
            for (Map.Entry<String, JsonElement> entry : root.getAsJsonObject("foods").entrySet()) {
                ResourceLocation item = ResourceLocation.tryParse(entry.getKey());
                if (item == null || !BuiltInRegistries.ITEM.containsKey(item)) {
                    LOGGER.warn("food_buffs.json: Item {} gibt es nicht", entry.getKey());
                    continue;
                }
                List<Buff> buffs = new ArrayList<>();
                JsonArray array = entry.getValue().getAsJsonArray();
                for (JsonElement e : array) {
                    JsonObject o = e.getAsJsonObject();
                    ResourceLocation id = ResourceLocation.tryParse(o.get("effect").getAsString());
                    Holder<MobEffect> effect = id == null ? null : BuiltInRegistries.MOB_EFFECT.getHolder(id).orElse(null);
                    if (effect == null) {
                        LOGGER.warn("food_buffs.json: Effekt {} bei {} gibt es nicht", o.get("effect").getAsString(), entry.getKey());
                        continue;
                    }
                    int seconds = o.get("seconds").getAsInt();
                    int amplifier = o.has("amplifier") ? o.get("amplifier").getAsInt() : 0;
                    buffs.add(new Buff(effect, seconds * 20, amplifier));
                }
                if (!buffs.isEmpty()) parsed.put(item, buffs);
            }
            foods = parsed;
            healMultiplier = multiplier;
            LOGGER.info("food_buffs.json: {} Gerichte mit Buffs", parsed.size());
            return parsed.size();
        } catch (IOException | RuntimeException e) {
            LOGGER.error("food_buffs.json nicht lesbar, behalte den alten Stand", e);
            return -1;
        }
    }
}
