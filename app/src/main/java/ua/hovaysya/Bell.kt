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
 *     початок тривоги   ··· ▬▬▬ ···       SOS, as Тривога rings it
 *     балістика         ············      a dense stutter: the roof is not enough
 *     летить сюди       ·· ··             knock-knock, knock-knock
 *     відбій            ▬                 one long note, no rhythm at all
 *     тихо              (nothing)
 *
 * One glyph per pulse, `·` short and `▬` long, so what Settings draws can
 * be compared against what the arrays actually do. It could not be, and
 * the cost was this: the drawing said two pairs and the array buzzed one.
 * A screen that teaches the wrong alphabet is worse than one that teaches
 * none, because it is believed.
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
 *
 * The same trap catches every other edit to these definitions, and for longer,
 * because nothing reports it. An id also carries [RECIPE], a fingerprint of the
 * patterns themselves, so changing one changes the ids and the channels are
 * rebuilt without anybody having to know that they must be. Three of my changes
 * to the alphabet reached nobody before that existed.
 */
class Bell(private val store: Store) {

    private val generation: Int get() = store.channelGeneration

    private fun id(name: String) = "$name.$RECIPE.v$generation"

    /** Ballistic, or something over this very roof. */
    val shelter: String get() = id("shelter")

    /** The siren itself: a raid has begun. */
    val siren: String get() = id("siren")

    /** Something is heading into my circle. */
    val near: String get() = id("near")

    /** It is over. */
    val clear: String get() = id("clear")

    /** Worth knowing, not worth waking. */
    val quiet: String get() = id("quiet")

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
    val status: String get() = id("status")

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
                // Silent as a channel. The sound is played by `Siren` at a
                // volume this app controls, which a channel's own cannot be --
                // and a channel's sound is immutable once created, so it could
                // never have become a setting.
                setSound(null, null)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            },
            NotificationChannel(
                siren, "Тривога", NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Початок тривоги. Три коротких, три довгих, три коротких."
                enableVibration(true)
                vibrationPattern = SOS
                setBypassDnd(true)
                // Silent as a channel. The sound is played by `Siren` at a
                // volume this app controls, which a channel's own cannot be --
                // and a channel's sound is immutable once created, so it could
                // never have become a setting.
                setSound(null, null)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            },
            NotificationChannel(
                near, "Загроза сюди", NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Щось летить у бік мого кола."
                enableVibration(true)
                vibrationPattern = NEAR
                setBypassDnd(true)
                // Silent as a channel. The sound is played by `Siren` at a
                // volume this app controls, which a channel's own cannot be --
                // and a channel's sound is immutable once created, so it could
                // never have become a setting.
                setSound(null, null)
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
                // Silent as a channel. The sound is played by `Siren` at a
                // volume this app controls, which a channel's own cannot be --
                // and a channel's sound is immutable once created, so it could
                // never have become a setting.
                setSound(null, null)
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

        // And throw away our own channels from an earlier recipe. Without this
        // the system's notification settings fill up with dead copies of "В
        // укриття" -- one per edit -- and there is no way for anybody to tell
        // which of them is the live one.
        //
        // Only ours, matched on the name before the first dot. Deleting a
        // channel somebody else made would be a fine way to break another app.
        val wanted = channels.map { it.id }.toSet()
        manager.notificationChannels
            .filter { it.id.substringBefore('.') in NAMES && it.id !in wanted }
            .forEach { manager.deleteNotificationChannel(it.id) }
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
        // Sound first, and only where this app actually speaks -- "звук там де
        // його видає Ховайся". Three sounds for five channels: the wail when a
        // raid is declared, the same siren in the near rhythm for anything
        // arriving over him, the till's pip when it is over. The quiet window
        // can zero the volume; it never touches the vibration.
        val volume = store.volumeNow()
        when (channel) {
            siren -> Siren.alert(volume)
            // Ballistic had been playing the drone's rhythm, which is his
            // report: "зараз звук як у наближення дрона". Three sounds for five
            // channels is still the arrangement; what was wrong was which two
            // shared one.
            shelter -> Siren.rhythm(SHELTER, volume)
            near -> Siren.rhythm(NEAR, volume)
            clear -> Siren.clear(volume)
            else -> Unit
        }
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
        //
        // **Every gap is at least 200 ms**, and that is the lesson these
        // patterns cost twice. A vibration motor does not stop when the
        // pattern says off -- it spins down, and a gap shorter than that reads
        // as one buzz getting momentarily weaker rather than as two buzzes.
        //
        // `NEAR` had 180 ms pulses split by 120, and it merged: "вібрація на
        // «Загроза сюди» не 2 + 2, а 1 + 1". He had reported that once before
        // and I fixed the array -- two pulses became four -- while leaving the
        // gaps that were hiding them, so the second report was the same bug
        // surviving its own fix. `SOS` had the same defect at 180/140, which
        // means "три короткі" were never three.
        //
        // Pulses got shorter as the gaps got longer, so the rhythms still fit
        // in the same time. A short pulse is easier to count anyway: what the
        // hand reads is the *edges*, and there are twice as many of those in a
        // tap than in a buzz.
        //
        // `SHELTER` is exempt on purpose -- it is meant to be one continuous
        // thing -- and the guard in `test_repo_hygiene` knows that.

        private val NAMES = setOf(
            "shelter", "siren", "near", "clear", "quiet", "status")

        /**
         * A fingerprint of the alphabet, carried in every channel id.
         *
         * **A notification channel is immutable once it exists.** Its vibration
         * pattern, its sound, its importance are read when it is created and
         * never again, so editing them in this file changes nothing on a phone
         * that already has the channel. There was a stored counter for this, but
         * only a button in Settings ever bumped it -- so every change I made to
         * the alphabet was inert until somebody happened to press it.
         *
         * That is what his two reports were. "Вібрація на «Загроза сюди» не
         * 2 + 2, а 1 + 1" was true after I had fixed the array, because his phone
         * still held the channel built from the *first* version of it; and
         * "нічого не вібрувало, здається вібрувало 1 раз від пуш повідомлення"
         * is a channel still carrying Android's default, because `setSound(null,
         * null)` never reached it either. I changed the definitions three times
         * and the phone was never told once.
         *
         * So the id now derives from the definitions. Change a pattern and the
         * ids change with it, the channels are rebuilt on the next launch, and
         * the stale ones are deleted. Nobody has to remember anything, which is
         * the only kind of fix that holds -- the counter is still here, because
         * the night-mode grant genuinely is a different reason to rebuild.
         *
         * `String.hashCode` is specified by the language rather than left to the
         * runtime, so this is stable across launches and devices. It only has to
         * *change* when the recipe changes; it does not have to be a good hash.
         */
        private val RECIPE: String by lazy {
            val recipe = listOf(
                SOS, SHELTER, NEAR, CLEAR,
            ).joinToString("|") { it.joinToString(",") } +
                // Not a pattern, but just as immutable, and just as inert when
                // it changes: the channels are silent because `Siren` owns the
                // sound now.
                "|silent"
            Integer.toHexString(recipe.hashCode())
        }

        /** ··· ▬▬▬ ···  three short, three long, three short. */
        private val SOS = longArrayOf(
            0, 140, 200, 140, 200, 140,
            420, 480, 200, 480, 200, 480,
            420, 140, 200, 140, 200, 140,
        )

        /**
         * Three short, then three short. His call, and it replaces a dense
         * stutter of twelve pulses at 100 ms that was designed to be felt as
         * one continuous thing.
         *
         * The stutter was the wrong idea twice over. It was indistinguishable
         * from a phone buzzing at nothing in particular, which is the one thing
         * the loudest pattern in the alphabet must not be, and its gaps were
         * below the width a hand can feel -- so what it actually delivered was
         * an undifferentiated hum, not a chosen texture.
         *
         * Six pulses split three and three, gapped like the rest of the
         * alphabet so they can be counted. The sound follows the same array,
         * because a bell and a buzz saying different things is how somebody
         * learns neither.
         */
        private val SHELTER = longArrayOf(
            0, 90, 220, 90, 220, 90,
            500, 90, 220, 90, 220, 90,
        )

        /**
         * Knock-knock, knock-knock. Four pulses in two pairs.
         *
         * It was one pair, and Settings had always drawn it as two
         * -- his catch: "наче має бути 2 коротких + 2 коротких, а
         * гуде 1 короткий + 1 короткий". The drawing was the better
         * of the two and not only because it was published: a single
         * pair is what every other app does for an ordinary
         * notification, and this one has to be recognisable as
         * deliberate.
         *
         * Then it still buzzed 1 + 1, because four pulses split by
         * 120 ms are not four pulses to a hand. The gaps are the fix;
         * see the note above the patterns.
         */
        private val NEAR = longArrayOf(0, 90, 220, 90, 500, 90, 220, 90)

        /** One long note. The only single-pulse pattern in the set. */
        private val CLEAR = longArrayOf(0, 1200)
    }
}
