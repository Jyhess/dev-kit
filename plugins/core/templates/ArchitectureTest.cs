#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using ArchUnitNET.Domain;
using ArchUnitNET.Loader;
using static ArchUnitNET.Fluent.ArchRuleDefinition;
${framework_using}
namespace ${namespace};

/// <summary>
/// The components of ${root} and their allowed dependencies, drawn in docs/architecture.puml and checked on the
/// compiled code. .github/scripts/architecture.py checks that every namespace of the code is declared there.
/// TestsFollowComponents checks the mechanical rules of docs/design/tests.md on the tests of ${namespace}.
/// Changing the diagram or this test is an architecture change, approved by the user.
/// </summary>
${class_attribute}public class ArchitectureTest
{
    private const string Root = "${root}";
    private const string Diagram = "docs/architecture.puml";
    private const string TestsNamespace = "${namespace}";
    private static readonly bool Writing = Environment.GetEnvironmentVariable("ARCHITECTURE_DIAGRAM") == "write";

    private static readonly Lazy<Architecture> Code = new(() => new ArchLoader()
        .LoadAssemblies(System.Reflection.Assembly.Load("${assembly}"))
        .Build());

    private static readonly Lazy<Architecture> CodeAndTests = new(() => new ArchLoader()
        .LoadAssemblies(new[] { System.Reflection.Assembly.Load("${assembly}"), typeof(ArchitectureTest).Assembly }
            .Distinct().ToArray())
        .Build());

    /// <summary>Checks nothing while WriteDiagram rewrites the arrows (ARCHITECTURE_DIAGRAM=write).</summary>
    ${test_attribute}
    public void AdheresToDiagram()
    {
        if (Writing)
        {
            return;
        }
        var violations = Types().Should().AdhereToPlantUmlDiagram(DiagramPath())
            .Evaluate(Code.Value)
            .Where(result => !result.Passed)
            .Select(result => result.Description)
            .ToList();
        if (violations.Count > 0)
        {
            throw new InvalidOperationException(
                "Dependencies not drawn in " + Diagram + ":\n" + string.Join("\n", violations));
        }
    }

    /// <summary>
    /// Rewrites the arrows of the diagram from the compiled code, between the components declared there by
    /// `python3 .github/scripts/architecture.py --write` (run it first), keeping the other lines. Runs only with
    /// ARCHITECTURE_DIAGRAM=write: every current dependency becomes allowed, so review the diff.
    /// </summary>
    ${test_attribute}
    public void WriteDiagram()
    {
        if (!Writing)
        {
            return;
        }
        var path = DiagramPath();
        var lines = File.ReadAllLines(path);
        var declared = new HashSet<string>(lines.Select(line => Declaration.Match(line))
            .Where(match => match.Success)
            .Select(match => match.Groups[1].Value));
        var arrows = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var type in Code.Value.Types)
        {
            var from = ComponentOf(type.Namespace.FullName);
            if (from == null || !declared.Contains(from))
            {
                continue;
            }
            foreach (var dependency in type.Dependencies)
            {
                var to = ComponentOf(dependency.Target.Namespace.FullName);
                if (to != null && to != from && declared.Contains(to))
                {
                    arrows.Add("[" + from + "] --> [" + to + "]");
                }
            }
        }
        var kept = lines.Where(line => !Arrow.IsMatch(line) && line.Trim() != "@enduml");
        File.WriteAllLines(path, kept.Concat(arrows).Concat(new[] { "@enduml" }));
    }

    /// <summary>
    /// The tests mirror the components: a test type of TestsNamespace.X(.*) tests the component ${root}.X, or the
    /// root component when X is the last segment of ${root} and not a component; none sits in TestsNamespace itself.
    /// A test uses only the slow dependencies (the namespaces of the `' slow:` header lines of the diagram) its
    /// component uses, itself or through the components it uses.
    /// </summary>
    ${test_attribute}
    public void TestsFollowComponents()
    {
        if (Writing)
        {
            return;
        }
        var slow = File.ReadAllLines(DiagramPath()).Select(line => SlowLine.Match(line)).Where(match => match.Success)
            .SelectMany(match => match.Groups[1].Value.Split(' ', StringSplitOptions.RemoveEmptyEntries)).ToList();
        var types = CodeAndTests.Value.Types.ToList();
        var direct = new Dictionary<string, HashSet<string>>();
        var edges = new Dictionary<string, HashSet<string>>();
        foreach (var type in types.Where(type => !IsTest(type.Namespace.FullName)))
        {
            var from = ComponentOf(type.Namespace.FullName);
            if (from == null)
            {
                continue;
            }
            var uses = direct.TryGetValue(from, out var found) ? found : direct[from] = new HashSet<string>();
            var reaches = edges.TryGetValue(from, out var known) ? known : edges[from] = new HashSet<string>();
            foreach (var dependency in type.Dependencies)
            {
                var target = dependency.Target.Namespace.FullName;
                uses.UnionWith(SlowOf(target, slow));
                var to = IsTest(target) ? null : ComponentOf(target);
                if (to != null && to != from)
                {
                    reaches.Add(to);
                }
            }
        }
        var reach = direct.Keys.ToDictionary(component => component, component => Reached(component, direct, edges));
        var violations = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var type in types.Where(type => IsTest(type.Namespace.FullName)))
        {
            if (type.FullName.StartsWith(typeof(ArchitectureTest).FullName!))
            {
                continue;
            }
            if (type.Namespace.FullName == TestsNamespace)
            {
                violations.Add(type.FullName + ": test at the root of " + TestsNamespace
                               + ", move it to the namespace of the component it tests");
                continue;
            }
            var component = TestedComponent(type.Namespace.FullName, reach.Keys);
            if (!reach.TryGetValue(component, out var allowed))
            {
                violations.Add(type.FullName + ": its namespace mirrors no component (" + component + " has no code)");
                continue;
            }
            foreach (var dependency in type.Dependencies)
            {
                var target = dependency.Target.Namespace.FullName;
                var used = new HashSet<string>(SlowOf(target, slow));
                var to = IsTest(target) ? null : ComponentOf(target);
                if (to != null && reach.TryGetValue(to, out var through))
                {
                    used.UnionWith(through);
                }
                foreach (var name in used.Where(name => !allowed.Contains(name)))
                {
                    violations.Add(type.FullName + " uses " + name + ", a slow dependency " + component + " does not use");
                }
            }
        }
        if (violations.Count > 0)
        {
            throw new InvalidOperationException(
                "Tests not following docs/design/tests.md:\n" + string.Join("\n", violations));
        }
    }

    private static bool IsTest(string ns) => ns == TestsNamespace || ns.StartsWith(TestsNamespace + ".");

    private static string TestedComponent(string ns, IEnumerable<string> components)
    {
        var name = ns.Substring(TestsNamespace.Length + 1).Split('.')[0];
        var component = Root + "." + name;
        return !components.Contains(component) && name == Root.Split('.').Last() ? Root : component;
    }

    private static IEnumerable<string> SlowOf(string ns, IEnumerable<string> slow) =>
        slow.Where(name => ns == name || ns.StartsWith(name + "."));

    private static HashSet<string> Reached(string start, Dictionary<string, HashSet<string>> direct,
        Dictionary<string, HashSet<string>> edges)
    {
        var seen = new HashSet<string> { start };
        var todo = new Stack<string>(seen);
        var found = new HashSet<string>();
        while (todo.Count > 0)
        {
            var current = todo.Pop();
            found.UnionWith(direct.TryGetValue(current, out var uses) ? uses : Enumerable.Empty<string>());
            foreach (var next in edges.TryGetValue(current, out var targets) ? targets : Enumerable.Empty<string>())
            {
                if (seen.Add(next))
                {
                    todo.Push(next);
                }
            }
        }
        return found;
    }

    // Same forms as COMPONENT, ARROW and SLOW in .github/scripts/architecture.py.
    private static readonly Regex Declaration = new(@"^\s*\[([^\]]+)\]\s*<<");
    private static readonly Regex SlowLine = new(@"^\s*'\s*slow:(.*)$$");
    private static readonly Regex Arrow = new(@"^\s*\[[^\]]+\]\s*[-.]+(?:\w+[-.]+)?>\s*\[[^\]]+\]\s*$$");

    private static string? ComponentOf(string ns)
    {
        if (ns == Root)
        {
            return Root;
        }
        return ns.StartsWith(Root + ".") ? Root + "." + ns.Substring(Root.Length + 1).Split('.')[0] : null;
    }

    private static string DiagramPath()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir != null; dir = dir.Parent)
        {
            var path = Path.Combine(dir.FullName, Diagram);
            if (File.Exists(path))
            {
                return path;
            }
        }
        throw new FileNotFoundException(Diagram + " not found above " + AppContext.BaseDirectory);
    }
}
