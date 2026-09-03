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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import ua.hovaysya.Post
import ua.hovaysya.saidPlainly
import ua.hovaysya.Screen
import ua.hovaysya.Store
import ua.hovaysya.Verdict

/**
 * The two feeds, which exist because he asked for the noise to be somewhere
 * other than the screen that wakes him: "спам повідомленнями на основному екрані
 * це таки може бути незручно. Для спаму повідомленнями буде свій спеціальний
 * екран."
 *
 * So the first screen answers "what is happening" and these answer "why do you
 * say that" -- one showing what Ховайся decided, the other the raw channels it
 * decided from. Keeping the second is his point too: "тут добре що повідомлення
 * самого каналу теж завжди виводиться, що дасть додатковий контекст."
 */

/** What Ховайся said, and the reason it gives itself. */
@Composable
fun HovaysyaFeed(store: Store) {
    var rows by remember { mutableStateOf<List<Verdict>>(emptyList()) }
    var problem by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { store.api().verdicts() }
                // The server filters now, and it has to: filtering after a
                // limit is not a filter. The check stays as a belt, since a
                // row with nothing said has nothing to draw.
                .onSuccess { rows = it.filter { row -> row.said != null }
                             problem = null }
                .onFailure { problem = saidPlainly(it) }
            delay(15_000)
        }
    }

    Feed(
        title = "Ховайся",
        subtitle = "що казав Ховайся · найновіші внизу",
        empty = "За останні дні Ховайся нічого не казав.",
        problem = problem,
        isEmpty = rows.isEmpty(),
        count = rows.size,
    ) {
        items(rows, key = { it.cursor }) { row ->
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(16.dp, 4.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .padding(14.dp, 12.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        Modifier
                            .width(3.dp)
                            .height(16.dp)
                            .background(markFor(
                                loud = row.level == "alert"
                                    && !isClear(row.alarm)
                                    && !isPartial(row.alarm),
                                clear = isClear(row.alarm),
                                partial = isPartial(row.alarm),
                            ))
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        clock(row.at),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    row.alarm?.takeIf { it != "none" }?.let {
                        Spacer(Modifier.width(8.dp))
                        Text(
                            it.uppercase(),
                            style = MaterialTheme.typography.labelSmall,
                            color = colourFor(Screen.WATCHING),
                        )
                    }
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    row.said ?: "",
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = if (row.level == "alert") FontWeight.SemiBold
                                 else null,
                )
                // The rule name is not shown -- his call, and he is right that it
                // is not for this screen: "в застосунку в чаті ховайся не виводь
                // назву правила". `too-far: oblast, not the city` is written for
                // whoever is arguing with the policy, and it still travels in
                // `/decisions` for exactly that. A feed is read by somebody
                // asking what happened.
                // And the post it decided on, whole. It used to be folded onto
                // one line and cut at 180 characters -- "якщо вже показуємо
                // повідомлення, то показуємо його повністю" -- and the fold cost
                // as much as the cut: a channel writing two facts on two lines
                // had them run together into one sentence about one thing.
                row.text?.let {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        it,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

// The field, never the sentence. A word in a sentence is a guess about a
// wording that can change; `alarm` is the contract -- his call, and the earlier
// version of this file had exactly the cleverness he ruled out.
//
// Full apart from partial, too: "Відбій по балістиці" lifts one class while the
// alert continues, so it earns the amber mark and not the green one.
private fun isClear(alarm: String?): Boolean = alarm == "clear"

private fun isPartial(alarm: String?): Boolean = alarm == "clear-partial"

/** Every channel, merged into one stream. */
@Composable
fun ChannelFeed(store: Store) {
    var rows by remember { mutableStateOf<List<Post>>(emptyList()) }
    var problem by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        while (true) {
            // Thirty minutes, which is his number: "коли я відкриваю скрін, я
            // хочу бачити останні повідомлення за 30хв".
            runCatching { store.api().posts(minutes = 30) }
                .onSuccess { rows = it; problem = null }
                .onFailure { problem = saidPlainly(it) }
            delay(20_000)
        }
    }

    Feed(
        title = "Канали",
        subtitle = "усі канали, останні 30 хв · найновіші внизу",
        empty = "За останні 30 хвилин тихо.",
        problem = problem,
        isEmpty = rows.isEmpty(),
        count = rows.size,
    ) {
        items(rows, key = { "${it.channel}/${it.id}" }) { post ->
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(16.dp, 4.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .padding(14.dp, 12.dp),
            ) {
                Row {
                    Text(
                        clock(post.ts),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        post.channel,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.height(6.dp))
                Text(post.text, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/**
 * Oldest at the top, newest at the bottom, and the view sitting at the bottom --
 * his: "зроби новіші повідомлення внизу, а не згори. Так в Телеграм, звичніше."
 *
 * Which is more than habit. A feed that grows downwards puts the newest line
 * where the thumb already is and where the eye last was, and every message app
 * anybody here uses has taught that for years. Reading a raid upwards means
 * re-learning the direction of time at the moment least suited to it.
 *
 * The list follows new arrivals only when it is already at the bottom. Somebody
 * scrolled up is reading something, and yanking them away from it to show a line
 * they have not asked for is how a feed becomes unusable during exactly the hour
 * it matters.
 */
@Composable
private fun Feed(
    title: String,
    subtitle: String,
    empty: String,
    problem: String?,
    isEmpty: Boolean,
    count: Int,
    rows: androidx.compose.foundation.lazy.LazyListScope.() -> Unit,
) {
    val listState = rememberLazyListState()
    var opened by remember { mutableStateOf(false) }
    LaunchedEffect(count) {
        if (count == 0) return@LaunchedEffect
        val info = listState.layoutInfo
        val lastVisible = info.visibleItemsInfo.lastOrNull()?.index ?: -1
        val wasAtBottom = lastVisible >= info.totalItemsCount - 2
        if (!opened || wasAtBottom) {
            listState.scrollToItem(count - 1)
            opened = true
        }
    }

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(24.dp, 20.dp, 24.dp, 10.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge)
            Text(
                problem ?: subtitle,
                style = MaterialTheme.typography.labelSmall,
                color = if (problem != null) MaterialTheme.colorScheme.error
                        else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (isEmpty && problem == null) {
            Box(
                Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    empty,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            LazyColumn(
                Modifier.fillMaxSize(),
                state = listState,
                verticalArrangement = Arrangement.Top,
                content = rows,
            )
        }
    }
}
