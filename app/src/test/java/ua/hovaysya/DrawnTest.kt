package ua.hovaysya

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

/**
 * What the permanent line actually shows, so it is not posted again unchanged.
 *
 * His report: "раз при тривозі пуш не свайпався і я не міг припинити звук", on
 * an unlocked phone. Re-posting a notification cancels a drag that is in
 * progress, and this app re-posts constantly -- `/state` is a long poll that
 * answers either when something changed **or** when its thirty seconds run out,
 * and every answer called `show`.
 *
 * Measured over 742 nights of the corpus, replayed through the same policy the
 * server runs:
 *
 *     answers                            814167     1097 a night
 *     of them redrew a different line      4912        7 a night
 *     changed nothing on screen             99.4%
 *     answers per hour                      120 median, 133 worst
 *
 * One re-post every thirty seconds, all day and all night, and about seven of
 * them a night carry news. The swipe had to survive a coin toss it should never
 * have been asked to make.
 *
 * So the line is compared before it is posted, and this is the comparison.
 * Everything the shade can see and nothing else: what a `Screen` carries beyond
 * these four fields is the feed's business.
 */
class DrawnTest {

    private fun screen(
        state: String? = Screen.ALERT,
        top: Named? = Named("shahed", "шахед"),
        said: List<Line> = emptyList(),
        at: Long? = 1_000,
        peak: Int = 0,
        version: String? = "a",
    ) = Screen(state = state, home = "Жуляни", at = at, top = top,
               threat = top, recon = emptyList(), cleared = emptyList(),
               peak = peak, said = said, ended = null, note = null,
               version = version)

    private fun drawn(screen: Screen?, problem: String? = null,
                      sheltering: Boolean = false) =
        AlertService.drawnOf(screen, problem, sheltering)

    @Test
    fun `a new version that changes nothing visible draws the same line`() {
        // The 99.4%. The server answers because the feed moved, or because a
        // reconnaissance flag aged out, or simply because thirty seconds
        // passed -- and the shade has no way to show any of it.
        val before = drawn(screen(version = "a", at = 1_000))
        val after = drawn(screen(version = "b", at = 1_060, peak = 3))
        assertEquals(before, after)
    }

    @Test
    fun `the worst thing in the air is the line, so a new one redraws`() {
        assertNotEquals(
            drawn(screen(top = Named("shahed", "шахед"))),
            drawn(screen(top = Named("ballistic", "балістика"))))
    }

    @Test
    fun `the end of a raid redraws`() {
        // Title, body and colour all move at once, and this is the redraw that
        // has to survive any amount of skipping.
        assertNotEquals(
            drawn(screen(state = Screen.ALERT)),
            drawn(screen(state = Screen.QUIET, top = null)))
    }

    @Test
    fun `only the newest thing said shows, so older lines do not redraw`() {
        // `said` holds the last three. Two of them scrolling past is a change
        // in the payload and no change at all in the shade.
        val older = Line("2026-09-10T00:00:00+00:00", "info", null, "Дрон.")
        val newer = Line("2026-09-10T00:01:00+00:00", "info", null, "Ще дрон.")
        val newest = Line("2026-09-10T00:02:00+00:00", "alert", "clear",
                          "Відбій тривоги.")
        assertEquals(
            drawn(screen(state = Screen.QUIET, top = null,
                         said = listOf(older, newest))),
            drawn(screen(state = Screen.QUIET, top = null,
                         said = listOf(newer, newest))))
    }

    @Test
    fun `a different last line redraws`() {
        val clear = Line("2026-09-10T00:02:00+00:00", "alert", "clear",
                         "Відбій тривоги.")
        val drone = Line("2026-09-10T00:03:00+00:00", "info", null,
                         "Дрон на Бровари.")
        assertNotEquals(
            drawn(screen(state = Screen.QUIET, top = null, said = listOf(clear))),
            drawn(screen(state = Screen.QUIET, top = null, said = listOf(drone))))
    }

    @Test
    fun `the shelter badge is part of the line`() {
        // It is drawn as `setSubText`, so a comparison that ignored it would
        // make turning the mode on invisible until the sky changed -- which is
        // the bug that `ACTION_REFRESH` was added for. Skipping redraws must
        // not bring it back by another road.
        assertNotEquals(
            drawn(screen(), sheltering = false),
            drawn(screen(), sheltering = true))
    }

    @Test
    fun `trouble is the line while it lasts`() {
        assertNotEquals(drawn(screen(), problem = null),
                        drawn(screen(), problem = "немає зв'язку"))
        // And its minute counter is real news: it is the difference between a
        // deploy and an outage.
        assertNotEquals(drawn(null, problem = "немає зв'язку"),
                        drawn(null, problem = "немає зв'язку · 5 хв"))
    }

    @Test
    fun `not knowing is not the same as quiet`() {
        // A server that has never written for this person, against one saying
        // there is nothing in the air. Same absence of a threat, opposite
        // meanings, and the line has always said so.
        assertNotEquals(drawn(null), drawn(screen(state = Screen.QUIET, top = null)))
    }
}
