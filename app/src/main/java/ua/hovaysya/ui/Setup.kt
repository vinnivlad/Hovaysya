package ua.hovaysya.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ua.hovaysya.Gazetteer
import ua.hovaysya.Place
import ua.hovaysya.Secret
import ua.hovaysya.Store

/**
 * The first run, which is the only time this app asks for anything.
 *
 * Two questions and no account. The phone makes its own secret and sends only
 * the hash of it, so nothing that could impersonate this device ever leaves it,
 * and the name is a label for the log rather than a credential -- which is why
 * it can be anything and why a repeat is answered with a suffix instead of a
 * refusal.
 *
 * The district is the one thing that cannot be defaulted. Every decision this
 * system makes resolves against it, and a wrong guess is worse than a question.
 */
@Composable
fun Setup(store: Store, done: () -> Unit) {
    var step by remember { mutableStateOf(0) }

    when (step) {
        0 -> TakeMeIn(store) { step = 1 }
        else -> ChooseHome(store, done)
    }
}

@Composable
private fun TakeMeIn(store: Store, next: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var base by remember { mutableStateOf(store.base) }
    var showServer by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var problem by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Ховайся", style = MaterialTheme.typography.displayLarge)
        Spacer(Modifier.height(8.dp))
        Text(
            "Будить тільки тоді, коли це стосується тебе.",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(32.dp))

        OutlinedTextField(
            value = name,
            onValueChange = { name = it.take(24) },
            label = { Text("Як тебе звати") },
            supportingText = {
                Text("Це підпис у логу, не пароль. Можна будь-що.")
            },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        if (showServer) {
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = base,
                onValueChange = { base = it },
                label = { Text("Сервер") },
                // The emulator reaches its host at 10.0.2.2, which is the only
                // reason this field exists.
                supportingText = { Text("З емулятора локальний — http://10.0.2.2:8080") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        } else {
            TextButton(onClick = { showServer = true }) { Text("Інший сервер") }
        }

        problem?.let {
            Spacer(Modifier.height(12.dp))
            Text(it, color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium)
        }

        Spacer(Modifier.height(24.dp))
        Button(
            enabled = !busy && name.isNotBlank(),
            onClick = {
                busy = true
                problem = null
                scope.launch {
                    val secret = Secret.make()
                    val result = runCatching {
                        store.base = base
                        // Only the hash goes over the wire, and this is the
                        // whole of the security model: the server can recognise
                        // this phone and cannot become it.
                        store.api().register(Secret.hash(secret), name.trim())
                    }
                    busy = false
                    result.onSuccess { stored ->
                        store.secret = secret
                        store.name = stored
                        next()
                    }.onFailure { problem = it.message ?: "не вийшло" }
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (busy) "…" else "Далі")
        }
    }
}

@Composable
private fun ChooseHome(store: Store, done: () -> Unit) {
    var gazetteer by remember { mutableStateOf<Gazetteer?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }
    var chosen by remember { mutableStateOf<Place?>(null) }
    var radius by remember { mutableStateOf(6f) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        runCatching { store.api().gazetteer() }
            .onSuccess { gazetteer = it }
            .onFailure { problem = it.message ?: "не вийшло" }
    }

    val ready = gazetteer
    if (ready == null) {
        Column(
            Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            problem?.let {
                Text(it, color = MaterialTheme.colorScheme.error)
            } ?: CircularProgressIndicator()
        }
        return
    }

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(24.dp, 24.dp, 24.dp, 8.dp)) {
            Text("Де ти живеш", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(4.dp))
            Text(
                "Усе інше рахується від цієї точки.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        LazyColumn(Modifier.weight(1f)) {
            // Grouped in the gazetteer's own order, so "мій район" means to the
            // person what it means to the rules.
            ready.tiers.forEach { tier ->
                val inTier = ready.homes().filter { it.tier == tier }
                if (inTier.isEmpty()) return@forEach
                item(key = "tier-$tier") {
                    Text(
                        tierWord(tier),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(24.dp, 16.dp, 24.dp, 6.dp),
                    )
                }
                items(inTier, key = { it.name }) { place ->
                    val picked = chosen?.name == place.name
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .padding(16.dp, 2.dp)
                            .clip(RoundedCornerShape(10.dp))
                            .background(
                                if (picked) MaterialTheme.colorScheme.surfaceVariant
                                else MaterialTheme.colorScheme.background
                            )
                            .clickable { chosen = place }
                            .padding(12.dp),
                    ) {
                        Text(
                            place.name,
                            style = MaterialTheme.typography.bodyLarge,
                            fontWeight = if (picked) FontWeight.SemiBold else null,
                        )
                    }
                }
            }
        }

        Column(Modifier.padding(24.dp, 8.dp, 24.dp, 24.dp)) {
            Text(
                "Ближнє коло: ${"%.0f".format(radius)} км",
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                "Про що говорити голосно, а не тихо.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Slider(
                value = radius,
                onValueChange = { radius = it },
                valueRange = 2f..15f,
                steps = 12,
            )
            problem?.let {
                Text(it, color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium)
            }
            Spacer(Modifier.height(8.dp))
            Button(
                enabled = !busy && chosen != null,
                onClick = {
                    busy = true
                    problem = null
                    scope.launch {
                        val result = runCatching {
                            store.api().saveConfig(
                                mapOf(
                                    "home" to chosen!!.name,
                                    "radius_km" to radius.toDouble(),
                                )
                            )
                        }
                        busy = false
                        result.onSuccess { done() }
                            .onFailure { problem = it.message ?: "не вийшло" }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (busy) "…" else "Готово")
            }
        }
    }
}

/** The tier names, said the way he says them. */
internal fun tierWord(tier: String): String = when (tier) {
    "my-area" -> "МІЙ РАЙОН"
    "my-district" -> "ПОРУЧ"
    "city" -> "КИЇВ"
    "oblast" -> "ОБЛАСТЬ"
    else -> tier.uppercase()
}
