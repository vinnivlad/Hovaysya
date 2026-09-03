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
 * Only for a phone that has registered. Starting a service that would
 * immediately stop itself is noise in the log and a moment of a notification
 * nobody asked for.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (!Store(context).registered) return
        AlertService.start(context)
    }
}
