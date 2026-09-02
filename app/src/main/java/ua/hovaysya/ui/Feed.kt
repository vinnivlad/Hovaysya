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
                // Only what was actually said. `/decisions` carries every
                // verdict including the silent ones, because the reason is what
                // makes a decision arguable -- but a screen called "Ховайся"
                // showing `too-far: oblast, not the city` is showing the
                // machine's reasoning as though it were a message. He saw one
                // with no text at all and said so.
                .onSuccess { rows = it.filter { row -> row.said != null }
                             problem = null }
                .onFailure { problem = it.message ?: "немає зв'язку" }
            delay(15_000)
        }
    }

    Feed(
        title = "Ховайся",
        subtitle = "рішення, найновіші вгорі",
        empty = "За останні дні Ховайся нічого не казав.",
        problem = problem,
        isEmpty = rows.isEmpty(),
    ) {
        items(rows.reversed(), key = { it.cursor }) { row ->
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
                            .background(
                                if (row.level == "alert") colourFor(Screen.ALERT)
                                else MaterialTheme.colorScheme.onSurfaceVariant
                            )
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
                // The reason, because a decision nobody can question is not one
                // that can be corrected -- which is how every rule here got fixed.
                row.reason?.let {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        it,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                // And the post it decided on, folded in below.
                row.text?.let {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        it.lines().joinToString(" ").take(180),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

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
                .onFailure { problem = it.message ?: "немає зв'язку" }
            delay(20_000)
        }
    }

    Feed(
        title = "Канали",
        subtitle = "останні 30 хв, найновіші вгорі",
        empty = "За останні 30 хвилин тихо.",
        problem = problem,
        isEmpty = rows.isEmpty(),
    ) {
        items(rows.reversed(), key = { "${it.channel}/${it.id}" }) { post ->
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

@Composable
private fun Feed(
    title: String,
    subtitle: String,
    empty: String,
    problem: String?,
    isEmpty: Boolean,
    rows: androidx.compose.foundation.lazy.LazyListScope.() -> Unit,
) {
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
                verticalArrangement = Arrangement.Top,
                content = rows,
            )
        }
    }
}
