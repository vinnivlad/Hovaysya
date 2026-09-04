package ua.hovaysya

import java.net.SocketTimeoutException
import java.net.UnknownHostException
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * What a failure looks like to somebody who is not debugging it.
 *
 * The rule these guard is his report: `HTTP 502` was reaching the permanent
 * notification, which happens every time the API restarts, because the proxy
 * answers with an HTML page and there is no JSON in it to read a message out of.
 * A transport status code is not news to anybody holding a phone.
 */
class SaidPlainlyTest {

    @Test
    fun `no network is the phone's own problem and says so`() {
        assertEquals("немає мережі", saidPlainly(UnknownHostException("hovaysya")))
    }

    @Test
    fun `a timeout is the service, not the network`() {
        assertEquals("сервіс не відповідає", saidPlainly(SocketTimeoutException()))
    }

    @Test
    fun `an unknown token asks for the one thing that fixes it`() {
        // 401 also carries the server's own "потрібен токен", which is true and
        // useless to a phone that thought it had one.
        assertEquals("зареєструйся знову",
                     saidPlainly(ApiError("потрібен токен", 401)))
    }

    @Test
    fun `no status code ever reaches the screen`() {
        for (code in listOf(500, 502, 503, 504)) {
            val said = saidPlainly(ApiError("HTTP $code", code))
            assertEquals("сервіс не відповідає", said)
        }
    }

    @Test
    fun `the server's own wording passes through`() {
        // It is written in Ukrainian for a person, and better than anything
        // this side could invent. These two are the server's own words, from
        // `tools/serve/api.py`.
        assertEquals("занадто часто, спробуй за хвилину",
                     saidPlainly(ApiError("занадто часто, спробуй за хвилину",
                                          429)))
        assertEquals("нема такого", saidPlainly(ApiError("нема такого", 404)))
    }

    @Test
    fun `a five hundred keeps its wording to itself`() {
        // The order of the branches decides this, and it is worth a test of its
        // own because the docstring above the function reads as though every
        // message but 401 passes through. What the server sends with a 500 is
        // "не записалось: " and a Python exception, which is not for anybody
        // holding a phone -- so the generic wording is the better answer and
        // the comment is what is out of date.
        assertEquals("сервіс не відповідає",
                     saidPlainly(ApiError("не записалось: KeyError('who')", 500)))
    }

    @Test
    fun `anything unrecognised still says something`() {
        assertEquals("немає звʼязку", saidPlainly(IllegalStateException()))
        assertEquals("немає звʼязку", saidPlainly(ApiError("", 0)))
    }
}
