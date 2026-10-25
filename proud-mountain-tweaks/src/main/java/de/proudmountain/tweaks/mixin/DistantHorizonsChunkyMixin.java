package de.proudmountain.tweaks.mixin;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Distant Horizons 3.3.3 meldet sich beim ersten geladenen Chunk bei Chunky an (pausiert dann seine eigene
 * Weltgenerierung, solange Chunky vorgeneriert). Die Spawn-Chunks laden aber, bevor Chunky beim Serverstart
 * initialisiert ist: ChunkyProvider.get() wirft "Chunky is not loaded." und der Serverstart bricht ab.
 * Die Anmeldung wird deshalb übersprungen, bis Chunky bereit ist, und beim nächsten Chunk erneut versucht.
 */
@Pseudo
@Mixin(targets = "com.seibel.distanthorizons.core.wrapperInterfaces.modAccessor.AbstractChunkyAccessor", remap = false)
public abstract class DistantHorizonsChunkyMixin {
    @Shadow
    private boolean listenerBound;

    @Inject(method = "tryRunFirstTimeSetup", at = @At("HEAD"), cancellable = true)
    private void proudmountain$waitForChunky(CallbackInfo ci) {
        if (!listenerBound && !proudmountain$chunkyLoaded()) {
            ci.cancel();
        }
    }

    private static boolean proudmountain$chunkyLoaded() {
        try {
            Class.forName("org.popcraft.chunky.ChunkyProvider").getMethod("get").invoke(null);
            return true;
        } catch (ReflectiveOperationException | LinkageError e) {
            return false;
        }
    }
}
