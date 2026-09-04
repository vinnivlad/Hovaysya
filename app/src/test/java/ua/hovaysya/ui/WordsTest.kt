package ua.hovaysya.ui

import org.junit.Assert.assertEquals
import org.junit.Test
import ua.hovaysya.Screen

/**
 * The words the screens are allowed to say.
 *
 * Each of these is a ruling of his rather than a default, which is why they are
 * worth a test: they are the kind of thing a later edit "tidies" without knowing
 * what it is for.
 */
class WordsTest {

    private fun screen(state: String?) = Screen(
        state = state, at = null, top = null, threat = null,
        recon = emptyList(), cleared = emptyList(), peak = 0,
        said = emptyList(), ended = null, note = null, version = null,
    )

    @Test
    fun `watching is not an alert, and says so in the top line`() {
        // His: "на головному екрані Стежу значить немає тривоги? Так і пиши БЕЗ
        // ТРИВОГ зеленим." The headline answers one question -- is there an
        // alert -- and that has two answers, so what is being tracked lives on
        // the line underneath instead.
        assertEquals("БЕЗ ТРИВОГ", headline(screen(Screen.WATCHING), null))
        assertEquals("БЕЗ ТРИВОГ", headline(screen(Screen.QUIET), null))
        assertEquals("ТРИВОГА", headline(screen(Screen.ALERT), null))
    }

    @Test
    fun `not knowing is never drawn as calm`() {
        // A phone in the seconds after it registers, and a phone that cannot
        // reach the service, are both ignorant rather than safe. Saying "БЕЗ
        // ТРИВОГ" there would be the worst available lie.
        assertEquals("НЕ ЗНАЮ", headline(screen(state = null), null))
        assertEquals("НЕ ЗНАЮ", headline(screen(state = null), "немає мережі"))
        assertEquals("НЕ ЗНАЮ", headline(null, "немає мережі"))
    }

    @Test
    fun `before the first answer it says nothing rather than guessing`() {
        // No state and no failure yet: the request is still in flight, and an
        // ellipsis is the honest answer for that second.
        assertEquals("…", headline(null, null))
    }

    @Test
    fun `the tiers are named the way he names them`() {
        assertEquals("МІЙ РАЙОН", tierWord("my-area"))
        assertEquals("ПОРУЧ", tierWord("my-district"))
        assertEquals("КИЇВ", tierWord("city"))
        assertEquals("ОБЛАСТЬ", tierWord("oblast"))
    }

    @Test
    fun `a tier with no word of its own still reads as a label`() {
        // Not left lowercase among shouted ones, and not dropped either: a
        // gazetteer that grows a tier must not produce a blank chip.
        assertEquals("ELSEWHERE", tierWord("elsewhere"))
    }
}
