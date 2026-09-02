package ua.hovaysya.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import ua.hovaysya.Screen

/**
 * The palette is decided by the circumstance rather than by taste: this screen
 * is read in the dark, half awake, in the first second after being woken. So
 * saturation is spent in exactly one place -- the state -- and everything else
 * is a neutral with a slight cast towards it, which is what stops the page
 * looking assembled from defaults.
 */

// Grounds. Not pure black: an OLED pure black makes the type edges bloom, and
// this is read at arm's length in a dark room.
private val NightGround = Color(0xFF111214)
private val NightRaised = Color(0xFF1B1D21)
private val DayGround = Color(0xFFF7F6F3)
private val DayRaised = Color(0xFFFFFFFF)

// The three states, and each has to be recognisable before the words are.
private val Calm = Color(0xFF5B7C74)      // nothing is flying
private val Watch = Color(0xFFC98A2B)     // something is up, not here
private val Danger = Color(0xFFD5442C)    // it concerns me

private val NightText = Color(0xFFECEAE6)
private val NightMuted = Color(0xFF8E9096)
private val DayText = Color(0xFF1A1B1D)
private val DayMuted = Color(0xFF6B6C70)

private val night = darkColorScheme(
    primary = Watch,
    onPrimary = Color(0xFF14150F),
    background = NightGround,
    onBackground = NightText,
    surface = NightGround,
    onSurface = NightText,
    surfaceVariant = NightRaised,
    onSurfaceVariant = NightMuted,
    error = Danger,
    onError = Color(0xFFFFF3F0),
    outline = Color(0xFF34373C),
)

private val day = lightColorScheme(
    primary = Watch,
    onPrimary = Color(0xFF14150F),
    background = DayGround,
    onBackground = DayText,
    surface = DayGround,
    onSurface = DayText,
    surfaceVariant = DayRaised,
    onSurfaceVariant = DayMuted,
    error = Danger,
    onError = Color(0xFFFFF3F0),
    outline = Color(0xFFD8D5CE),
)

// One display size that is deliberately larger than Material's largest: the top
// line has to be legible without focusing.
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
        colorScheme = if (isSystemInDarkTheme()) night else day,
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
    else -> MaterialTheme.colorScheme.onSurfaceVariant
}
