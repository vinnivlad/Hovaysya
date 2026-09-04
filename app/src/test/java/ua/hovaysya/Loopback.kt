package ua.hovaysya

import java.io.Closeable
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket

/**
 * An HTTP server small enough to be a test fixture.
 *
 * The parsers in `Api` are lambdas inside its suspend functions, so the only
 * way to reach one is to let it make a request. That needs a server, and the
 * two obvious ways to get one are both closed: `com.sun.net.httpserver` is not
 * in the `android.jar` that unit tests compile against, and MockWebServer is a
 * dependency this app does not otherwise have.
 *
 * `ServerSocket` is in `android.jar`, and HTTP over one connection is a request
 * line, some headers, a blank line, and the same going back. Thirty lines
 * against a dependency is the right trade here, and it keeps the test honest in
 * a way a mock would not: this is the real `HttpURLConnection` path, headers,
 * status codes, encoding and all.
 */
internal class Loopback : Closeable {

    private val socket = ServerSocket(0, 0, InetAddress.getByName("127.0.0.1"))

    val base = "http://127.0.0.1:${socket.localPort}"

    /** Every request line seen, so a test can assert what was asked for. */
    val asked = mutableListOf<String>()
    var authorization: String? = null
        private set
    /** The body the client sent, for the endpoints that take one. */
    var received: String? = null
        private set

    private var code = 200
    private var payload = ""

    fun respond(code: Int = 200, payload: String) {
        this.code = code
        this.payload = payload
    }

    private val thread = Thread {
        while (!socket.isClosed) {
            val connection = runCatching { socket.accept() }.getOrNull() ?: return@Thread
            runCatching { connection.use(::answer) }
        }
    }.apply { isDaemon = true; start() }

    private fun answer(connection: Socket) {
        val input = connection.getInputStream().bufferedReader()
        val request = input.readLine() ?: return
        asked.add(request.split(" ").getOrElse(1) { "" })
        // Per request, not cumulative: a test that checks a header is *absent*
        // would otherwise pass on the one before it.
        authorization = null

        var length = 0
        while (true) {
            val header = input.readLine().orEmpty()
            if (header.isBlank()) break
            val name = header.substringBefore(':').trim().lowercase()
            val value = header.substringAfter(':').trim()
            when (name) {
                "authorization" -> authorization = value
                "content-length" -> length = value.toIntOrNull() ?: 0
            }
        }
        // Read it even when nothing asserts on it: a body left in the socket is
        // a client blocked on the flush rather than a test that fails.
        if (length > 0) {
            val body = CharArray(length)
            var read = 0
            while (read < length) {
                val n = input.read(body, read, length - read)
                if (n <= 0) break
                read += n
            }
            received = String(body, 0, read)
        }

        val bytes = payload.toByteArray()
        val head = buildString {
            append("HTTP/1.1 ").append(code).append(" X\r\n")
            append("Content-Type: application/json; charset=utf-8\r\n")
            append("Content-Length: ").append(bytes.size).append("\r\n")
            // One request per connection: nothing here is measuring throughput,
            // and keep-alive would leave the client waiting for a reuse that
            // never comes.
            append("Connection: close\r\n\r\n")
        }
        connection.getOutputStream().apply {
            write(head.toByteArray(Charsets.US_ASCII))
            write(bytes)
            flush()
        }
    }

    override fun close() {
        socket.close()
    }
}
