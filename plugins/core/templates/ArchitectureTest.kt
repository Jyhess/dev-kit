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
 * testsFollowComponents checks the mechanical rules of docs/design/tests.md on the unit tests.
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

    /**
     * The tests mirror the components: a test class sits in the package of a component that has code. A test uses
     * only the slow dependencies (the packages of the `' slow:` header lines of the diagram) its component uses, itself
     * or through the components it uses.
     */
    @Test
    fun testsFollowComponents() {
        if (WRITING) {
            return
        }
        val slow = diagram().readLines().mapNotNull { SLOW.find(it)?.groupValues?.get(1) }
            .flatMap { it.split(' ').filter(String::isNotEmpty) }
        val direct = mutableMapOf<String, MutableSet<String>>()
        val edges = mutableMapOf<String, MutableSet<String>>()
        for (javaClass in code) {
            val from = componentOf(javaClass.packageName) ?: continue
            val uses = direct.getOrPut(from) { mutableSetOf() }
            val reaches = edges.getOrPut(from) { mutableSetOf() }
            for (dependency in javaClass.directDependenciesFromSelf) {
                val target = dependency.targetClass.baseComponentType.packageName
                uses.addAll(slowOf(target, slow))
                componentOf(target)?.takeIf { it != from }?.let(reaches::add)
            }
        }
        val reach = direct.keys.associateWith { reached(it, direct, edges) }
        val violations = sortedSetOf<String>()
        for (javaClass in tests) {
            if (javaClass.name.startsWith(ArchitectureTest::class.java.name)) {
                continue
            }
            val component = componentOf(javaClass.packageName)
            val allowed = component?.let { reach[it] }
            if (component == null || allowed == null) {
                violations.add(javaClass.name + ": its package mirrors no component with code")
                continue
            }
            for (dependency in javaClass.directDependenciesFromSelf) {
                val target = dependency.targetClass.baseComponentType.packageName
                val used = slowOf(target, slow).toMutableSet()
                componentOf(target)?.let { reach[it] }?.let(used::addAll)
                for (name in used - allowed) {
                    violations.add(javaClass.name + " uses " + name + ", a slow dependency " + component +
                        " does not use")
                }
            }
        }
        if (violations.isNotEmpty()) {
            throw AssertionError("Tests not following docs/design/tests.md:\n" + violations.joinToString("\n"))
        }
    }

    private companion object {
        const val ROOT = "${root}"
        const val DIAGRAM = "docs/architecture.puml"
        val WRITING = System.getenv("ARCHITECTURE_DIAGRAM") == "write"

        // Same forms as COMPONENT, ARROW and SLOW in .github/scripts/architecture.py.
        val DECLARATION = Regex("""^\s*\[([^\]]+)\]\s*<<""")
        val SLOW = Regex("""^\s*'\s*slow:(.*)$$""")
        val ARROW = Regex("""^\s*\[[^\]]+\]\s*[-.]+(?:\w+[-.]+)?>\s*\[[^\]]+\]\s*""")

        val code: JavaClasses by lazy {
            ClassFileImporter().withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS).importPackages(ROOT)
        }

        val tests: JavaClasses by lazy {
            ClassFileImporter().withImportOption(ImportOption.Predefined.ONLY_INCLUDE_TESTS).importPackages(ROOT)
        }

        fun slowOf(pkg: String, slow: List<String>): List<String> =
            slow.filter { pkg == it || pkg.startsWith("$$it.") }

        fun reached(start: String, direct: Map<String, Set<String>>, edges: Map<String, Set<String>>): Set<String> {
            val seen = mutableSetOf(start)
            val todo = ArrayDeque(seen)
            val found = mutableSetOf<String>()
            while (todo.isNotEmpty()) {
                val current = todo.removeLast()
                found.addAll(direct[current].orEmpty())
                edges[current].orEmpty().filter(seen::add).forEach(todo::addLast)
            }
            return found
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
