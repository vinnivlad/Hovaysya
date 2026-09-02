package ua.hovaysya.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
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
        content = content,
    )
}

/** The colour a state is owed. Unknown is muted, never calm. */
@Composable
fun colourFor(state: String?): Color = when (state) {
    Screen.ALERT -> Danger
    Screen.WATCHING -> Watch
    Screen.QUIET -> Calm
    else -> Muted
}
