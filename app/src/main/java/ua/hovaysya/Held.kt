package ua.hovaysya

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

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
