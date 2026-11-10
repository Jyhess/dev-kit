package ${root}

import com.tngtech.archunit.core.domain.JavaClasses
import com.tngtech.archunit.core.importer.ClassFileImporter
import com.tngtech.archunit.core.importer.ImportOption
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes
import com.tngtech.archunit.library.plantuml.rules.PlantUmlArchCondition.Configuration.consideringOnlyDependenciesInDiagram
import com.tngtech.archunit.library.plantuml.rules.PlantUmlArchCondition.adhereToPlantUmlDiagram
import java.io.File
${test_import}

/**
 * The components of ${root} and their allowed dependencies, drawn in docs/architecture.puml and checked on the
 * compiled code. .github/scripts/architecture.py checks that every package of the code is declared there.
 * Changing the diagram or this test is an architecture change, approved by the user.
 */
class ArchitectureTest {
    /** Checks nothing while writeDiagram rewrites the arrows (ARCHITECTURE_DIAGRAM=write). */
    @Test
    fun adheresToDiagram() {
        if (WRITING) {
            return
        }
        classes().that().resideInAPackage(ROOT + "..")
            .should(adhereToPlantUmlDiagram(diagram().toURI().toURL(), consideringOnlyDependenciesInDiagram()))
            .check(code)
    }

    /**
     * Rewrites the arrows of the diagram from the compiled code, between the components declared there by
     * `python3 .github/scripts/architecture.py --write` (run it first), keeping the other lines. Runs only with
     * ARCHITECTURE_DIAGRAM=write: every current dependency becomes allowed, so review the diff.
     */
    @Test
    fun writeDiagram() {
        if (!WRITING) {
            return
        }
        val file = diagram()
        val lines = file.readLines()
        val declared = lines.mapNotNull { DECLARATION.find(it)?.groupValues?.get(1) }.toSet()
        val arrows = sortedSetOf<String>()
        for (javaClass in code) {
            val from = componentOf(javaClass.packageName)
            if (from == null || from !in declared) {
                continue
            }
            for (dependency in javaClass.directDependenciesFromSelf) {
                val to = componentOf(dependency.targetClass.baseComponentType.packageName)
                if (to != null && to != from && to in declared) {
                    arrows.add("[" + from + "] --> [" + to + "]")
                }
            }
        }
        val kept = lines.filter { !ARROW.matches(it) && it.trim() != "@enduml" }
        file.writeText((kept + arrows + "@enduml").joinToString("\n", postfix = "\n"))
    }

    private companion object {
        const val ROOT = "${root}"
        const val DIAGRAM = "docs/architecture.puml"
        val WRITING = System.getenv("ARCHITECTURE_DIAGRAM") == "write"

        // Same forms as COMPONENT and ARROW in .github/scripts/architecture.py.
        val DECLARATION = Regex("""^\s*\[([^\]]+)\]\s*<<""")
        val ARROW = Regex("""^\s*\[[^\]]+\]\s*[-.]+(?:\w+[-.]+)?>\s*\[[^\]]+\]\s*""")

        val code: JavaClasses by lazy {
            ClassFileImporter().withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS).importPackages(ROOT)
        }

        fun componentOf(pkg: String): String? = when {
            pkg == ROOT -> ROOT
            pkg.startsWith(ROOT + ".") -> ROOT + "." + pkg.substring(ROOT.length + 1).substringBefore('.')
            else -> null
        }

        /** docs/architecture.puml, from the module folder Gradle runs the tests in, or one of its parents. */
        fun diagram(): File {
            var dir: File? = File("").absoluteFile
            while (dir != null) {
                val file = File(dir, DIAGRAM)
                if (file.isFile) {
                    return file
                }
                dir = dir.parentFile
            }
            throw IllegalStateException(DIAGRAM + " not found above " + File("").absolutePath)
        }
    }
}
