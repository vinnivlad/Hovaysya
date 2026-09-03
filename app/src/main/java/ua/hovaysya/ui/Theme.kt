package ua.hovaysya.ui

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import ua.hovaysya.Screen

/**
 * One theme, dark, whatever the phone is set to. His call: "зроби його в темних
 * тонах, наче він в dark-mode. Це буде одна і єдина тема в ньому."
 *
 * Which is the right call for this app rather than a preference, and worth
 * writing down: the screen that matters is opened in a dark room, at arm's
 * length, in the first seconds after being woken. A light theme is not a
 * different taste there -- it is a flash of white in the face of somebody who
 * has just been told a missile is coming, and it costs them the seconds their
 * eyes need to read the one word on the screen.
 *
 * Being the only theme also means the palette can be tuned for it instead of
 * being half of a pair. Saturation is spent in exactly one place -- the state --
 * and the neutrals carry a slight cast towards it, which is what keeps the page
 * from reading as assembled from defaults.
 *
 * `res/values/colors.xml` holds the ground colour a second time, because the
 * window manager paints it before any Kotlin runs. There is no `values-night`:
 * with one theme it would be a copy, and a copy is somewhere for the two to
 * drift apart.
 */

// Not pure black. On OLED it makes type edges bloom, which is the opposite of
// legible at the moment this screen is read.
private val Ground = Color(0xFF0E0F11)
private val Raised = Color(0xFF191B1F)
private val Outline = Color(0xFF2E3136)

// Warm off-white rather than white: softer at night, and it stops the display
// line from glaring when it fills half the screen.
private val Text = Color(0xFFECEAE6)
private val Muted = Color(0xFF8B8D93)

// The three states, each recognisable before its word is read.
private val Calm = Color(0xFF5F8479)      // nothing is flying
private val Watch = Color(0xFFD4952F)     // something is up, not here
private val Danger = Color(0xFFE8503A)    // it concerns me

private val scheme = darkColorScheme(
    primary = Watch,
    onPrimary = Color(0xFF14150F),
    secondary = Calm,
    background = Ground,
    onBackground = Text,
    surface = Ground,
    onSurface = Text,
    surfaceVariant = Raised,
    onSurfaceVariant = Muted,
    error = Danger,
    onError = Color(0xFF1A0D0A),
    outline = Outline,
    outlineVariant = Outline,
)

// One display size deliberately larger than Material's largest: the top line has
// to be legible without focusing.
private val typography = Typography(
    displayLarge = TextStyle(
        fontSize = 46.sp, lineHeight = 50.sp, fontWeight = FontWeight.Bold),
    titleLarge = TextStyle(
        fontSize = 21.sp, lineHeight = 27.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 17.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 21.sp),
    labelSmall = TextStyle(
        fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium,
        letterSpacing = 0.8.sp),
)

@Composable
fun HovaysyaTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = scheme,
        typography = typography,
    ) {
        // The `Surface` is here rather than in each screen, and it is not
        // decoration. Outside one, Compose leaves `LocalContentColor` at its
        // default -- **black** -- so any `Text` without an explicit colour comes
        // out black on this near-black ground.
        //
        // Which is exactly what happened: `App` puts the four tabs inside a
        // `Scaffold`, so they were fine, but the first-run screen returns before
        // that and had no surface above it at all. Every word of the
        // registration screen was black on black. Putting it in the theme means
        // no screen can be added later that forgets it.
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = scheme.background,
            contentColor = scheme.onBackground,
            content = content,
        )
    }
}

/** The colour a state is owed. Unknown is muted, never calm. */
@Composable
fun colourFor(state: String?): Color = when (state) {
    Screen.ALERT -> Danger
    Screen.WATCHING -> Watch
    Screen.QUIET -> Calm
    else -> Muted
}

/**
 * The headline's colour, which is a coarser question than the state.
 *
 * His: "на головному екрані Стежу значить немає тривоги? Так і пиши БЕЗ ТРИВОГ
 * зеленим." The top line answers one thing -- is there an alert -- and that has
 * two answers, so `watching` is green like `quiet` and the amber lives on the
 * threat line underneath instead. Nothing is lost: what is being tracked is
 * still named, in the colour that says it is being tracked.
 */
@Composable
fun headlineColour(state: String?): Color = when (state) {
    Screen.ALERT -> Danger
    Screen.WATCHING, Screen.QUIET -> Calm
    else -> Muted
}

/**
 * Green for the end of a raid, amber for one class of it, red for a raid,
 * muted for a status line.
 *
 * The amber is the one worth arguing about, and he raised it: a partial
 * all-clear -- "Відбій по балістиці" -- is good news that does not end
 * anything. Green would say it was over while a drone was still up; red would
 * say the lifting was itself a danger. It is the middle, and this is the only
 * mark in the set that means "less than before".
 */
@Composable
fun markFor(loud: Boolean, clear: Boolean, partial: Boolean = false): Color = when {
    clear -> Calm
    partial -> Watch
    loud -> Danger
    else -> Muted
}
