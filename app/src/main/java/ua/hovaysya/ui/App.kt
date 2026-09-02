package ua.hovaysya.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import ua.hovaysya.Bell
import ua.hovaysya.Store

/**
 * Four screens, and which one is showing.
 *
 * No navigation library: four destinations that never nest and never take an
 * argument are an index, and a back stack over them would be a fiction -- the
 * bottom bar is the whole model.
 *
 * The gate in front of them is the first run. Nothing here can ask the server
 * anything until this phone has a token, and nothing can be decided for the
 * person until they have said where they live.
 */
@Composable
fun App(store: Store, bell: Bell) {
    var registered by remember { mutableStateOf(store.registered) }

    if (!registered) {
        Setup(store) { registered = true }
        return
    }

    var tab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Зараз", "Ховайся", "Канали", "Налаштування")

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surfaceVariant) {
                tabs.forEachIndexed { index, label ->
                    NavigationBarItem(
                        selected = tab == index,
                        onClick = { tab = index },
                        // No icons. Four words are unambiguous and an icon set
                        // for "Ховайся feed" versus "all channels" would not be.
                        icon = {},
                        label = { Text(label, style = MaterialTheme.typography.labelSmall) },
                    )
                }
            }
        },
    ) { insets ->
        Box(Modifier.fillMaxSize().padding(insets)) {
            when (tab) {
                0 -> Now(store)
                1 -> HovaysyaFeed(store)
                2 -> ChannelFeed(store)
                else -> Settings(store, bell) { registered = false }
            }
        }
    }
}
