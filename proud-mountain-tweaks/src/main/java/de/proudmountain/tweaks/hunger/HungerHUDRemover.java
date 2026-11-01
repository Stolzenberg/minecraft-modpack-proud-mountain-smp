package de.proudmountain.tweaks.hunger;

import net.neoforged.neoforge.client.event.RenderGuiLayerEvent;
import net.neoforged.neoforge.client.gui.VanillaGuiLayers;
import net.neoforged.neoforge.common.NeoForge;

/** Blendet die Hungerleiste aus (nur Client, nur über diese Klasse laden). */
public final class HungerHUDRemover {
    private HungerHUDRemover() {
    }

    public static void init() {
        NeoForge.EVENT_BUS.addListener(RenderGuiLayerEvent.Pre.class, event -> {
            if (event.getName().equals(VanillaGuiLayers.FOOD_LEVEL)) event.setCanceled(true);
        });
    }
}
