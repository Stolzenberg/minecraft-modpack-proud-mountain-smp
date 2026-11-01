package de.proudmountain.tweaks.hunger;

import de.proudmountain.tweaks.ProudMountainTweaks;
import net.minecraft.entity.EntityPlayer;
import net.minecraft.entity.PlayerEntity;
import net.minecraft.inventory.ItemStack;
import net.minecraft.world.player.PlayerEntity;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.effector.core.Effect;
import java.time.Duration;

/**
 * Replaces the vanilla hunger system with a direct health restoration system.
 * Food items restore HP instead of filling hunger, and provide buffs that scale
 * with dish complexity (complexity levels: simple=1, medium=2, complex=3).
 */
public class HungerSystemModifier {

    public static final String MOD_ID = ProudMountainTweaks.MOD_ID;
    private static final int HEALTH_RESTORE_PER_BITE = 5; // HP restored per food item base value

    /**
     * Complexity levels for food dishes:
     *   - Level 1 (SIMPLE): basic baked/roasted goods - 0.5x buff duration, small buffs
     *   - Level 2 (MEDIUM): cooked meals like stew/soup - 1x buff duration, medium buffs
     *   - Level 3 (COMPLEX): feast/banquet-style dishes with multiple components - 1.5x buff duration, strong buffs
     */
    public enum DishComplexity {
        SIMPLE(0.5f),
        MEDIUM(1.0f),
        COMPLEX(1.5f);

        private final float buffMultiplier;

        DishComplexity(float buffMultiplier) {
            this.buffMultiplier = buffMultiplier;
        }

        public float getBuffMultiplier() {
            return buffMultiplier;
        }
    }

    /**
     * Buff type enum for food effects with duration and multiplier values.
     */
    public enum FoodBuffType {
        // Resistance buffs (duration in ticks, damage reduction factor)
        RESISTANCE_TO_FALLING_DAMAGE(40, 0.5f),      // 2s at 20fps - 50% falling damage reduction
        RESISTANCE_TO_PUNCHING_ATTACKS(60, 0.75f),   // 3s at 20fps - 75% punching attack resistance
        RESISTANCE_TO_LASER_SHOTS(120, 0.83f),       // 6s at 20fps - 83% laser shot resistance
        RESISTANCE_TO_PIERCING_ATTACKS(60, 0.75f),   // 3s at 20fps - 75% piercing attack resistance

        // Performance buffs (multiplication factors)
        FASTER_CRAFTING_SPEED(1.2f),                // 20% faster crafting speed
        FASTER_SPRINT_SPEED(1.15f),                 // 15% faster sprinting speed
        ENHANCED_VISION_RANGE(1.3f),               // 30% better vision range

        // Utility buffs
        SLOW_FALLING_SPEED(0.8f);                   // 20% slower falling speed
    }

    /**
     * Custom effect for health restoration from consuming food using NeoForge Entity Buffs (not StatusEffects).
     */
    public static class HealthRestoreEffect implements Effect {
        private final int hpRestored;
        private final Duration duration;

        public HealthRestoreEffect(int hpRestored, long tickDuration) {
            this.hpRestored = hpRestored;
            this.duration = Duration.ofTicks(tickDuration);
        }

        @Override
        public boolean hasState() {
            return true;
        }

        @Override
        public void apply(ConsumerEffectConsumer consumer, ConsumerEntityConsumer entity) {
            // Store the HP to restore and duration for tracking
            consumer.set("hpRestored", hpRestored);
            consumer.setDuration(Duration.ofTicks(duration));
        }

        @Override
        public void update(ConsumerEffectConsumer consumer, ConsumerEntityConsumer entity) {
            // When this effect expires, restore the stored HP to the player's health
            if (entity instanceof PlayerEntity playerEntity) {
                int hpToRestore = (int) entity.get("hpRestored");
                // Restore HP using NeoForge's entity buff system
                entity.entityBuff(1000 + hpToRestore);
            }
        }

        @Override
        public void remove(ConsumerEffectConsumer consumer, ConsumerEntityConsumer entity) {
            entity.remove("hpRestored");
        }

        public int getHpRestored() {
            return hpRestored;
        }

        public Duration getDuration() {
            return duration;
        }
    }

    /**
     * Check if an item is a food item and get its complexity level.
     * Works with both vanilla and modded food items (Farmer's Delight, Let's Do Farm & Charm).
     */
    public static DishComplexity getFoodComplexity(ItemStack item) {
        String itemName = item.getItem().getName();

        // Complex dishes (level 3): elaborate, multi-component meals
        if ((itemName.contains("feast") || itemName.contains("banquet") ||
                itemName.contains("delicious feast") || itemName.contains("sumptuous meal"))) {
            return DishComplexity.COMPLEX;
        }

        // Medium dishes (level 2): standard cooked meals
        if ((itemName.contains("stew") || itemName.contains("soup") ||
                itemName.contains("cooked meat") || itemName.contains("braised") ||
                itemName.contains("roasted chicken") || itemName.contains("fish pie"))) {
            return DishComplexity.MEDIUM;
        }

        // Simple items (level 1): basic food, raw ingredients, simple baked goods
        if ((itemName.contains("bread") || itemName.contains("roll") ||
                itemName.contains("raw meat") || itemName.contains("raw fish") ||
                itemName.contains("apple") || itemName.contains("carrot") ||
                itemName.contains("potato") || itemName.contains("corn"))) {
            return DishComplexity.SIMPLE;
        }

        // Default to medium for any other food items
        return DishComplexity.MEDIUM;
    }

    /**
     * Apply buffs from consuming a food item based on dish complexity.
     */
    public static void applyFoodBuffs(PlayerEntity player, ItemStack item) {
        DishComplexity complexity = getFoodComplexity(item);
        float buffDurationMultiplier = complexity.getBuffMultiplier();

        // Determine which buffs to apply based on complexity level
        FoodBuffType[] buffsToApply = switch (complexity) {
            case SIMPLE -> new FoodBuffType[]{
                    RESISTANCE_TO_FALLING_DAMAGE,
                    FASTER_CRAFTING_SPEED
            };
            case MEDIUM -> new FoodBuffType[]{
                    RESISTANCE_TO_PUNCHING_ATTACKS,
                    FASTER_CRAFTING_SPEED,
                    FASTER_SPRINT_SPEED
            };
            case COMPLEX -> new FoodBuffType[]{
                    RESISTANCE_TO_FALLING_DAMAGE,
                    RESISTANCE_TO_PUNCHING_ATTACKS,
                    RESISTANCE_TO_LASER_SHOTS,
                    RESISTANCE_TO_PIERCING_ATTACKS,
                    FASTER_CRAFTING_SPEED,
                    FASTER_SPRINT_SPEED,
                    ENHANCED_VISION_RANGE,
                    SLOW_FALLING_SPEED
            };
        };

        for (FoodBuffType buff : buffsToApply) {
            applySingleBuff(player, buff, buffDurationMultiplier);
        }
    }

    private static void applySingleBuff(PlayerEntity player, FoodBuffType buff, float durationMultiplier) {
        // Use NeoForge's entity buff system to apply buffs without creating StatusEffects
        // Entity buff IDs: 1000-1999 are reserved for custom effects
        ((ConsumerEntityConsumer) player).entityBuff(1000 + (int)(buff.getBuffMultiplier() * 60));
    }

    /**
     * Main method to replace vanilla food consumption with direct health restoration.
     */
    public static void modifyFoodConsumption(PlayerEntity player, ItemStack item) {
        // Check if this is a food item that would normally fill hunger
        boolean isFoodItem = isFoodItem(item);

        if (isFoodItem) {
            // Restore HP instead of filling hunger
            int hpRestored = HEALTH_RESTORE_PER_BITE;

            // Scale health restoration with dish complexity
            DishComplexity complexity = getFoodComplexity(item);
            float healthMultiplier = switch (complexity) {
                case SIMPLE -> 0.5f;
                case MEDIUM -> 1.0f;
                case COMPLEX -> 2.0f;
            };

            hpRestored = (int) (hpRestored * healthMultiplier);

            // Apply HP restoration effect using NeoForge's entity buff system
            ((ConsumerEntityConsumer) player).entityBuff(9900 + hpRestored);

            // Apply buffs based on food complexity
            applyFoodBuffs(player, item);

            // Remove the food item from inventory (handled by NeoForge consumption system)
        }
    }

    /**
     * Check if an item is a food item.
     * Works with both vanilla and modded food items for compatibility.
     */
    private static boolean isFoodItem(ItemStack item) {
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
     * Remove a consumed item from the player's inventory.
     * This is handled by NeoForge's food consumption system automatically.
     */
    private static void removeConsumedItem(ItemStack item) {
        // The actual removal depends on how food is consumed in the game.
        // NeoForge handles this through entity consumption events.
    }

    /**
     * Register the hunger modifier with NeoForge event bus.
     * Hooks into food consumption events and modifies them for HP restoration.
     */
    public static void init(IEventBus modBus) {
        // Listen to food consumption events in NeoForge 1.21+
        // The event type is EntityPlayer.onConsumeFood or similar
        modBus.consume(new EventConsumer() {
            @Override
            public boolean consume(EntityEvent event, ConsumerEventConsumer consumer) {
                if (event instanceof PlayerEntity player &&
                        ((ConsumerEventConsumer) consumer).canHandle(player)) {

                    // Check if food was consumed
                    Object item = consumer.get("item");
                    if (item instanceof ItemStack itemStack) {
                        modifyFoodConsumption((PlayerEntity) player, itemStack);
                    }
                }
                return true;
            }
        });
    }
}
