package ua.hovaysya.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import ua.hovaysya.AlertService
import ua.hovaysya.R
import ua.hovaysya.Store

/**
 * The top of every screen: what this one is, and the two things reachable from
 * all of them.
 *
 * His ask: "кнопки «В укритті» і «Налаштування» щоб були видимі на всіх
 * екранах у хедері." They were on `Зараз` alone, which is the screen he is
 * least likely to be looking at when he wants them -- the point of the shelter
 * mode is to be switched on in the dark, and hunting for the right tab first
 * is the one thing it cannot ask of anybody.
 *
 * **No line under it**, and that was measured rather than assumed. He asked for
 * a horizontal rule separating the header from the content "like on the Ховайся
 * screen" -- and there is no rule anywhere in this app. What reads as one there
 * is the top edge of the first card. Told that, his answer was "лінію тоді не
 * роби, бо буде тепер 2 лінії", which is right: the card edge is already doing
 * the job on two screens out of three.
 *
 * The subtitle is a slot rather than a string. `Зараз` says where it is
 * watching in `bodyMedium`; the feeds say what they hold, in `labelSmall`, and
 * turn it red when the server is unreachable. Passing a style and a colour and
 * a flag to reconcile those would be three parameters describing one sentence
 * that the caller already knows how to write.
 */
@Composable
internal fun ScreenHeader(
    store: Store,
    title: String,
    onSettings: () -> Unit,
    subtitle: @Composable () -> Unit,
) {
    // Read through `remember` and not `Held`: this lives in `SharedPreferences`,
    // where re-reading costs nothing and can never be stale. A tab switch
    // destroys this composition, so every screen's header reads the truth as it
    // opens rather than inheriting another screen's copy.
    var sheltering by remember { mutableStateOf(store.sheltering) }
    val context = LocalContext.current

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleLarge)
            subtitle()
        }
        // "Я в укритті", one tap from wherever he is standing.
        //
        // His own drawing now, rather than the moon glyph that stood in for it:
        // a bunker says the thing the moon only suggested. It is tinted rather
        // than swapped, so the two states are one shape in two colours -- see
        // `ic_shelter`.
        Box(
            Modifier
                .size(40.dp)
                .clip(CircleShape)
                .clickable {
                    sheltering = !sheltering
                    store.sheltering = sheltering
                    // Or the badge on the permanent notification arrives up to
                    // thirty seconds late.
                    AlertService.refresh(context)
                },
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_shelter),
                contentDescription = "В укритті",
                tint = if (sheltering) MaterialTheme.colorScheme.primary
                       else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(24.dp),
            )
        }
        Box(
            Modifier
                .size(40.dp)
                .clip(CircleShape)
                .clickable(onClick = onSettings),
            contentAlignment = Alignment.Center,
        ) {
            // A glyph and not an icon resource: `material-icons` is a
            // dependency this app does not have, and a gear is read the same in
            // every language.
            Text(
                "⚙",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
