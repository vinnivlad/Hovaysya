package ua.hovaysya

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Read the field, never the sentence -- his call: "не мудри по слову відбій.
 * Почекаємо змін на сервері."
 *
 * The three questions a line is asked are not the same question. An all-clear is
 * `level="alert"` with `alarm="clear"`, because announcing one is an audible
 * event, so anything colouring by the level alone drew the end of a raid with
 * the same red mark as the raid. And a partial clear is neither the end of
 * anything nor a danger: "Відбій по балістиці" lifts one class while the alert
 * runs on.
 */
class LineTest {

    private fun line(level: String?, alarm: String?) =
        Line(at = "2026-09-04T18:41:25Z", level = level, alarm = alarm,
             text = "текст")

    @Test
    fun `a full all-clear is loud but is not danger`() {
        val clear = line("alert", "clear")
        assertTrue(clear.isClear)
        assertFalse(clear.isPartial)
        assertFalse(clear.isLoud)
    }

    @Test
    fun `a partial all-clear is neither the end nor a danger`() {
        val partial = line("alert", "clear-partial")
        assertFalse(partial.isClear)
        assertTrue(partial.isPartial)
        assertFalse(partial.isLoud)
    }

    @Test
    fun `an alert with a threat class is the loud case`() {
        val loud = line("alert", "drone-jet")
        assertTrue(loud.isLoud)
        assertFalse(loud.isClear)
        assertFalse(loud.isPartial)
    }

    @Test
    fun `a quiet line is never loud, whatever it carries`() {
        assertFalse(line("info", "drone-jet").isLoud)
        assertFalse(line("info", "none").isLoud)
        assertFalse(line(null, null).isLoud)
    }

    @Test
    fun `the word does not decide it, the field does`() {
        // A sentence that says відбій with no `alarm` to match is not an
        // all-clear, and one that says nothing of the kind but carries the
        // field is.
        val sentence = Line(at = "x", level = "alert", alarm = "drone",
                            text = "Відбій тривоги")
        assertFalse(sentence.isClear)
        val field = Line(at = "x", level = "alert", alarm = "clear",
                         text = "Жуляни")
        assertTrue(field.isClear)
    }

    @Test
    fun `a screen with no state admits it rather than claiming calm`() {
        // The seconds after a phone registers, before the watcher has written
        // anything for it. Telling somebody there are no threats when nobody
        // has looked would be the worst available lie.
        assertFalse(screen(state = null).known)
        assertTrue(screen(state = Screen.QUIET).known)
    }

    private fun screen(state: String?) = Screen(
        state = state, home = "Жуляни", at = null, top = null, threat = null,
        recon = emptyList(), cleared = emptyList(), peak = 0,
        said = emptyList(), ended = null, note = null, version = null,
    )
}
