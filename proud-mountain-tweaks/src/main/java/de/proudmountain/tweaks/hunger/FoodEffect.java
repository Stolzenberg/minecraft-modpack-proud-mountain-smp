package de.proudmountain.tweaks.hunger;

import net.neoforged.effector.core.Effect;
import java.util.Objects;

/**
 * Custom effect for health restoration from consuming food.
 * Applies a temporary buff to restore HP when the player consumes food.
 */
public class FoodEffect implements Effect {

    private final int hpRestored;
    private final Duration duration;

    public FoodEffect(int hpRestored, long tickDuration) {
        this.hpRestored = Objects.requireNonNull(hpRestored, "hpRestored must not be null");
        this.duration = Duration.ofTicks(tickDuration);
    }

    @Override
    public boolean hasState() {
        return true;
    }

    @Override
    public void apply(ConsumerEffectConsumer consumer) {
        // Store the HP to restore and duration for tracking
        consumer.set("hpRestored", hpRestored);
        consumer.set("duration", duration.getSeconds());
        consumer.setDuration(duration);
    }

    @Override
    public void update(ConsumerEffectConsumer consumer, ConsumerEntityConsumer entity) {
        // When this effect expires, restore the stored HP to the player's health
        if (entity instanceof PlayerEntity playerEntity) {
            int hpToRestore = (int) entity.get("hpRestored");
            // Restore HP without capping above max - let the game handle overflow
            playerEntity.entityBuff(1000 + hpToRestore);
        }
    }

    @Override
    public void remove(ConsumerEffectConsumer consumer, ConsumerEntityConsumer entity) {
        entity.remove("hpRestored");
        entity.remove("duration");
    }

    public int getHpRestored() {
        return hpRestored;
    }

    public Duration getDuration() {
        return duration;
    }
}
