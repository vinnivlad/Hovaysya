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
import ua.hovaysya.Held
import ua.hovaysya.Post
import ua.hovaysya.clock
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
    // Kept above the tabs -- see `Held`. An empty feed and a forgotten one look
    // identical on screen, and one of them is a lie.
    val rows = Held.said
    val problem = Held.saidProblem

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { store.api().verdicts() }
                // The server filters now, and it has to: filtering after a
                // limit is not a filter. The check stays as a belt, since a
                // row with nothing said has nothing to draw.
                .onSuccess { Held.said = it.filter { row -> row.said != null }
                             Held.saidProblem = null }
                .onFailure { Held.saidProblem = saidPlainly(it) }
            delay(15_000)
        }
    }

    Feed(
        title = "Ховайся",
        subtitle = "що казав Ховайся · найновіші зверху",
        empty = "За останні дні Ховайся нічого не казав.",
        problem = problem,
        isEmpty = rows.isEmpty(),
        count = rows.size,
    ) {
        items(rows.asReversed(), key = { it.cursor }) { row ->
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
    val rows = Held.posts
    val problem = Held.postsProblem

    LaunchedEffect(Unit) {
        while (true) {
            // Thirty minutes, which is his number: "коли я відкриваю скрін, я
            // хочу бачити останні повідомлення за 30хв".
            runCatching { store.api().posts(minutes = 30) }
                .onSuccess { Held.posts = it; Held.postsProblem = null }
                .onFailure { Held.postsProblem = saidPlainly(it) }
            delay(20_000)
        }
    }

    Feed(
        title = "Канали",
        subtitle = "усі канали, останні 30 хв · найновіші зверху",
        empty = "За останні 30 хвилин тихо.",
        problem = problem,
        isEmpty = rows.isEmpty(),
        count = rows.size,
    ) {
        items(rows.asReversed(), key = { "${it.channel}/${it.id}" }) { post ->
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
 * Newest at the top, and the view sitting at the top -- his direction, after
 * living with the other way round: "в додатку фід Ховайся і фід всіх каналів
 * давай вертаємо щоб новіші зверху."
 *
 * It was the Telegram habit before this ("зроби новіші повідомлення внизу, а не
 * згори. Так в Телеграм, звичніше"), and the argument for it was that a feed
 * growing downwards puts the newest line where the thumb already is. What that
 * argument missed is what these two screens are for. A chat is a conversation
 * you are inside of, so it reads forwards; these answer "what is happening" and
 * "why do you say that", and the answer to both is the last line rather than the
 * first. Opening the app during a raid should not mean scrolling to the end of
 * half an hour of channel traffic to find out. The main screen has said the
 * newest thing first since it existed, so this also stops two screens out of
 * three from disagreeing about which way time runs.
 *
 * The list follows new arrivals only when it is already at the top. Somebody
 * scrolled down is reading something, and yanking them away from it to show a
 * line they have not asked for is how a feed becomes unusable during exactly the
 * hour it matters.
 *
 * What makes that safe with the newest first is the `key` on every row: new
 * messages now arrive *above* whatever is being read, and a list keyed by index
 * alone would shift the reader down by one row for each of them. Keyed, the
 * scroll position stays on the message it was on.
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
        val wasAtTop = listState.firstVisibleItemIndex <= 1
        if (!opened || wasAtTop) {
            listState.scrollToItem(0)
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
