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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import ua.hovaysya.Health
import ua.hovaysya.Held
import ua.hovaysya.clock
import ua.hovaysya.saidPlainly
import ua.hovaysya.spell
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
    // Read from `Held`, not remembered here: this composition dies every time
    // he touches another tab, and the state must not die with it. Reading the
    // fields during composition subscribes to them, so the answer that arrives
    // a moment later still redraws.
    val screen = Held.screen
    val health = Held.health
    val problem = Held.problem

    // While this screen is open, and only then. Background waking is the push
    // notification's job, and polling from the foreground is what keeps a screen
    // that is being *looked at* honest.
    LaunchedEffect(Unit) {
        while (true) {
            val api = store.api()
            runCatching { api.screen() }
                .onSuccess { Held.screen = it; Held.problem = null }
                .onFailure { Held.problem = saidPlainly(it) }
            runCatching { api.health() }.onSuccess { Held.health = it }
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
        // The name, and what it is for. Nowhere inside the app said either --
        // his observation, and the second half of it is the sharper one: the
        // feed's tab is labelled "Ховайся" and, with the name established
        // nowhere, that label read as a word chosen for no reason.
        //
        // Quiet, but not as quiet as it was. The line used to add "Будить лише
        // про твоє коло" in the smallest type there is, which is a promise
        // nobody could read making a claim the app has to earn anyway; he asked
        // for it gone and for the rest a little larger. The headline below is
        // still the only thing here anybody needs at a glance.
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.Top,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    "Ховайся",
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Text(
                    "Стежить за небом.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(8.dp))
                Status(health, problem)
            }
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
 *
 * The words are about the watching and not about a watcher, which is his
 * correction: "«спостерігач живий» треба змінити. Фраза двозначна в цих
 * реаліях." It is, and so was its opposite -- "спостерігач мовчить 12 хв" reads
 * worse than the state it describes. An app for air raids cannot afford a line
 * that could be read as being about a person, however well the code means it.
 */
@Composable
private fun Status(health: Health?, problem: String?) {
    val text = when {
        problem != null -> problem
        health == null -> "…"
        !health.ok -> "сервіс не відповідає як слід"
        health.pollAgeS == null -> "сервіс на звʼязку"
        health.pollAgeS > 300 -> "спостереження стоїть ${health.pollAgeS / 60} хв"
        else -> "спостереження працює"
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
