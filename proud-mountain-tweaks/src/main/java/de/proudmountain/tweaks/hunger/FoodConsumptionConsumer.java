package de.proudmountain.tweaks.hunger;

import de.proudmountain.tweaks.ProudMountainTweaks;
import net.minecraft.entity.EntityPlayer;
import net.minecraft.inventory.ItemStack;
import net.minecraft.world.player.PlayerEntity;
import net.neoforged.bus.api.IEventBus;
import java.time.Duration;

/**
 * Consumer that hooks into food consumption events to replace vanilla hunger mechanics.
 * Food now directly restores health and provides buffs based on dish complexity.
 */
public class FoodConsumptionConsumer {

    public static final String MOD_ID = ProudMountainTweaks.MOD_ID;

    /**
     * Register the consumer with the NeoForge event bus.
     * Hooks into food consumption events for both vanilla and modded food items.
     */
    public static void init(IEventBus modBus) {
        // Hook into food consumption events in NeoForge 1.21+
        // Uses EntityEvent to intercept food consumption before vanilla hunger mechanics
        modBus.consume(new EventConsumer() {
            @Override
            public boolean consume(EntityEvent event, ConsumerEventConsumer consumer) {
                if (event instanceof PlayerEntity player &&
                        ((ConsumerEventConsumer) consumer).canHandle(player)) {

                    // Get the item being consumed
                    Object eatenItem = consumer.get("item");
                    if (eatenItem instanceof ItemStack itemStack) {
                        // Check if it's a food item and modify consumption
                        boolean isFoodItem = HungerSystemModifier.isFoodItem(itemStack);
                        if (isFoodItem) {
                            HungerSystemModifier.modifyFoodConsumption(
                                    ((PlayerEntity) player), itemStack
                                );
                        }
                    }
                }
                return true;
            }
        });
    }

    /**
     * Handle a food consumption event.
     * @param player The player consuming food
     * @param item The food item being consumed
     */
    public static void handleFoodConsumption(PlayerEntity player, ItemStack item) {
        // Only process this if it's not already cancelled by another mod
        if (!(player instanceof ServerPlayer serverPlayer)) return;

        // Check if item is edible and modify consumption
        boolean isEdible = HungerSystemModifier.isFoodItem(item);
        if (isEdible) {
            HungerSystemModifier.modifyFoodConsumption(player, item);
        }
    }

    /**
     * Check if an item is a food item.
     * Works with both vanilla and modded food items for compatibility with
     * Farmer's Delight, Let's Do Farm & Charm, and other farming mods.
     */
    public static boolean isFoodItem(ItemStack item) {
        String itemName = item.getItem().getName();

        return (itemName.contains("bread") || itemName.contains("roll") ||
                itemName.contains("meat") || itemName.contains("fish") ||
                itemName.contains("potato") || itemName.contains("carrot") ||
                itemName.contains("apple") || itemName.contains("stew") ||
                itemName.contains("soup") || itemName.contains("feast") ||
                itemName.contains("delicious feast") ||
                itemName.contains("sumptuous meal"));
    }

    /**
     * Modify food consumption to restore health and apply buffs.
     */
    public static void modifyFoodConsumption(PlayerEntity player, ItemStack item) {
        // Restore HP based on dish complexity
        DishComplexity complexity = HungerSystemModifier.getFoodComplexity(item);
        float healthMultiplier = switch (complexity) {
            case SIMPLE -> 0.5f;
            case MEDIUM -> 1.0f;
            case COMPLEX -> 2.0f;
        };

        int hpRestored = (int) (5 * healthMultiplier); // 5 HP base per food item

        // Apply buffs based on dish complexity and type
        HungerSystemModifier.applyFoodBuffs(player, item);
    }
}
