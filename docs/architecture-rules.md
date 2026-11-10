# Architecture rules as tests

Investigation piloted on a private .NET project. The question: how to describe a project's architecture so that (1) the AI checks by itself that a change respects it, and (2) the CI shows an architecture change that the PR did not declare.

Short answer: write the architecture as rules checked on the code by a test library, keep the list of components and their allowed dependencies in one declarative file read by those tests, and make "every component is declared" a rule too. Any structural change then has to touch that file, which the CI can see.

## What the tools check

All of them read the code statically (compiled assembly or import statements) and fail like an ordinary test or lint step.

| | NetArchTest.Rules 1.3 | ArchUnitNET 0.13 | import-linter | dependency-cruiser |
|---|---|---|---|---|
| Stack | .NET | .NET | Python | JS/TS |
| Reads | compiled assembly (Mono.Cecil) | compiled assemblies (Mono.Cecil) | `import` statements | `import`/`require` |
| Rules written in | C# test code | C# test code, or a PlantUML component diagram | `.importlinter` / `pyproject.toml` contracts | `.dependency-cruiser.js` |
| Forbidden dependency | yes, by type or namespace **name prefix** | yes, by any set of types (e.g. "every class derived from a framework base class") | yes (`forbidden`) | yes (`forbidden`, `allowed`) |
| Layers | as pairs of forbidden dependencies | `Layer` objects, or the diagram | yes (`layers`) | as path rules |
| Cycles | no | yes (`Slices().BeFreeOfCycles()`) | between siblings (`acyclic_siblings`, recent versions) | yes (`no-circular`) |
| Independent modules | no | yes (slices) | yes (`independence`) | yes |
| Naming, inheritance, attributes | yes | yes | no | no |
| Immutability | yes (`BeImmutable`, shallow) | yes (on fields and properties, shallow) | no | no |
| Rule selecting nothing | passes | **fails** by default (`WithoutRequiringPositiveResults()` to allow) | fails on an unknown module | — |
| Violation report | failing type names only | type, member and the forbidden target | the import chain with lines | the import path, graph output |
| Known violations baseline | no | no (filter by hand) | `ignore_imports` | `--ignore-known` file |

Others looked at, not retained: NetArchTest.eNhancedEdition (maintained fork with better reports, same model), pytestarch (ArchUnit-style for pytest, smaller), Tach (Python modules with declared `depends_on` and interfaces in `tach.toml`, fast; its vendor's long-term maintenance is uncertain), eslint-plugin-boundaries (same rules as dependency-cruiser, shown in the editor), ts-arch (ArchUnit-style for TS).

## What they cannot check

- Anything outside the language: engine scene files that attach scripts, string node paths (`GetNode("Ui/Label")`), dependency injection by configuration, reflection. A rule holds only for what the compiler or the import graph sees.
- Behaviour: "a simulation is deterministic", "the driver publishes a snapshot each tick". Those stay ordinary tests.
- Deep immutability: a `readonly` field holding a mutable list passes.
- **A new component by itself.** No tool says "this namespace (or package) is new". It has to be a rule of the project: the list of declared components is compared to the components found in the code (see below).
- Intent. The rules say where code may depend; they do not say where new code should go. The AI still reads the architecture page for that.

## .NET prototype

The project is a single assembly (tests included), one namespace per folder. Its architecture is a pattern rather than layers: each feature has a `*Simulation` (plain C#, implements `ISimulation<TCommands, TSnapshot>`), a `*Driver` engine node that advances it, and `*View` nodes that read its immutable snapshot. Only the comment of `ISimulation` said so.

Three rules, in `tests/ArchitectureTest.cs` with ArchUnitNET, run by `dotnet test` with the other tests (no engine runtime needed, about 4 s to load the assemblies):

1. Simulations use no engine class: classes implementing `ISimulation<,>` depend on no class of the engine namespace except its math helpers (value types stay allowed).
2. Snapshots are immutable: no settable property or non-readonly field in a type implementing `ISnapshot`.
3. The display never touches a simulation: `*View` types depend on no simulation class.

Simulations and snapshots are found through their interfaces, so a new one is checked without editing the test. Each rule was proven by making it fail (an engine logging call in a simulation, a settable property on a snapshot, a view method taking a simulation): the report names the type and the forbidden target, e.g. `App.Orders.OrderSimulation does depend on "Engine.Log"`.

Found on the way, not made rules yet: two namespace cycles, and a driver not named `*Driver`.

NetArchTest could express rules 1 and 2 but not as precisely: its dependency check matches names by prefix (forbidding `Engine.Node` also forbids `Engine.Node3D` and `Engine.NodePath`), so the engine classes have to be listed by name, and it reports only the failing type names.

## One source of truth

The architecture lives in one file per project, read by both the tests and the AI:

- **.NET:** a PlantUML component diagram (`docs/architecture.puml`), one component per namespace, one arrow per allowed dependency; ArchUnitNET's `AdhereToPlantUmlDiagram` fails on any dependency not drawn. Rules that a diagram cannot say (no engine class in simulations, immutability) stay as named tests in `tests/ArchitectureTest.cs`.
- **Python:** the import-linter contracts in `.importlinter`, one `allowed` contract per child of each root package and one for its `__init__`, each listing the components it may import (a custom contract type in `.github/scripts/architecture.py`); with several root packages, their components form one graph: an import from one to another must be allowed. A folder of Python code without `__init__.py` under the root package fails the check rather than passing unchecked: grimp, which import-linter builds its graph with, skips it.
- **Rust:** a PlantUML component diagram (`docs/architecture.puml`, header `' stack: rust`), one component per crate of the Cargo workspace, one arrow per allowed dependency (normal and build, not dev). `.github/scripts/architecture.py` checks it against `cargo metadata --no-deps`: a Python script rather than a Rust test, so no PlantUML parser and no test crate. Cargo enforces the edges between crates; modules inside a crate are not components.
  - `<<restricted>>` marks a crate (e.g. the domain) whose direct external dependencies are an allowlist: only the external crates drawn (`<<external>>`). The other crates are free in their external dependencies. An allowlist rather than a denylist, which a new crate such as winit would pass.
- **Kotlin:** a PlantUML component diagram (`docs/architecture.puml`, header `' stack: kotlin`, `' root:` and `' sources:` lines), one component per package right under the root package, sub-packages included, one arrow per allowed dependency; ArchUnit's `adhereToPlantUmlDiagram` in `ArchitectureTest.kt` fails on any dependency not drawn, and `.github/scripts/architecture.py` checks that every package of the sources (`.kt` and `.java`) is declared. One Gradle module; several are not covered yet.
- **JS/TS:** `docs/architecture.json` (`"stack": "js"`): the `roots`, the folders to `exclude`, and each component (a folder right under a root) with the components it may import. `.github/scripts/architecture.py` checks it against the imports dependency-cruiser resolves (`.dependency-cruiser.cjs` holds only how to read them: node_modules, `tsconfig.json`), so the script, not dependency-cruiser rules, is the one checker, testable without Node. A source file dependency-cruiser does not read (TypeScript without a compiler it supports) fails the check rather than passing unchecked. Test files may import any component.

In every stack, `.github/scripts/architecture.py` also fails when the allowed dependencies form a cycle between components: the code can only use allowed dependencies, so checking the declaration covers the code, with one implementation and one message for all stacks. The rule is on in every project; a known cycle is admitted by naming exactly its components on an `allowed cycle` line of the architecture file (`' allowed cycle: Shop.A Shop.B`, `# allowed cycle:` in `.importlinter`, `"allowed_cycles"` in `architecture.json`), and an admitted cycle that is gone fails, so the list only shrinks.

`AGENTS.md` points to that file and to the architecture tests, and says that changing either is an architecture change to be approved by the user. The AI checks a change by running the tests; it does not have to remember prose.

A project test makes new components visible: the components found in the code (namespaces of `scripts/`, top-level packages, `src/` folders) must equal the components declared in the file. A new folder fails the test until it is declared, so it cannot appear silently.

## Undeclared changes in CI

With the above, every structural change touches the architecture file or the architecture tests: a new component fails the declaration test, a new dependency between components fails the diagram or contract check. The CI then only needs a path rule: a PR whose diff touches those files is an architecture change; it must say so in its description (its `## Architecture changes` section, see `docs/pr-description.md`) and is never merged without review (`docs/auto-merge.md`). Done with manifests and top-level folders (`docs/pr-description.md`). Weakening a rule (a known-violation entry, `WithoutRequiringPositiveResults`) is a change of the same files, so it is flagged the same way.

## Recommendation

| Stack | Tool | Source of truth |
|---|---|---|
| .NET | ArchUnitNET | PlantUML diagram + `ArchitectureTest.cs` |
| Python | import-linter | contracts in `.importlinter` |
| Kotlin (meteo) | ArchUnit | PlantUML diagram + `ArchitectureTest.kt` |
| Rust | `.github/scripts/architecture.py` over `cargo metadata` | PlantUML diagram of the workspace crates |
| JS/TS | `.github/scripts/architecture.py` over dependency-cruiser | `docs/architecture.json` |

Each with the "every component declared" test, and the CI path rule above. `core:project-init` sets up the .NET, Python, JS/TS, Rust and Kotlin ones.
