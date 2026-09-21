package ua.hovaysya

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * What the app already knows, kept above the tabs.
 *
 * The tabs are a `when` over an index, so switching one destroys the other's
 * composition and every `remember` inside it. Each screen therefore started
 * from nothing and drew an empty tab until its request came back -- which he
 * caught by doing the obvious thing: "при швидких переключеннях між табами стає
 * видно, що дані не встигають завантажитись і таба стоїть пуста".
 *
 * Worse than a flicker, because of what the emptiness says. The feed's empty
 * line is "За останні 30 хвилин тихо" and the headline's is "…": on a tab that
 * exists to report an air raid, forgetting is indistinguishable from calm. An
 * app should not be able to say "quiet" because it has stopped knowing.
 *
 * So the state lives here, for the life of the process, and a request updates
 * it instead of replacing it. Refreshing on open stays -- that part was right,
 * and it is why this is a cache and not a store: whatever is here is the last
 * answer, shown immediately, and corrected a moment later.
 *
 * A plain object rather than a `ViewModel`, because a `ViewModel` would be the
 * first dependency outside the compiler's own libraries this app has needed,
 * and it would buy one thing -- being cleared with the Activity -- that is
 * precisely what is not wanted here.
 *
 * `mutableStateOf` and not plain fields: these are read during composition, and
 * a field nobody is subscribed to would keep the screen on the first value it
 * ever saw.
 */
object Held {

    // --- the main screen ------------------------------------------------------
    var screen by mutableStateOf<Screen?>(null)
    var health by mutableStateOf<Health?>(null)
    var problem by mutableStateOf<String?>(null)

    // --- the doorbell ---------------------------------------------------------
    /**
     * Bumped whenever the server's answer has actually changed.
     *
     * `AlertService` holds one long poll open against `/state?wait=30` and hears
     * within a second; the feeds used to sit on private timers of fifteen and
     * twenty seconds and never be told. His words: "в мене враження що сервер
     * оновлюється швидше ніж в додатку" -- and he had started flicking between
     * tabs to force a refresh, which only bought extra requests.
     *
     * A counter rather than a flag, so a screen that was not listening at the
     * moment it rang can still see that the number is not the one it remembers.
     *
     * A `StateFlow` and not snapshot state, which the tests settled: a waiter
     * parked on `snapshotFlow` wakes only when apply notifications are
     * dispatched, and with the feed's own shell composed around it that did not
     * happen at all. The doorbell is an event, not something the screen draws,
     * so it has no business depending on when Compose next draws a frame.
     */
    private val rings = MutableStateFlow(0)

    /** The count to wait on. Read it before a request, wait on it after. */
    val pulse: StateFlow<Int> get() = rings

    /** Something changed up there; whoever is showing a feed should ask again. */
    fun ring() {
        rings.value += 1
    }

    // --- what Ховайся said ----------------------------------------------------
    var said by mutableStateOf<List<Verdict>>(emptyList())
    var saidProblem by mutableStateOf<String?>(null)

    // --- every channel --------------------------------------------------------
    var posts by mutableStateOf<List<Post>>(emptyList())
    var postsProblem by mutableStateOf<String?>(null)

    /**
     * Forget all of it, which is only right when the phone is forgetting who it
     * is. Called from `Store.forget` rather than from the screen that offers it,
     * so registering again cannot inherit the previous person's night -- their
     * ring, their raid, their lines, decided from a home that is not this one.
     */
    fun clear() {
        screen = null
        health = null
        problem = null
        said = emptyList()
        saidProblem = null
        posts = emptyList()
        postsProblem = null
    }
}
