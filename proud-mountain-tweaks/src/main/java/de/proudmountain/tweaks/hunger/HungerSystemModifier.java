package de.proudmountain.tweaks.hunger;

import com.mojang.brigadier.Command;
import net.minecraft.commands.Commands;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.food.FoodData;
import net.minecraft.world.food.FoodProperties;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.entity.living.LivingEntityUseItemEvent;
import net.neoforged.neoforge.event.server.ServerAboutToStartEvent;
import net.neoforged.neoforge.event.tick.PlayerTickEvent;

/**
 * Kein Hunger: Der Food-Level bleibt fest auf 17 (unter 18 gibt es keine natürliche Regeneration,
 * sprinten geht, essen bleibt möglich). Essen heilt direkt Lebenspunkte in Höhe des Nährwerts
 * (mal heal_multiplier). Buffs gibt es nur für Gerichte, die in food_buffs.json eingetragen sind,
 * siehe FoodBuffConfig. Als Essen gilt alles mit der Food-Komponente, also Vanilla und alle Mods.
 */
public final class HungerSystemModifier {
    private static final int FIXED_FOOD_LEVEL = 17;

    private HungerSystemModifier() {
    }

    public static void init() {
        NeoForge.EVENT_BUS.addListener(PlayerTickEvent.Post.class, HungerSystemModifier::onPlayerTick);
        NeoForge.EVENT_BUS.addListener(LivingEntityUseItemEvent.Finish.class, HungerSystemModifier::onEaten);
        NeoForge.EVENT_BUS.addListener(ServerAboutToStartEvent.class, event -> FoodBuffConfig.load());
        NeoForge.EVENT_BUS.addListener(RegisterCommandsEvent.class, event -> event.getDispatcher().register(
                Commands.literal("foodbuffs").requires(s -> s.hasPermission(2))
                        .then(Commands.literal("reload").executes(ctx -> {
                            int n = FoodBuffConfig.load();
                            ctx.getSource().sendSuccess(() -> Component.literal(n < 0
                                    ? "food_buffs.json nicht lesbar, siehe Log"
                                    : "food_buffs.json geladen: " + n + " Gerichte mit Buffs"), true);
                            return Command.SINGLE_SUCCESS;
                        }))));
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

        player.heal(food.nutrition() * FoodBuffConfig.healMultiplier());
        for (MobEffectInstance effect : FoodBuffConfig.effectsFor(BuiltInRegistries.ITEM.getKey(stack.getItem()))) {
            player.addEffect(effect);
        }
    }
}
