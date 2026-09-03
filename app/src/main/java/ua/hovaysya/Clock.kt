package ua.hovaysya

import java.time.Instant
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Kyiv time, always, whatever the phone is set to.
 *
 * Not the device zone, and that is the domain's decision rather than a
 * formatting preference. These are Kyiv alerts, the channels write Kyiv time,
 * the person is in Kyiv, and a phone in the wrong zone -- travelling, or an
 * emulator out of the box -- must not be able to make any of this lie about when
 * something happened. The emulator taught it: the feed read 06:28 while Kyiv
 * said 09:28, which looked exactly like a service that had died three hours ago.
 *
 * It lives here rather than in `ui` because quiet hours need it too, and a
 * window that silences an alarm is not a formatting concern.
 *
 * Looked up defensively. "Europe/Kyiv" became the canonical name only in tzdata
 * 2022b; on a device whose zone database predates that -- and minSdk here is
 * Android 8 -- the name is "Europe/Kiev" and `ZoneId.of` throws rather than
 * returning anything. The fixed offset is the last resort and is knowingly wrong
 * for half the year, because Ukraine keeps summer time; it is there so the worst
 * case is a clock an hour out rather than no screen at all.
 */
val KYIV: ZoneId = sequenceOf("Europe/Kyiv", "Europe/Kiev")
    .mapNotNull { runCatching { ZoneId.of(it) }.getOrNull() }
    .firstOrNull()
    ?: ZoneId.of("+03:00")

private val HH_MM = DateTimeFormatter.ofPattern("HH:mm")

/** An ISO stamp from the decision log, which the watcher writes in UTC. */
fun clock(iso: String): String = runCatching {
    OffsetDateTime.parse(iso).atZoneSameInstant(KYIV).format(HH_MM)
}.getOrElse { iso }

/** Epoch seconds, as `/messages` gives them. */
fun clock(epochSeconds: Long): String =
    Instant.ofEpochSecond(epochSeconds).atZone(KYIV).format(HH_MM)

/**
 * A duration in the words a person would use. "1 год 20 хв", "45 хв", "40 с".
 *
 * Rounded to what matters: nobody reading how long a raid lasted needs the
 * seconds, and everybody reading a forty-second one would notice their absence.
 */
fun spell(seconds: Long): String {
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    return when {
        hours > 0 && minutes > 0 -> "$hours год $minutes хв"
        hours > 0 -> "$hours год"
        minutes > 0 -> "$minutes хв"
        else -> "$seconds с"
    }
}

/** When sound is withheld, if the setting is on. Kyiv's clock, not the phone's. */
val QUIET_FROM: LocalTime = LocalTime.of(22, 0)
val QUIET_UNTIL: LocalTime = LocalTime.of(8, 0)

/**
 * Whether the quiet window is open now.
 *
 * The window crosses midnight, so it is a union rather than a range: after
 * ten or before eight. Written out because the obvious `from <= now && now <
 * until` is false at every hour the window is actually open.
 */
fun inQuietHours(now: LocalTime = LocalTime.now(KYIV)): Boolean =
    now >= QUIET_FROM || now < QUIET_UNTIL
