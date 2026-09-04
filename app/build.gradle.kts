// The whole build. Compose and AndroidX, and nothing else -- no HTTP client, no
// JSON library, no dependency injection.
//
// That is the same choice the backend made and for the same reason: this has to
// still build in a year, on a machine nobody has prepared, at a moment when
// something is wrong. `HttpURLConnection` and `org.json` are in the platform.
// Four endpoints returning small objects do not repay a dependency that can
// break a build the night it is needed.

import java.time.LocalDate
import java.util.Properties

plugins {
    id("com.android.application") version "8.7.3"
    id("org.jetbrains.kotlin.android") version "2.1.0"
    // Kotlin 2.x moved the Compose compiler into its own plugin.
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"
}

// The version, from the year and the number of commits in it. His scheme, and
// his reason for wanting one: "міняй версію застосунку на кожну готову правку. Я
// сам буду забувати."
//
//     versionCode  20260222      year * 10000 + commits this year
//     versionName  2026.222
//
// Monotonic across a year boundary, which a bare commit count is not: 2026 with
// its five-thousandth commit is 20265000 and the first of 2027 is 20270001.
// Ten thousand commits in one year is the ceiling and it is not close.
//
// Counted rather than typed because a `versionCode` that somebody has to
// remember to raise is one that stays wrong. Android refuses to install an older
// code over a newer one, so a forgotten bump means a phone silently keeping the
// build it has -- which is the same failure as not shipping.
//
// Commits that touch nothing in `app/` still move it. That is deliberate: the
// number is a stamp, not a changelog, and it only has to be different and
// larger.
fun commitsThisYear(): Int? = runCatching {
    val process = ProcessBuilder(
        "git", "rev-list", "--count", "HEAD",
        "--since=${LocalDate.now().year}-01-01")
        .directory(rootProject.projectDir)
        .redirectErrorStream(true)
        .start()
    val text = process.inputStream.bufferedReader().use { it.readText() }
    process.waitFor()
    text.trim().toIntOrNull()
}.getOrNull()

val buildYear = LocalDate.now().year
val buildCount = commitsThisYear()
if (buildCount == null) {
    // Without git the number would be lower than the last real one, so the APK
    // simply will not install over anything -- a loud failure rather than a
    // build that quietly claims to be older than it is.
    logger.lifecycle(
        "  Ховайся: git не відповів — версія буде $buildYear.0, і така збірка " +
        "не встановиться поверх наявної. Це навмисно.")
}

// Where the release key lives, read from a file that is not in git.
//
// The passwords are the reason this is a file and not a constant: this
// repository is public. `keystore.properties` sits beside `local.properties` in
// the root, is gitignored the same way, and points at a keystore under `data/`
// -- which is where every other secret in this project already lives and which
// no server ever receives, because `deploy/lean.sh` carries only tracked
// directories and `data/` is not one.
//
// Absent, the build still configures and `assembleDebug` still works. Only the
// release APK comes out unsigned, which Android refuses to install -- so the
// failure is loud rather than a silently unsigned build handed to somebody.
val signingProperties = Properties().apply {
    val file = rootProject.file("keystore.properties")
    if (file.exists()) {
        file.inputStream().use { load(it) }
    }
}
// Complete, not merely present. A half-filled file would make this true and
// then fail the build on a wrong password, which says nothing about the cause --
// where an absent one says exactly what to do.
val signable = listOf("storeFile", "storePassword", "keyAlias", "keyPassword")
    .all { !signingProperties.getProperty(it).isNullOrBlank() }

android {
    namespace = "ua.hovaysya"
    compileSdk = 35

    defaultConfig {
        applicationId = "ua.hovaysya"
        // 26 is where notification channels and `setBypassDnd` begin, and those
        // are the app: a bell at three in the morning that "не турбувати" does
        // not swallow. Below that there is nothing worth shipping.
        minSdk = 26
        targetSdk = 35
        versionCode = buildYear * 10_000 + (buildCount ?: 0)
        versionName = "$buildYear.${buildCount ?: 0}"
    }

    if (signable) {
        signingConfigs {
            create("release") {
                storeFile = rootProject.file(
                    signingProperties.getProperty("storeFile"))
                storePassword = signingProperties.getProperty("storePassword")
                keyAlias = signingProperties.getProperty("keyAlias")
                keyPassword = signingProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Null rather than the debug key, deliberately. Signing a release
            // with the debug key would install and would tie the app's identity
            // to a keystore that lives in everybody's home directory -- and the
            // identity is the whole point of signing: it is what lets one build
            // replace another instead of demanding an uninstall.
            signingConfig = if (signable) {
                signingConfigs.getByName("release")
            } else {
                null
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    // Unit tests run on this machine's JVM, never on a device, and that is the
    // whole point: they run in the same command that builds, so a fault can be
    // watched failing before it is called fixed. Robolectric supplies the parts
    // of Android that a plain JVM lacks -- `org.json`, `SharedPreferences`, and
    // enough of a window for Compose to lay a list out -- and needs the app's
    // resources on the classpath to do it.
    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }

    buildFeatures {
        compose = true
        // So the app can show which build a phone is running, which is the other
        // half of having a version at all: a number nobody can read from the
        // device answers no question.
        buildConfig = true
    }
}

if (!signable) {
    logger.lifecycle(
        "  Ховайся: keystore.properties немає — release-APK буде без підпису " +
        "і не встановиться. Для debug це не потрібно; див. app/README.md.")
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    val compose = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(compose)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Test only, and never in the APK -- which is what keeps the line in
    // app/README.md about AndroidX-only dependencies true of the app itself.
    // `junit` and `robolectric` are not AndroidX and cannot be: nothing
    // AndroidX runs a JVM test or fakes an Android for it.
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.14.1")
    testImplementation("androidx.test:core-ktx:1.6.1")
    testImplementation(compose)
    testImplementation("androidx.compose.ui:ui-test-junit4")
    // The stub activity `createComposeRule` needs. It lives in the debug
    // manifest because that is the variant the unit tests are built against.
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
