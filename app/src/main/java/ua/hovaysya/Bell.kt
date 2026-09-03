package ua.hovaysya

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.provider.Settings

/**
 * The alphabet, and the one Android trap that would go unnoticed until it
 * mattered.
 *
 * # The alphabet
 *
 * His requirement, and the defect it exposed: "мені треба різні вібрації на
 * початок і кінець тривоги." The server marks an all-clear as `level="alert"`
 * with `alarm="clear"` -- because announcing it *is* an audible event -- so a
 * mapping keyed on the level alone rang the raid pattern for the end of the
 * raid. 72 of them in the live log. Being woken by what feels exactly like an
 * alert, to be told the alert is over, is the worst thing in this list.
 *
 * The start is his too: "3 коротких, 3 довгих, 3 коротких, так само як і в
 * застосунку Тривога". Which is SOS, and the point is not the code -- it is
 * that everyone in this country already knows that rhythm without being taught,
 * so it is the one pattern this app must not invent for itself.
 *
 *     початок тривоги   ··· --- ···       SOS, as Тривога rings it
 *     балістика         ▪▪▪▪▪▪▪▪▪▪▪▪      a dense stutter: the roof is not enough
 *     летить сюди       ·· ··             two knocks
 *     відбій            ▬▬▬▬▬             one long note, no rhythm at all
 *     тихо              (nothing)
 *
 * Four things to tell apart half asleep, so each differs in *rhythm* rather than
 * in length: nine structured pulses, twelve rapid ones, two quick ones, and a
 * single note. The all-clear is a single note on purpose -- nothing else in the
 * set is one pulse, so it cannot be mistaken for a warning even at the moment of
 * waking.
 *
 * Where the ballistic pattern comes from is worth saying: it is the one this app
 * has that Тривога does not, because the server has already decided the thing
 * concerns *this* person. That is the whole reason to prefer denser and more
 * insistent than SOS rather than a variation on it.
 *
 * # The trap
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

    /** Ballistic, or something over this very roof. */
    val shelter: String get() = "shelter.v$generation"

    /** The siren itself: a raid has begun. */
    val siren: String get() = "siren.v$generation"

    /** Something is heading into my circle. */
    val near: String get() = "near.v$generation"

    /** It is over. */
    val clear: String get() = "clear.v$generation"

    /** Worth knowing, not worth waking. */
    val quiet: String get() = "quiet.v$generation"

    /**
     * The service's own presence, and nothing else.
     *
     * Its own channel rather than `quiet`, for two reasons. It is not a message
     * about a threat -- it is the line that says this app is running at all --
     * and it needs `setShowBadge(false)`, which `quiet` must not have: a silent
     * status line about a real threat should still mark the icon.
     *
     * Without that the launcher wore a permanent unread dot, because Android
     * badges any active notification and this one never goes away. His words:
     * "на застосунку постійно висить червоний кружочок непрочитаного
     * повідомлення." A badge that is always on says nothing, which makes every
     * real one say nothing either.
     */
    val status: String get() = "status.v$generation"

    fun create(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
            ?: return

        // Every channel the server can ring with `level="alert"` bypasses night
        // mode, and none of the others do. That division is not this app's
        // judgement to make twice: the server has already decided whether this
        // person should be woken, and all that is left here is what it feels
        // like. Second-guessing it in the client is how two rule sets drift.
        val channels = listOf(
            NotificationChannel(
                shelter, "В укриття", NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Балістика, або загроза над самим домом."
                enableVibration(true)
                vibrationPattern = SHELTER
                setBypassDnd(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            },
            NotificationChannel(
                siren, "Тривога", NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Початок тривоги. Три коротких, три довгих, три коротких."
                enableVibration(true)
                vibrationPattern = SOS
                setBypassDnd(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            },
            NotificationChannel(
                near, "Загроза сюди", NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Щось летить у бік мого кола."
                enableVibration(true)
                vibrationPattern = NEAR
                setBypassDnd(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            },
            NotificationChannel(
                clear, "Відбій", NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                // Deliberately not bypassing night mode. Somebody who slept
                // through a raid does not need waking to hear it ended; somebody
                // who is awake and waiting does, and gets it. If that is the
                // wrong call it is one setting to change -- but the default has
                // to be one of the two, and this is the direction where being
                // wrong costs sleep rather than safety.
                description = "Тривога скінчилась. Один довгий сигнал."
                enableVibration(true)
                vibrationPattern = CLEAR
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            },
            NotificationChannel(
                quiet, "Тихо, для картини", NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Те, що варто знати, але не варто будити."
                enableVibration(false)
                setSound(null, null)
            },
            NotificationChannel(
                status, "Стан сервісу", NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Постійний рядок: чи є тривога і чи це працює."
                enableVibration(false)
                setSound(null, null)
                setShowBadge(false)
            },
        )
        manager.createNotificationChannels(channels)
    }

    /** Whether the shelter bell will actually be heard through night mode. */
    fun canWake(context: Context): Boolean {
        val manager = context.getSystemService(NotificationManager::class.java)
            ?: return false
        return manager.getNotificationChannel(shelter)?.canBypassDnd() == true
    }

    /**
     * A fresh set, because the old ones cannot be changed. The old ids are
     * deleted so the person is not left with ten channels in their system
     * settings, five of which do nothing.
     */
    fun remake(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        listOf(shelter, siren, near, clear, quiet, status)
            .forEach { manager?.deleteNotificationChannel(it) }
        store.channelGeneration = generation + 1
        create(context)
    }

    /**
     * Which bell a decision rings, from the two words the server already sends.
     *
     * The all-clear is tested **first**, and that order is the whole correction:
     * an all-clear arrives as `level="alert"` with `alarm="clear"`, so anything
     * that looks at the level before the alarm rings a raid to announce the end
     * of one.
     */
    fun channelFor(level: String?, alarm: String?): String = when {
        alarm == "clear" || alarm == "clear-partial" -> clear
        level != "alert" -> quiet
        alarm == "ballistic" -> shelter
        // The siren's own declaration, as opposed to a report of what is flying.
        alarm == "alert" -> siren
        else -> near
    }

    /**
     * Post one, so a bell can be heard before the night it arrives. Which is the
     * only way to check the alphabet at all: patterns are distinguishable only
     * if somebody has felt every one of them.
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

        // `{ wait, buzz, wait, buzz, ... }` in milliseconds. Tuned by rhythm
        // rather than by Morse timing: what matters is that a hand can tell
        // these apart, not that a radio operator could.

        /** ··· --- ···  three short, three long, three short. */
        private val SOS = longArrayOf(
            0, 180, 140, 180, 140, 180,
            320, 520, 140, 520, 140, 520,
            320, 180, 140, 180, 140, 180,
        )

        /** A dense stutter. Nothing structured about it, which is the point. */
        private val SHELTER = longArrayOf(
            0, 150, 100, 150, 100, 150, 100, 150, 100, 150, 100, 150,
            100, 150, 100, 150, 100, 150, 100, 150, 100, 150, 100, 150,
        )

        /** Two knocks. */
        private val NEAR = longArrayOf(0, 250, 180, 250)

        /** One long note. The only single-pulse pattern in the set. */
        private val CLEAR = longArrayOf(0, 1200)
    }
}
