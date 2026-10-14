pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "PyxpoApp"
include(":app")
// Native modules listed in [tool.pyxpo] modules are linked by pyxpo (regenerated on every build).
apply(from = "pyxpo-gen/modules.settings.gradle.kts")
