package ua.hovaysya

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.provider.Settings

/**
 * The three bells, and the one Android trap that would go unnoticed until it
 * mattered.
 *
 * A notification channel is **immutable once created**. Importance, vibration
 * pattern and `setBypassDnd` are read at creation, and every later
 * `createNotificationChannel` with the same id is ignored -- on purpose, because
 * these settings belong to the person rather than to the app.
 *
 * Which sets a trap. The app has to create channels on first launch to be able
 * to notify at all, but `setBypassDnd(true)` is refused unless "Доступ до режиму
 * «Не турбувати»" is already granted -- and that grant has no runtime prompt, so
 * on a first launch it never is. The shelter channel is then permanently one
 * that cannot bypass night mode. No error, no warning, and the failure surfaces
 * at three in the morning on the one night it counts.
 *
 * The only way out is a new channel id, so the generation is a stored number
 * rather than a constant: granting the access bumps it, and [canWake] reports
 * what the channel *actually* got by reading it back from the system instead of
 * assuming we were obeyed.
 */
class Bell(private val store: Store) {

    private val generation: Int get() = store.channelGeneration

    val shelter: String get() = "shelter.v$generation"
    val alert: String get() = "alert.v$generation"
    val quiet: String get() = "quiet.v$generation"

    fun create(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
            ?: return

        val shelterChannel = NotificationChannel(
            shelter, "В укриття", NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Балістика, або загроза над самим домом."
            enableVibration(true)
            vibrationPattern = SHELTER_PATTERN
            // Ignored unless policy access is granted at this moment.
            setBypassDnd(true)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }

        val alertChannel = NotificationChannel(
            alert, "Загроза сюди", NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Щось летить у бік мого кола."
            enableVibration(true)
            vibrationPattern = ALERT_PATTERN
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }

        val quietChannel = NotificationChannel(
            quiet, "Тихо, для картини", NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Те, що варто знати, але не варто будити."
            enableVibration(false)
            setSound(null, null)
        }

        manager.createNotificationChannels(
            listOf(shelterChannel, alertChannel, quietChannel))
    }

    /** Whether the shelter bell will actually be heard through night mode. */
    fun canWake(context: Context): Boolean {
        val manager = context.getSystemService(NotificationManager::class.java)
            ?: return false
        return manager.getNotificationChannel(shelter)?.canBypassDnd() == true
    }

    /**
     * A fresh set of channels, because the old ones cannot be changed. The old
     * ids are deleted so the person is not left with six channels in their
     * system settings, two of which do nothing.
     */
    fun remake(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        listOf(shelter, alert, quiet).forEach { manager?.deleteNotificationChannel(it) }
        store.channelGeneration = generation + 1
        create(context)
    }

    /**
     * Which bell a decision rings, from the two words the server already sends.
     * The mapping is here and not on the server: the server decides *whether* to
     * wake somebody, and this decides what that feels like.
     */
    fun channelFor(level: String?, alarm: String?): String = when {
        level == "alert" && alarm == "ballistic" -> shelter
        level == "alert" -> alert
        else -> quiet
    }

    /**
     * Post one, so a bell can be heard before the night it arrives. Which is the
     * only way to check the alphabet at all: three patterns are distinguishable
     * only if somebody has felt all three.
     */
    fun ring(context: Context, channel: String, title: String, body: String) {
        val manager = context.getSystemService(NotificationManager::class.java)
            ?: return
        val notification = Notification.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_bell)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .build()
        manager.notify(channel.hashCode(), notification)
    }

    companion object {
        /** Whether the person has granted "Не турбувати" access at all. */
        fun policyGranted(context: Context): Boolean =
            context.getSystemService(NotificationManager::class.java)
                ?.isNotificationPolicyAccessGranted == true

        /** The settings page for it. There is no runtime prompt for this one. */
        fun policyIntent(): Intent =
            Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS)

        /**
         * The alphabet. Three patterns that can be told apart through a mattress,
         * half asleep, without looking -- which is the whole specification.
         *
         * `{ wait, buzz, wait, buzz, ... }` in milliseconds.
         */
        // Long, insistent, three times: this one means move.
        private val SHELTER_PATTERN = longArrayOf(0, 700, 250, 700, 250, 700)
        // Two short knocks: something is coming, but the roof is not the answer.
        private val ALERT_PATTERN = longArrayOf(0, 250, 180, 250)
    }
}
