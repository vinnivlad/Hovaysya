package ua.hovaysya.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.delay
import ua.hovaysya.Health
import ua.hovaysya.Screen
import ua.hovaysya.Store

/**
 * The screen he described: "теперішню максимальну загрозу (знижує коли дали
 * частковий відбій)", "без загроз коли тривоги нема", "дорозвідка і яка + нижча
 * загроза", and the last few lines Ховайся said.
 *
 * All of it arrives composed as facts from `/state`, so nothing here decides
 * anything -- this file chooses type sizes and what sits above what. The one
 * judgement it does make is what to show when the answer is not known, and it
 * refuses to guess: an app that reports calm because it failed to ask is worse
 * than one that says it does not know.
 */
@Composable
fun Now(store: Store, onSettings: () -> Unit) {
    var screen by remember { mutableStateOf<Screen?>(null) }
    var health by remember { mutableStateOf<Health?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }

    // While this screen is open, and only then. Background waking is the push
    // notification's job, and polling from the foreground is what keeps a screen
    // that is being *looked at* honest.
    LaunchedEffect(Unit) {
        while (true) {
            val api = store.api()
            runCatching { api.screen() }
                .onSuccess { screen = it; problem = null }
                .onFailure { problem = it.message ?: "немає зв'язку" }
            runCatching { api.health() }.onSuccess { health = it }
            delay(10_000)
        }
    }

    val state = screen?.state
    val accent = headlineColour(state)
    val alerting = state == Screen.ALERT

    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp),
    ) {
        // The service on the left, the way in to settings on the right. One row,
        // because both are things you glance at rather than read.
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.weight(1f)) { Status(health, problem) }
            Box(
                Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .clickable(onClick = onSettings),
                contentAlignment = Alignment.Center,
            ) {
                // A glyph and not an icon resource: `material-icons` is a
                // dependency this app does not have, and a gear is read the same
                // in every language.
                Text(
                    "⚙",
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        Column(
            Modifier.fillMaxWidth().weight(1f),
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                headline(screen, problem),
                style = MaterialTheme.typography.displayLarge,
                color = accent,
            )

            // The maximum threat still in the air. Under the headline rather
            // than in it, because "ТРИВОГА" and "балістика" are two facts and
            // one can change without the other.
            // Only while an alert is on, which overrules what I argued
            // yesterday. I kept the class under the headline because it "does
            // not lose the information" -- and he sent a screenshot of "БЕЗ
            // ТРИВОГ" with "Реактивний шахед" beneath it, which contradicts
            // itself before it informs anybody.
            //
            // The information was not worth keeping there either. A class with
            // no place attached says nothing anybody can act on, and if the
            // thing were coming here the bell would have rung and the siren
            // would have followed. `watching` means something is in the air
            // somewhere, which is the state this app exists to stop reporting.
            screen?.top?.takeIf { alerting }?.let { top ->
                Spacer(Modifier.height(6.dp))
                Text(
                    top.word.replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.titleLarge,
                    color = colourFor(state),
                )
            }

            // "Дрони, Балістика Дорозвідка" -- the second line of his example,
            // and for the same reason it is only shown during one. What is being
            // re-checked is a detail of a raid, not news on its own.
            screen?.recon?.takeIf { alerting && it.isNotEmpty() }?.let { recon ->
                Spacer(Modifier.height(10.dp))
                Text(
                    recon.joinToString(", ") {
                        it.word.replaceFirstChar { c -> c.uppercase() }
                    } + " — дорозвідка",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            screen?.cleared?.takeIf { alerting && it.isNotEmpty() }?.let { cleared ->
                Spacer(Modifier.height(4.dp))
                Text(
                    "Знято: " + cleared.joinToString(", ") { it.word },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            screen?.note?.let { note ->
                Spacer(Modifier.height(10.dp))
                Text(
                    note,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        // "останні 1-3 повідомлення від ховайся внизу"
        screen?.said?.takeLast(3)?.reversed()?.forEach { line ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .padding(14.dp, 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(markFor(loud = line.isLoud,
                                             clear = line.isClear,
                                             partial = line.isPartial))
                )
                Spacer(Modifier.size(10.dp))
                Column {
                    // The one place a cut belongs, and his: "обрізати має сенс
                    // хіба на головному екрані в застосунку, де 1-3 останні
                    // повідомлення внизу." By lines rather than by characters,
                    // so it fits the space it actually has instead of a number
                    // guessed against an unknown width.
                    //
                    // It will almost never fire. The median sentence is 19
                    // characters and only 5 of 5895 run past 60 -- all of them
                    // lists of oblasts, which is exactly the case where the foot
                    // of this screen is the wrong place for twelve names.
                    Text(
                        line.text,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    // How long the alert ran, beside the line that ended it.
                    // It is the one thing worth still knowing once a raid is
                    // over, and the reason the closing line outlives the rest.
                    val lasted = screen?.ended
                        ?.takeIf { line.isClear }
                        ?.let { " · тривало " + spell(it.lastedS) }
                    Text(
                        clock(line.at) + (lasted ?: ""),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/**
 * The service, in one line. His reason for wanting it at all: "бо ж реально,
 * якщо А не працює, то який взагалі сенс?"
 *
 * `poll_age_s` is the number that means something -- the watcher rewrites its
 * log after every poll whether or not anything arrived. The age of the last
 * *message* is not health: ten-minute silences happened 307 times in two weeks.
 */
@Composable
private fun Status(health: Health?, problem: String?) {
    val text = when {
        problem != null -> problem
        health == null -> "…"
        !health.ok -> "сервіс не відповідає як слід"
        health.pollAgeS == null -> "сервіс на звʼязку"
        health.pollAgeS > 300 -> "спостерігач мовчить ${health.pollAgeS / 60} хв"
        else -> "спостерігач живий"
    }
    val bad = problem != null || health?.ok == false ||
        (health?.pollAgeS ?: 0L) > 300
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(7.dp)
                .clip(CircleShape)
                .background(
                    if (bad) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.onSurfaceVariant
                )
        )
        Spacer(Modifier.size(8.dp))
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Start,
        )
    }
}

/**
 * One question, two answers. "СТЕЖУ" was answering a different question than the
 * one somebody opens this screen to ask, and he said so: "Стежу значить немає
 * тривоги? Так і пиши БЕЗ ТРИВОГ."
 *
 * `watching` and `quiet` therefore read the same here, and they are not the same
 * underneath -- the difference shows as the threat named below, which is where
 * it belongs. What is never collapsed is not knowing: an app that reports calm
 * because it failed to ask is worse than one that admits it.
 */
private fun headline(screen: Screen?, problem: String?): String = when {
    screen == null && problem != null -> "НЕ ЗНАЮ"
    screen == null -> "…"
    !screen.known -> "НЕ ЗНАЮ"
    screen.state == Screen.ALERT -> "ТРИВОГА"
    else -> "БЕЗ ТРИВОГ"
}

/**
 * Kyiv time, always, whatever the phone is set to.
 *
 * Not the device zone, and this is the second thing that number taught. The
 * watcher stamps its log in UTC, so slicing the characters out of the string --
 * which is what this did first -- put every line three hours into the past. That
 * was fixed by converting properly, into `systemDefault()`, and the emulator
 * runs in UTC: the feed showed 06:28 while Kyiv said 09:28, and it read exactly
 * like a service that had stopped three hours ago.
 *
 * So the zone is the domain's rather than the device's. These are Kyiv alerts,
 * the channels write Kyiv time, the person is in Kyiv, and a phone in the wrong
 * zone -- travelling, or an emulator out of the box -- must not be able to
 * make this screen lie about when something happened. There is nothing here a
 * device setting should be allowed to move.
 */
/**
 * And it has to be looked up defensively. "Europe/Kyiv" became the canonical
 * name only in tzdata 2022b; on a device whose zone database predates that --
 * and minSdk here is Android 8 -- the name is "Europe/Kiev" and `ZoneId.of`
 * throws rather than returning anything. A crash on the screen that says whether
 * to take cover is not a trade worth making for a spelling.
 *
 * The fixed offset is the last resort and is knowingly wrong for half the year,
 * because Ukraine keeps summer time. It is there so the worst case is a clock an
 * hour out rather than no screen at all.
 */
private val KYIV: ZoneId = sequenceOf("Europe/Kyiv", "Europe/Kiev")
    .mapNotNull { runCatching { ZoneId.of(it) }.getOrNull() }
    .firstOrNull()
    ?: ZoneId.of("+03:00")
private val HH_MM = DateTimeFormatter.ofPattern("HH:mm")

/**
 * A duration in the words a person would use. "1 год 20 хв", "45 хв", "40 с".
 *
 * Rounded to what matters: nobody reading how long a raid lasted needs the
 * seconds, and everybody reading a forty-second one would notice their absence.
 */
internal fun spell(seconds: Long): String {
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    return when {
        hours > 0 && minutes > 0 -> "$hours год $minutes хв"
        hours > 0 -> "$hours год"
        minutes > 0 -> "$minutes хв"
        else -> "$seconds с"
    }
}

/** An ISO stamp from the decision log, which is written in UTC. */
internal fun clock(iso: String): String = runCatching {
    OffsetDateTime.parse(iso).atZoneSameInstant(KYIV).format(HH_MM)
}.getOrElse { iso }

/** Epoch seconds, as `/messages` gives them. */
internal fun clock(epochSeconds: Long): String =
    Instant.ofEpochSecond(epochSeconds).atZone(KYIV).format(HH_MM)
