// One module, and the root project is it. Four screens do not need a
// multi-project build, and the flatter tree keeps `deploy/lean.sh` honest: it
// excludes `app` wholesale, so nothing here ever reaches a server.
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
