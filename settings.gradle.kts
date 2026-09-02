// The Gradle build lives at the repository root and the app is a module of it.
//
// Which is what he reached for -- "я створив проект в Idea з базової папки, але
// gradle конфіг не дістає" -- and it is also the conventional Android layout, so
// the intuition and the convention agree. The alternative was to open `app/` as
// its own project, which works and leaves one repository holding two IDE
// projects for no reason.
//
// `deploy/lean.sh` still excludes `app/` from every server, so this file lands
// in a lean checkout pointing at a directory that is not there. Nothing on a
// server runs Gradle, so that costs nothing -- but it is why this file says so
// out loud rather than leaving somebody to discover it.

pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "hovaysya"
include(":app")
