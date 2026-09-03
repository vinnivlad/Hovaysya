package ua.hovaysya

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Start watching again after a reboot, without anybody opening the app.
 *
 * Which matters more here than the usual convenience argument. A phone reboots
 * for a system update in the middle of the night, and the person who owns it
 * finds out at three in the morning that nothing has been watching since --
 * because the app looked exactly the same either way. The service being
 * unstoppable-looking in the shade is precisely what makes its absence hard to
 * notice.
 *
 * The same argument covers an app update, which is what he caught: "після
 * оновлення не витягло активний статус тривоги". Installing an APK over a
 * running app kills the process, and Android does not bring a foreground
 * service back afterwards -- so every update left the phone unwatched until
 * somebody happened to open the app, and the only sign was a notification that
 * had quietly stopped being there. Worse than a reboot, because an update is a
 * thing we do deliberately, and we did it during a live alert.
 *
 * `MY_PACKAGE_REPLACED` is delivered to the app that was just replaced, needs no
 * permission, and is one of the few broadcasts still allowed to start a
 * foreground service from the background. Same handler, same guard.
 *
 * Only for a phone that has registered. Starting a service that would
 * immediately stop itself is noise in the log and a moment of a notification
 * nobody asked for.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val wakes = intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == Intent.ACTION_MY_PACKAGE_REPLACED
        if (!wakes) return
        if (!Store(context).registered) return
        AlertService.start(context)
    }
}
