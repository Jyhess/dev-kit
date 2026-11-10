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
/// Changing the diagram or this test is an architecture change, approved by the user.
/// </summary>
${class_attribute}public class ArchitectureTest
{
    private const string Root = "${root}";
    private const string Diagram = "docs/architecture.puml";
    private static readonly bool Writing = Environment.GetEnvironmentVariable("ARCHITECTURE_DIAGRAM") == "write";

    private static readonly Lazy<Architecture> Code = new(() => new ArchLoader()
        .LoadAssemblies(System.Reflection.Assembly.Load("${assembly}"))
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

    // Same forms as COMPONENT and ARROW in .github/scripts/architecture.py.
    private static readonly Regex Declaration = new(@"^\s*\[([^\]]+)\]\s*<<");
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
