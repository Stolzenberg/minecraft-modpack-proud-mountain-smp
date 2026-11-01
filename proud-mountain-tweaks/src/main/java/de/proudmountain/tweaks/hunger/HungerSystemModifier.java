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
 * Kein Hunger: Der Food-Level bleibt fest auf 17 (unter 18 gibt es keine natürliche Regeneration, sprinten geht, essen bleibt möglich).
 * Essen heilt direkt Lebenspunkte und gibt Buffs, die mit der Komplexität des Gerichts länger halten.
 * Einfaches Essen heilt nur, Buffs gibt es erst bei aufwendigeren Gerichten.
 * Als Essen gilt alles mit der Food-Komponente, also Vanilla und alle Mods ohne Namensraten.
 * Komplexität = Nährwert + Sättigung; dazu zählen Folgeitem (Schüssel) und eingebaute Effekte.
 */
public final class HungerSystemModifier {
    private static final int FIXED_FOOD_LEVEL = 17;

    private static final List<Holder<MobEffect>> BUFFS = List.of(
            MobEffects.DAMAGE_RESISTANCE, MobEffects.DIG_SPEED, MobEffects.MOVEMENT_SPEED);

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
        // Einfaches Essen (Brot, Äpfel, Ofenkartoffel) heilt nur. Steak = 1 Buff, Eintöpfe = 2, Festmahl = 3.
        int tier = score < 14 ? 0 : score < 28 ? 1 : score < 40 ? 2 : 3;
        if (tier == 0) return;

        int duration = (int) Math.min(6000, Math.max(600, score * 100));
        int start = Math.floorMod(stack.getItem().builtInRegistryHolder().key().location().hashCode(), BUFFS.size());
        for (int i = 0; i < tier; i++) {
            Holder<MobEffect> effect = BUFFS.get((start + i) % BUFFS.size());
            player.addEffect(new MobEffectInstance(effect, duration, 0, true, true, true));
        }
    }
}
