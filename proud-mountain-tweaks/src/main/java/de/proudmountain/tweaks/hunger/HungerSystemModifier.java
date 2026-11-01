package de.proudmountain.tweaks.hunger;

import net.minecraft.core.Holder;
import net.minecraft.core.component.DataComponents;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.food.FoodData;
import net.minecraft.world.food.FoodProperties;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.entity.living.LivingEntityUseItemEvent;
import net.neoforged.neoforge.event.tick.PlayerTickEvent;

import java.util.List;

/**
 * Kein Hunger: Der Food-Level bleibt fest auf 19 (sprinten geht, essen bleibt möglich).
 * Essen heilt direkt Lebenspunkte und gibt Buffs, die mit der Komplexität des Gerichts länger halten.
 * Als Essen gilt alles mit der Food-Komponente, also Vanilla und alle Mods ohne Namensraten.
 * Komplexität = Nährwert + Sättigung; dazu zählen Folgeitem (Schüssel) und eingebaute Effekte.
 */
public final class HungerSystemModifier {
    private static final int FIXED_FOOD_LEVEL = 19;

    private static final List<Holder<MobEffect>> BUFFS = List.of(
            MobEffects.DAMAGE_RESISTANCE, MobEffects.DIG_SPEED, MobEffects.MOVEMENT_SPEED,
            MobEffects.SLOW_FALLING, MobEffects.NIGHT_VISION, MobEffects.JUMP, MobEffects.DAMAGE_BOOST);

    private HungerSystemModifier() {
    }

    public static void init() {
        NeoForge.EVENT_BUS.addListener(PlayerTickEvent.Post.class, HungerSystemModifier::onPlayerTick);
        NeoForge.EVENT_BUS.addListener(LivingEntityUseItemEvent.Finish.class, HungerSystemModifier::onEaten);
    }

    private static void onPlayerTick(PlayerTickEvent.Post event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;
        FoodData food = player.getFoodData();
        food.setFoodLevel(FIXED_FOOD_LEVEL);
        food.setSaturation(0f);
        food.setExhaustion(0f);
    }

    private static void onEaten(LivingEntityUseItemEvent.Finish event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;
        ItemStack stack = event.getItem();
        FoodProperties food = stack.get(DataComponents.FOOD);
        if (food == null) return;

        player.heal(food.nutrition());

        float score = food.nutrition() + food.saturation();
        if (food.usingConvertsTo().isPresent()) score += 3;
        score += food.effects().size() * 2;
        int tier = score < 8 ? 1 : score < 16 ? 2 : 3;
        if (score < 2) return;

        int duration = (int) Math.min(12000, Math.max(600, score * 200));
        int start = Math.floorMod(stack.getItem().builtInRegistryHolder().key().location().hashCode(), BUFFS.size());
        for (int i = 0; i < tier; i++) {
            Holder<MobEffect> effect = BUFFS.get((start + i) % BUFFS.size());
            int amplifier = tier == 3 && i == 0 ? 1 : 0;
            player.addEffect(new MobEffectInstance(effect, duration, amplifier, true, true, true));
        }
    }
}
