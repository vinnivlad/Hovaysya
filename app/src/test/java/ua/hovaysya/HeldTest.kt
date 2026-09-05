package ua.hovaysya

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * Forgetting the device has to forget all of it.
 *
 * `Held` outlives the screens on purpose -- switching tabs destroys their
 * composition, and a feed that starts from nothing says "тихо" when it means "I
 * have stopped knowing". The cost of living that long is this: when the phone
 * forgets who it is, everything here belongs to the previous person -- their
 * ring, their raid, their lines, decided from a home that is not this one.
 */
class HeldTest {

    @Before
    fun fill() {
        Held.screen = Screen(
            state = Screen.ALERT, home = "Жуляни", at = 1L, top = Named("drone-jet", "реактивний"),
            threat = null, recon = emptyList(), cleared = emptyList(), peak = 2,
            said = listOf(Line("x", "alert", "drone-jet", "Жуляни")),
            ended = null, note = "нотатка", version = "v1",
        )
        Held.health = Health(ok = true, corpus = true, pollAgeS = 3,
                             messageAgeS = 9)
        Held.problem = "немає мережі"
        Held.said = listOf(Verdict("c", "at", "a", "alert", "drone", "Жуляни",
                                   "new target near me", "текст"))
        Held.saidProblem = "немає звʼязку"
        Held.posts = listOf(Post("mon1tor_ua", 1, 2, "текст", null))
        Held.postsProblem = "сервіс не відповідає"
    }

    @Test
    fun `clear leaves nothing of the previous person behind`() {
        Held.clear()

        assertNull(Held.screen)
        assertNull(Held.health)
        assertNull(Held.problem)
        assertEquals(emptyList<Verdict>(), Held.said)
        assertNull(Held.saidProblem)
        assertEquals(emptyList<Post>(), Held.posts)
        assertNull(Held.postsProblem)
    }

    /**
     * A tripwire, not an assertion about behaviour.
     *
     * The test above can only catch a field that `clear` forgets if it also
     * sets that field, so a field added to `Held` and left out of both would
     * pass. Counting them means adding one breaks this instead, and whoever
     * adds it is then holding the failing test that names the reason.
     */
    @Test
    fun `every field held here is accounted for above`() {
        val settable = Held.javaClass.declaredMethods
            .filter { it.name.startsWith("set") && it.parameterCount == 1 }
            .map { it.name }
            .toSet()
        assertEquals(
            "Held has a field the clear test does not set: $settable",
            7, settable.size,
        )
        assertTrue(settable.toString(), settable.containsAll(listOf(
            "setScreen", "setHealth", "setProblem",
            "setSaid", "setSaidProblem", "setPosts", "setPostsProblem",
        )))
    }
}
