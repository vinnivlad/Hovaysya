package ua.hovaysya.ui

import androidx.compose.foundation.background
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
fun Now(store: Store) {
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
    val accent = colourFor(state)

    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp),
    ) {
        Status(health, problem)

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
            screen?.top?.let { top ->
                Spacer(Modifier.height(6.dp))
                Text(
                    top.word.replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }

            // "Дрони, Балістика Дорозвідка" -- the second line of his example.
            // Reconnaissance is not the threat, so it is never in the headline.
            screen?.recon?.takeIf { it.isNotEmpty() }?.let { recon ->
                Spacer(Modifier.height(10.dp))
                Text(
                    recon.joinToString(", ") {
                        it.word.replaceFirstChar { c -> c.uppercase() }
                    } + " — дорозвідка",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            screen?.cleared?.takeIf { it.isNotEmpty() }?.let { cleared ->
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
                        .background(
                            if (line.level == "alert") colourFor(Screen.ALERT)
                            else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                )
                Spacer(Modifier.size(10.dp))
                Column {
                    Text(line.text, style = MaterialTheme.typography.bodyMedium)
                    Text(
                        clock(line.at),
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

private fun headline(screen: Screen?, problem: String?): String = when {
    screen == null && problem != null -> "НЕ ЗНАЮ"
    screen == null -> "…"
    !screen.known -> "НЕ ЗНАЮ"
    screen.state == Screen.ALERT -> "ТРИВОГА"
    screen.state == Screen.WATCHING -> "СТЕЖУ"
    else -> "БЕЗ ЗАГРОЗ"
}

/**
 * "2026-09-02T21:14:07+00:00" -> "00:14" in Kyiv.
 *
 * The watcher stamps its log in **UTC**, so cutting the characters out of the
 * string -- which is what this did first -- would put every line three hours
 * into the past. On the one screen whose job is to say what is happening now,
 * that is the worst kind of wrong: quietly plausible.
 */
internal fun clock(iso: String): String = runCatching {
    OffsetDateTime.parse(iso)
        .atZoneSameInstant(ZoneId.systemDefault())
        .format(HH_MM)
}.getOrElse { iso }

/** Epoch seconds, as `/messages` gives them. */
internal fun clock(epochSeconds: Long): String =
    Instant.ofEpochSecond(epochSeconds)
        .atZone(ZoneId.systemDefault())
        .format(HH_MM)

private val HH_MM = DateTimeFormatter.ofPattern("HH:mm")
