package de.proudmountain.tweaks.mixin;

import net.minecraft.world.entity.npc.Villager;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.ModifyConstant;

/**
 * Eisengolems: Ein Villager ruft bei Panik nur dann einen Golem, wenn er vor weniger als 24000 Ticks eingeschlafen
 * ist. In Vanilla ist das ein Tag, mit Better Days (daySpeed/nightSpeed 0.25, config/betterdays-common.toml) dauert
 * ein Tag aber 96000 Ticks. Ohne Anpassung läuft die Frist schon ab, während die Villager noch schlafen, und
 * Eisenfarmen liefern nur kurz nach einer übersprungenen Nacht. Die Frist wird deshalb auf einen ganzen Tag gestreckt.
 */
@Mixin(Villager.class)
public abstract class VillagerMixin {
    private static final long GOLEM_SLEEP_WINDOW = 96000L; // 24000 / 0.25, bei geänderter Tageslänge mit anpassen

    @ModifyConstant(method = "golemSpawnConditionsMet", constant = @Constant(longValue = 24000L))
    private long proudmountain$golemSleepWindow(long window) {
        return GOLEM_SLEEP_WINDOW;
    }
}
