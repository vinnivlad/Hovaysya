package ua.hovaysya.ui

import androidx.compose.material3.Text
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import ua.hovaysya.Store

/**
 * The two controls that now have to be on every screen.
 *
 * His ask: "кнопки «В укритті» і «Налаштування» щоб були видимі на всіх екранах
 * у хедері." They were on `Зараз` alone, and the shelter mode is exactly the
 * one thing that cannot ask somebody to find the right tab first -- it is
 * pressed in the dark, on the way down the stairs.
 *
 * Worth a test rather than a look, because the failure is silent and per
 * screen: one of the three forgets to use the header, nothing breaks, nothing
 * warns, and it is noticed the night the button is wanted and is not there.
 */
@RunWith(RobolectricTestRunner::class)
class HeaderTest {

    @get:Rule
    val rule = createComposeRule()

    private val store = Store(ApplicationProvider.getApplicationContext())

    @Before
    fun clean() {
        store.sheltering = false
    }

    private fun show(onSettings: () -> Unit = {}) {
        rule.setContent {
            HovaysyaTheme {
                ScreenHeader(store, "Ховайся", onSettings) { Text("підпис") }
            }
        }
    }

    @Test
    fun `both controls are in the header`() {
        show()
        rule.onNodeWithContentDescription("В укритті").assertExists()
        rule.onNodeWithText("⚙").assertExists()
    }

    @Test
    fun `the shelter button writes the mode down, not just the screen`() {
        // The state has to reach `Store`, because the service reads it there --
        // a button that only coloured itself would be a mode nothing obeys.
        show()
        assertFalse(store.sheltering)
        rule.onNodeWithContentDescription("В укритті").performClick()
        assertTrue(store.sheltering)
        rule.onNodeWithContentDescription("В укритті").performClick()
        assertFalse(store.sheltering)
    }

    @Test
    fun `the header opens on whatever the mode already is`() {
        // Switching tabs destroys the composition, so each screen's header
        // builds its own copy of this. Reading it from `Store` as it opens is
        // what keeps three headers from disagreeing about one mode.
        store.sheltering = true
        show()
        rule.onNodeWithContentDescription("В укритті").assertExists()
        assertTrue(store.sheltering)
    }

    @Test
    fun `the gear is a way out of every screen`() {
        var opened = false
        show { opened = true }
        rule.onNodeWithText("⚙").performClick()
        assertTrue(opened)
    }
}
