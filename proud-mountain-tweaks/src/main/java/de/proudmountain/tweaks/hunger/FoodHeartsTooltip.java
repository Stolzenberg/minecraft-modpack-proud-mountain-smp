package de.proudmountain.tweaks.hunger;

import net.minecraft.ChatFormatting;
import net.minecraft.core.component.DataComponents;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.world.food.FoodProperties;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.entity.player.ItemTooltipEvent;

/** Zeigt im Tooltip von Essen die Herzen, die es heilt, statt Hungerkeulen (nur Client, nur über diese Klasse laden). */
public final class FoodHeartsTooltip {
    private static boolean configLoaded;

    private FoodHeartsTooltip() {
    }

    public static void init() {
        NeoForge.EVENT_BUS.addListener(ItemTooltipEvent.class, FoodHeartsTooltip::onTooltip);
    }

    private static void onTooltip(ItemTooltipEvent event) {
        FoodProperties food = event.getItemStack().get(DataComponents.FOOD);
        if (food == null) return;
        if (!configLoaded) {
            // heal_multiplier liegt im Pack-Config-Ordner, der Client liest ihn wie der Server
            configLoaded = true;
            FoodBuffConfig.load();
        }
        float hp = food.nutrition() * FoodBuffConfig.healMultiplier();
        int halves = Math.round(hp);
        if (halves <= 0) return;

        MutableComponent line = Component.empty();
        int full = halves / 2;
        if (full > 0) line.append(Component.literal("❤".repeat(Math.min(full, 10))).withStyle(ChatFormatting.RED));
        if (full > 10) line.append(Component.literal(" x" + full).withStyle(ChatFormatting.RED));
        if (halves % 2 == 1) line.append(Component.literal(full > 0 ? " ½" : "½").withStyle(ChatFormatting.RED));
        event.getToolTip().add(line);
    }
}
