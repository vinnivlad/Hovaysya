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
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
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

    // One key function, used both to key the list and to tell `Feed` which rows
    // it is looking at. Two copies would drift, and the follow would then be
    // watching something the list does not show.
    val keyOf = { row: Verdict -> row.cursor }

    Feed(
        title = "Ховайся",
        subtitle = "що казав Ховайся · найновіші внизу",
        empty = "За останні дні Ховайся нічого не казав.",
        problem = problem,
        keys = rows.map(keyOf),
    ) {
        items(rows, key = keyOf) { row ->
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

    val keyOf = { post: Post -> "${post.channel}/${post.id}" }

    Feed(
        title = "Канали",
        subtitle = "усі канали, останні 30 хв · найновіші внизу",
        empty = "За останні 30 хвилин тихо.",
        problem = problem,
        keys = rows.map(keyOf),
    ) {
        items(rows, key = keyOf) { post ->
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
 * Oldest at the top, newest at the bottom, and the view following the newest --
 * back where it started, and the round trip is worth recording because the
 * detour proves what the fault was not.
 *
 * His first instruction was the Telegram habit: "зроби новіші повідомлення
 * внизу, а не згори. Так в Телеграм, звичніше." Then, because new lines were not
 * appearing without a scroll, "давай вертаємо щоб новіші зверху" -- and that
 * changed nothing, which was the useful part: "Я думав якщо зробити свіжі
 * зверху, то це пофікситься." The order was never the fault. So the order goes
 * back to the one he wanted for its own sake.
 *
 * **The fault was the trigger.** The follow ran from `LaunchedEffect(count)`,
 * where `count` is the number of rows -- and neither feed changes its number of
 * rows when something arrives:
 *
 *   - `/decisions?said=1&limit=60` answers with exactly sixty rows once three
 *     days of logs hold that many, and one run alone said eighty-six things. A
 *     new line pushes the oldest out: sixty before, sixty after. The effect
 *     never re-ran once -- broken permanently, not intermittently.
 *   - `/messages?back=30m` is a sliding half hour. One in, one out, and the
 *     count is unchanged; it worked only when the numbers happened to differ.
 *
 * So the key is the identity of the newest row. That is what "something arrived"
 * means, and it is true of both feeds whatever their length does.
 *
 * Whether to follow is decided by **gestures**, not by arrivals. `following` is
 * set when a scroll *ends*, to whether that scroll ended at the bottom, and
 * arrivals do not scroll, so they cannot change it. Sampling "am I at the
 * bottom" at the moment a row lands would answer no every time: the row is
 * already there, below the fold, so `canScrollForward` has just become true for
 * the very reason we are asking.
 *
 * Somebody scrolled up is reading something, and yanking them away from it is
 * how a feed becomes unusable during exactly the hour it matters. So instead
 * they get the count of what arrived while they were reading, on a button that
 * takes them there -- and the button needs no flag of its own, because the
 * position already is one: at the bottom is following, away from it is not.
 */
/**
 * Whether the newest row is on screen, which is what following means here.
 *
 * Not `canScrollForward`. A row taller than the screen -- `war_monitor` writes
 * nightly summaries that easily are -- leaves the list able to scroll further
 * after it has been scrolled to, because the rest of that one row is still
 * below. Read that way, following would drop to false the moment the follow
 * itself succeeded, and the button would appear while he is looking at the very
 * line it offers to take him to.
 *
 * `totalItemsCount` rather than the row list: this runs inside a long-lived
 * collector, so anything captured from the composition would go stale on the
 * next poll while the layout never does.
 */
private fun LazyListState.atNewest(): Boolean = with(layoutInfo) {
    totalItemsCount == 0 || visibleItemsInfo.lastOrNull()?.index == totalItemsCount - 1
}

@Composable
private fun Feed(
    title: String,
    subtitle: String,
    empty: String,
    problem: String?,
    keys: List<String>,
    rows: androidx.compose.foundation.lazy.LazyListScope.() -> Unit,
) {
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()

    val newest = keys.lastOrNull()
    var opened by remember { mutableStateOf(false) }
    var following by remember { mutableStateOf(true) }
    // The newest row already counted, so a poll that brings three lines counts
    // three and not the whole window.
    var accounted by remember { mutableStateOf<String?>(null) }
    var unseen by remember { mutableStateOf(0) }

    // Reaching the newest row by hand says the same thing as pressing the
    // button, so it clears the count the same way. Reading `isScrollInProgress`
    // rather than the position means this fires once per gesture, at its end,
    // instead of on every frame of it.
    LaunchedEffect(listState) {
        snapshotFlow { listState.isScrollInProgress }.collect { scrolling ->
            if (!scrolling) {
                following = listState.atNewest()
                if (following) unseen = 0
            }
        }
    }

    LaunchedEffect(newest) {
        if (newest == null) return@LaunchedEffect
        val last = keys.lastIndex
        if (!opened) {
            // Opening the screen lands on the newest line with no animation --
            // his ask, and an animation here would only be a scroll he did not
            // make.
            listState.scrollToItem(last)
            opened = true
        } else if (following) {
            listState.animateScrollToItem(last)
        } else {
            // How many arrived since the last one counted. A window that turned
            // over completely while he was reading -- half an hour of channel
            // traffic -- has nothing left to count from, and then everything on
            // screen is fairly called new.
            val at = keys.indexOf(accounted)
            unseen += if (at < 0) keys.size else last - at
        }
        accounted = newest
        if (following) unseen = 0
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
        if (keys.isEmpty() && problem == null) {
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
            Box(Modifier.fillMaxSize()) {
                LazyColumn(
                    Modifier.fillMaxSize(),
                    state = listState,
                    verticalArrangement = Arrangement.Top,
                    content = rows,
                )
                if (unseen > 0) {
                    FloatingActionButton(
                        onClick = {
                            // Set here as well as in the scroll observer: the
                            // animation takes a moment, and a button that
                            // answers next frame feels broken.
                            unseen = 0
                            following = true
                            scope.launch {
                                listState.animateScrollToItem(keys.lastIndex)
                            }
                        },
                        shape = CircleShape,
                        containerColor = MaterialTheme.colorScheme.surfaceVariant,
                        contentColor = colourFor(Screen.WATCHING),
                        modifier = Modifier
                            .align(Alignment.BottomEnd)
                            .padding(20.dp),
                    ) {
                        Text(
                            "↓ " + if (unseen > 99) "99+" else unseen.toString(),
                            style = MaterialTheme.typography.labelLarge,
                        )
                    }
                }
            }
        }
    }
}
