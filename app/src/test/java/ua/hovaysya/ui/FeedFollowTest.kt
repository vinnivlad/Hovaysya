package ua.hovaysya.ui

import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotDisplayed
import androidx.compose.ui.test.hasScrollAction
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.unit.dp
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The fault this file exists for, in one sentence: **the number of rows is not
 * the news.**
 *
 * The follow used to run from `LaunchedEffect(count)`, and neither feed changes
 * its number of rows when something arrives. `/decisions?said=1&limit=60`
 * answers with exactly sixty once the logs hold that many -- 146 in the
 * three-day window for his own recipient -- so a new line pushed the oldest out
 * and the count stayed sixty forever. His report: "не працює автоматичний
 * скролінг на останнє повідомлення, навіть якщо я сидів на останньому
 * повідомленні."
 *
 * The first test here is that exact shape: sixty rows in, sixty rows out, the
 * newest one different. It fails against the old trigger and passes against the
 * one keyed on the newest row's identity.
 *
 * A screen big enough to hold several rows and not all of them: the whole
 * subject is what happens off the bottom of the viewport.
 */
@RunWith(RobolectricTestRunner::class)
@Config(qualifiers = "w400dp-h800dp")
class FeedFollowTest {

    @get:Rule
    val rule = createComposeRule()

    private var keys by mutableStateOf(window(1))

    /** Sixty rows, the way both feeds answer: a window, not a growing list. */
    private fun window(from: Int) = (from until from + 60).map { "рядок $it" }

    private fun show() {
        rule.setContent {
            HovaysyaTheme {
                Feed(
                    title = "Ховайся",
                    subtitle = "тест",
                    empty = "нічого",
                    problem = null,
                    keys = keys,
                ) {
                    items(keys, key = { it }) { key ->
                        Text(key, Modifier.height(60.dp))
                    }
                }
            }
        }
    }

    @Test
    fun `opening the feed lands on the newest line`() {
        show()

        rule.onNodeWithText("рядок 60").assertIsDisplayed()
    }

    @Test
    fun `a feed whose length never changes still follows the newest line`() {
        show()
        rule.onNodeWithText("рядок 60").assertIsDisplayed()

        // The window slides: one arrives, the oldest falls out, sixty either
        // way. This is the whole bug.
        keys = window(2)
        rule.waitForIdle()

        rule.onNodeWithText("рядок 61").assertIsDisplayed()
    }

    @Test
    fun `scrolled away, what arrives is counted rather than shoved at him`() {
        show()
        rule.onNode(hasScrollAction()).performScrollToIndex(0)
        rule.waitForIdle()

        keys = window(2)
        rule.waitForIdle()

        // Still where he was reading -- the oldest row fell out of the window
        // with the slide, so the top of it is now the second -- and told how
        // much he is behind rather than being taken there.
        rule.onNodeWithText("рядок 2").assertIsDisplayed()
        rule.onNodeWithText("рядок 61").assertIsNotDisplayed()
        rule.onNodeWithText("↓ 1").assertIsDisplayed()

        keys = window(3)
        rule.waitForIdle()
        rule.onNodeWithText("↓ 2").assertIsDisplayed()
    }

    @Test
    fun `the button takes him to the newest line and clears itself`() {
        show()
        rule.onNode(hasScrollAction()).performScrollToIndex(0)
        rule.waitForIdle()
        keys = window(2)
        rule.waitForIdle()

        rule.onNodeWithText("↓ 1").performClick()
        rule.waitForIdle()

        rule.onNodeWithText("рядок 61").assertIsDisplayed()
        rule.onNodeWithText("↓ 1").assertDoesNotExist()
    }

    @Test
    fun `scrolling back by hand says the same thing as pressing it`() {
        show()
        rule.onNode(hasScrollAction()).performScrollToIndex(0)
        rule.waitForIdle()
        keys = window(2)
        rule.waitForIdle()
        rule.onNodeWithText("↓ 1").assertIsDisplayed()

        rule.onNode(hasScrollAction()).performScrollToIndex(keys.lastIndex)
        rule.waitForIdle()

        rule.onNodeWithText("↓ 1").assertDoesNotExist()
    }

    @Test
    fun `nothing arriving means no button, however long he reads`() {
        show()
        rule.onNode(hasScrollAction()).performScrollToIndex(0)
        rule.waitForIdle()

        // A poll that brings the same rows back is not news, and the trigger
        // keys on the newest row's identity rather than on the poll.
        keys = window(1)
        rule.waitForIdle()

        rule.onNodeWithText("↓ 1").assertDoesNotExist()
    }
}
