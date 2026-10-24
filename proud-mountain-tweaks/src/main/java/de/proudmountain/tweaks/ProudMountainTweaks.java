package de.proudmountain.tweaks;

import de.proudmountain.tweaks.seasons.SeasonCalendar;
import de.proudmountain.tweaks.seasons.SeasonCalendarConfig;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.ModList;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.config.ModConfig;

/**
 * Anpassungen für das Modpack:
 * Serene Seasons folgt dem echten Kalender, siehe SeasonCalendar (Server).
 * Mitgelieferte Resource Packs werden einmal eingeschaltet, siehe DefaultResourcePacks (nur Client).
 * Eisenfarmen laufen trotz Better-Days-Tageslänge den ganzen Tag, siehe VillagerMixin.
 * Außerdem legt neoforge.mods.toml die Ladereihenfolge Farmer's Delight -> Proud Mountain Tweaks -> Coffee Delight fest:
 * Coffee Delight greift beim Registrieren auf Farmer's-Delight-Blöcke zu, gibt die Reihenfolge aber selbst nicht an.
 */
@Mod(ProudMountainTweaks.MOD_ID)
public final class ProudMountainTweaks {
    public static final String MOD_ID = "proudmountain_tweaks";

    public ProudMountainTweaks(IEventBus modBus, ModContainer container) {
        container.registerConfig(ModConfig.Type.COMMON, SeasonCalendarConfig.SPEC);
        // SeasonCalendar greift auf Serene-Seasons-Klassen zu und darf ohne Serene Seasons nicht geladen werden
        if (ModList.get().isLoaded("sereneseasons")) SeasonCalendar.init();
    }
}
