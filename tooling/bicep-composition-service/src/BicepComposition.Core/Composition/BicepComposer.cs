using System.Text;
using System.Text.RegularExpressions;
using Bicep.Core.Diagnostics;
using Bicep.Core.Parsing;
using Bicep.Core.Syntax;
using Bicep.Core.Text;

namespace BicepComposition.Core.Composition;

public sealed class BicepComposer
{
    private static readonly Regex DeclarationRegex = new(
        "^(?<indent>\\s*)(?<kind>param|var|resource)\\s+(?<name>[A-Za-z_][A-Za-z0-9_]*)\\b",
        RegexOptions.Compiled);

    private static readonly Regex ResourceReferenceRegex = new(
        "resourceId\\('(?<type>[^']+)'\\s*,\\s*(?<name>[A-Za-z_][A-Za-z0-9_]*)\\.name\\)",
        RegexOptions.Compiled);

    private static readonly Regex IdentifierRegex = new(
        "\\b[A-Za-z_][A-Za-z0-9_]*\\b",
        RegexOptions.Compiled);

    public ComposeResult Compose(IReadOnlyCollection<ComposeInputFragment> fragments)
    {
        ArgumentNullException.ThrowIfNull(fragments);

        var orderedFragments = fragments.OrderBy(fragment => fragment.BatchIndex).ToArray();
        var files = new List<ComposeOutputFile>();
        var warnings = new List<string>();
        var unresolvedReferences = new List<ComposeUnresolvedReference>();
        var deduplicatedParams = 0;
        var deduplicatedVars = 0;
        var knownResourceIds = BuildKnownResourceIds(orderedFragments);

        foreach (var fragment in orderedFragments)
        {
            warnings.AddRange(CollectCompilerDiagnostics(fragment, fragment.BicepText, "input"));

            var transformed = TransformFragment(
                fragment,
                warnings,
                unresolvedReferences,
                knownResourceIds,
                ref deduplicatedParams,
                ref deduplicatedVars);

            warnings.AddRange(CollectCompilerDiagnostics(fragment, transformed, "output"));

            files.Add(new ComposeOutputFile($"modules/fragment_{fragment.BatchIndex:000}.bicep", transformed));
        }

        files.Insert(0, new ComposeOutputFile("main.bicep", BuildMainFile(orderedFragments)));

        return new ComposeResult(
            Status: "ok",
            MergeMode: "ast",
            Files: files,
            Stats: new ComposeStats(
                FragmentCount: orderedFragments.Length,
                DeduplicatedParams: deduplicatedParams,
                DeduplicatedVars: deduplicatedVars,
                UnresolvedReferenceCount: unresolvedReferences.Count),
            UnresolvedReferences: unresolvedReferences,
            Warnings: warnings);
    }

    private static HashSet<string> BuildKnownResourceIds(IEnumerable<ComposeInputFragment> fragments)
    {
        return fragments
            .SelectMany(fragment => fragment.SourceResourceIds)
            .Where(resourceId => !string.IsNullOrWhiteSpace(resourceId))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
    }

    private static string TransformFragment(
        ComposeInputFragment fragment,
        List<string> warnings,
        List<ComposeUnresolvedReference> unresolvedReferences,
        HashSet<string> knownResourceIds,
        ref int deduplicatedParams,
        ref int deduplicatedVars)
    {
        var normalizedText = fragment.BicepText.Replace("\r\n", "\n", StringComparison.Ordinal);
        var lines = normalizedText.Split('\n');
        var syntaxDeclarations = ParseTopLevelDeclarations(normalizedText);
        var declarations = new Dictionary<string, DeclarationState>(StringComparer.Ordinal);
        var emittedLines = new List<string>();

        for (var lineIndex = 0; lineIndex < lines.Length; lineIndex++)
        {
            if (syntaxDeclarations.StartLines.TryGetValue(lineIndex, out var syntaxDeclaration))
            {
                lineIndex = HandleSyntaxDeclaration(
                    fragment,
                    syntaxDeclaration,
                    declarations,
                    emittedLines,
                    warnings,
                    unresolvedReferences,
                    knownResourceIds,
                    deduplicatedParams,
                    deduplicatedVars,
                    out deduplicatedParams,
                    out deduplicatedVars);
                continue;
            }

            if (syntaxDeclarations.CoveredLines.Contains(lineIndex))
            {
                continue;
            }

            var line = lines[lineIndex];
            var match = DeclarationRegex.Match(line);
            if (!match.Success)
            {
                var rewrittenLine = RewriteReferences(line, declarations);
                emittedLines.Add(rewrittenLine);
                CollectUnresolvedReferences(fragment, rewrittenLine, unresolvedReferences, knownResourceIds, declarations);
                continue;
            }

            var kind = match.Groups["kind"].Value;
            var originalName = match.Groups["name"].Value;
            var declarationBody = line[(match.Index + match.Length)..].Trim();

            if (declarations.TryGetValue(originalName, out var existing))
            {
                if (string.Equals(existing.Kind, kind, StringComparison.Ordinal) &&
                    string.Equals(existing.Body, declarationBody, StringComparison.Ordinal))
                {
                    if (string.Equals(kind, "param", StringComparison.Ordinal))
                    {
                        deduplicatedParams++;
                    }
                    else if (string.Equals(kind, "var", StringComparison.Ordinal))
                    {
                        deduplicatedVars++;
                    }

                    warnings.Add($"Deduplicated {kind} '{originalName}' in fragment {fragment.BatchIndex}.");
                    continue;
                }

                var renamed = $"{originalName}_batch{fragment.BatchIndex}";
                var renamedLine = ReplaceFirstIdentifier(line, originalName, renamed);
                declarations[originalName] = existing with
                {
                    Aliases = existing.Aliases.Concat(new[] { new Alias(originalName, renamed) }).ToArray(),
                };
                var rewrittenRenamedLine = RewriteReferences(renamedLine, declarations, originalName, renamed);
                emittedLines.Add(rewrittenRenamedLine);
                CollectUnresolvedReferences(fragment, rewrittenRenamedLine, unresolvedReferences, knownResourceIds, declarations);
                warnings.Add($"Renamed {kind} '{originalName}' to '{renamed}' in fragment {fragment.BatchIndex} due to a semantic collision.");
                continue;
            }

            declarations[originalName] = new DeclarationState(kind, declarationBody, Array.Empty<Alias>());
            var rewrittenDeclarationLine = RewriteReferences(line, declarations);
            emittedLines.Add(rewrittenDeclarationLine);
            CollectUnresolvedReferences(fragment, rewrittenDeclarationLine, unresolvedReferences, knownResourceIds, declarations);
        }

        return string.Join(Environment.NewLine, emittedLines);
    }

    private static int HandleSyntaxDeclaration(
        ComposeInputFragment fragment,
        SyntaxDeclaration syntaxDeclaration,
        Dictionary<string, DeclarationState> declarations,
        List<string> emittedLines,
        List<string> warnings,
        List<ComposeUnresolvedReference> unresolvedReferences,
        HashSet<string> knownResourceIds,
        int currentDeduplicatedParams,
        int currentDeduplicatedVars,
        out int deduplicatedParams,
        out int deduplicatedVars)
    {
        deduplicatedParams = currentDeduplicatedParams;
        deduplicatedVars = currentDeduplicatedVars;

        var originalName = syntaxDeclaration.Name;
        var kind = syntaxDeclaration.Kind;
        var declarationText = syntaxDeclaration.Text;
        var declarationBody = syntaxDeclaration.Body;

        if (declarations.TryGetValue(originalName, out var existing))
        {
            if (string.Equals(existing.Kind, kind, StringComparison.Ordinal) &&
                string.Equals(existing.Body, declarationBody, StringComparison.Ordinal))
            {
                if (string.Equals(kind, "param", StringComparison.Ordinal))
                {
                    deduplicatedParams++;
                }
                else if (string.Equals(kind, "var", StringComparison.Ordinal))
                {
                    deduplicatedVars++;
                }

                warnings.Add($"Deduplicated {kind} '{originalName}' in fragment {fragment.BatchIndex}.");
                return syntaxDeclaration.EndLine;
            }

            var renamed = $"{originalName}_batch{fragment.BatchIndex}";
            var renamedDeclaration = ReplaceFirstIdentifier(declarationText, originalName, renamed);
            declarations[originalName] = existing with
            {
                Aliases = existing.Aliases.Concat(new[] { new Alias(originalName, renamed) }).ToArray(),
            };
            var rewrittenRenamedDeclaration = RewriteSyntaxDeclarationText(renamedDeclaration, renamed, declarations, originalName, renamed);
            emittedLines.Add(rewrittenRenamedDeclaration);
            CollectUnresolvedReferences(fragment, rewrittenRenamedDeclaration, unresolvedReferences, knownResourceIds, declarations);
            warnings.Add($"Renamed {kind} '{originalName}' to '{renamed}' in fragment {fragment.BatchIndex} due to a semantic collision.");
            return syntaxDeclaration.EndLine;
        }

        declarations[originalName] = new DeclarationState(kind, declarationBody, Array.Empty<Alias>());
        var rewrittenDeclaration = RewriteSyntaxDeclarationText(declarationText, originalName, declarations);
        emittedLines.Add(rewrittenDeclaration);
        CollectUnresolvedReferences(fragment, rewrittenDeclaration, unresolvedReferences, knownResourceIds, declarations);
        return syntaxDeclaration.EndLine;
    }

    private static ParsedDeclarations ParseTopLevelDeclarations(string normalizedText)
    {
        var parser = new Parser(normalizedText);
        var program = parser.Program();
        var lineStarts = TextCoordinateConverter.GetLineStarts(normalizedText);
        var startLines = new Dictionary<int, SyntaxDeclaration>();
        var coveredLines = new HashSet<int>();

        foreach (var declaration in program.Declarations)
        {
            SyntaxDeclaration? parsed = declaration switch
            {
                ParameterDeclarationSyntax parameter => CreateSyntaxDeclaration("param", parameter.Name.IdentifierName, parameter.Span, normalizedText, lineStarts),
                VariableDeclarationSyntax variable => CreateSyntaxDeclaration("var", variable.Name.IdentifierName, variable.Span, normalizedText, lineStarts),
                _ => null,
            };

            if (parsed is null)
            {
                continue;
            }

            startLines[parsed.StartLine] = parsed;
            for (var line = parsed.StartLine; line <= parsed.EndLine; line++)
            {
                coveredLines.Add(line);
            }
        }

        return new ParsedDeclarations(startLines, coveredLines);
    }

    private static SyntaxDeclaration? CreateSyntaxDeclaration(
        string kind,
        string name,
        TextSpan span,
        string normalizedText,
        IReadOnlyList<int> lineStarts)
    {
        if (span.Position < 0 || span.Position + span.Length > normalizedText.Length)
        {
            return null;
        }

        var text = normalizedText.Substring(span.Position, span.Length);
        var declarationStart = text.IndexOf(kind, StringComparison.Ordinal);
        if (declarationStart < 0)
        {
            return null;
        }

        var bodyStart = text.IndexOf(name, declarationStart, StringComparison.Ordinal);
        if (bodyStart < 0)
        {
            return null;
        }

        bodyStart += name.Length;
        var (startLine, _) = TextCoordinateConverter.GetPosition(lineStarts, span.Position);
        var endOffset = Math.Max(span.Position, span.Position + span.Length - 1);
        var (endLine, _) = TextCoordinateConverter.GetPosition(lineStarts, endOffset);

        return new SyntaxDeclaration(
            Kind: kind,
            Name: name,
            Text: text,
            Body: text[bodyStart..].Trim(),
            StartLine: startLine,
            EndLine: endLine);
    }

    private static string RewriteReferences(
        string line,
        Dictionary<string, DeclarationState> declarations,
        string? renamedOriginal = null,
        string? renamedValue = null)
    {
        var aliasMap = declarations
            .SelectMany(pair => pair.Value.Aliases)
            .ToDictionary(alias => alias.Original, alias => alias.Renamed, StringComparer.Ordinal);

        if (!string.IsNullOrEmpty(renamedOriginal) && !string.IsNullOrEmpty(renamedValue))
        {
            aliasMap[renamedOriginal] = renamedValue;
        }

        return IdentifierRegex.Replace(line, match =>
        {
            var identifier = match.Value;
            return aliasMap.TryGetValue(identifier, out var renamed) ? renamed : identifier;
        });
    }

    private static string RewriteSyntaxDeclarationText(
        string declarationText,
        string declaredName,
        Dictionary<string, DeclarationState> declarations,
        string? renamedOriginal = null,
        string? renamedValue = null)
    {
        var aliasMap = declarations
            .SelectMany(pair => pair.Value.Aliases)
            .ToDictionary(alias => alias.Original, alias => alias.Renamed, StringComparer.Ordinal);

        if (!string.IsNullOrEmpty(renamedOriginal) && !string.IsNullOrEmpty(renamedValue))
        {
            aliasMap[renamedOriginal] = renamedValue;
        }

        if (aliasMap.Count == 0)
        {
            return declarationText;
        }

        var protectedIdentifierIndex = FindDeclaredIdentifierIndex(declarationText, declaredName);
        return RewriteIdentifiersPreservingStringLiterals(declarationText, aliasMap, protectedIdentifierIndex);
    }

    private static int FindDeclaredIdentifierIndex(string declarationText, string declaredName)
    {
        var match = IdentifierRegex.Match(declarationText);
        while (match.Success)
        {
            if (string.Equals(match.Value, declaredName, StringComparison.Ordinal))
            {
                return match.Index;
            }

            match = match.NextMatch();
        }

        return -1;
    }

    private static string RewriteIdentifiersPreservingStringLiterals(
        string text,
        IReadOnlyDictionary<string, string> aliasMap,
        int protectedIdentifierIndex)
    {
        var builder = new StringBuilder(text.Length);
        RewriteSegment(text, 0, text.Length, aliasMap, protectedIdentifierIndex, builder);
        return builder.ToString();
    }

    private static void RewriteSegment(
        string text,
        int start,
        int end,
        IReadOnlyDictionary<string, string> aliasMap,
        int protectedIdentifierIndex,
        StringBuilder builder)
    {
        var index = start;
        while (index < end)
        {
            if (StartsWithTripleQuote(text, index, end))
            {
                index = RewriteStringLiteral(text, index, end, aliasMap, protectedIdentifierIndex, builder, isTripleQuoted: true);
                continue;
            }

            if (text[index] == '\'')
            {
                index = RewriteStringLiteral(text, index, end, aliasMap, protectedIdentifierIndex, builder, isTripleQuoted: false);
                continue;
            }

            if (IsIdentifierStart(text[index]))
            {
                var identifierStart = index;
                index++;
                while (index < end && IsIdentifierPart(text[index]))
                {
                    index++;
                }

                var identifier = text[identifierStart..index];
                if (identifierStart == protectedIdentifierIndex)
                {
                    builder.Append(identifier);
                    continue;
                }

                builder.Append(aliasMap.TryGetValue(identifier, out var renamed) ? renamed : identifier);
                continue;
            }

            builder.Append(text[index]);
            index++;
        }
    }

    private static int RewriteStringLiteral(
        string text,
        int start,
        int end,
        IReadOnlyDictionary<string, string> aliasMap,
        int protectedIdentifierIndex,
        StringBuilder builder,
        bool isTripleQuoted)
    {
        var quoteLength = isTripleQuoted ? 3 : 1;
        builder.Append(text, start, quoteLength);
        var index = start + quoteLength;

        while (index < end)
        {
            if (index + 1 < end && text[index] == '$' && text[index + 1] == '{')
            {
                builder.Append("${");
                index += 2;
                var interpolationStart = index;
                var depth = 1;
                while (index < end && depth > 0)
                {
                    if (StartsWithTripleQuote(text, index, end))
                    {
                        index = SkipStringLiteral(text, index + 3, end, true);
                        continue;
                    }

                    if (text[index] == '\'')
                    {
                        index = SkipStringLiteral(text, index + 1, end, false);
                        continue;
                    }

                    if (index + 1 < end && text[index] == '$' && text[index + 1] == '{')
                    {
                        depth++;
                        index += 2;
                        continue;
                    }

                    if (text[index] == '}')
                    {
                        depth--;
                        if (depth == 0)
                        {
                            break;
                        }
                    }

                    index++;
                }

                RewriteSegment(text, interpolationStart, index, aliasMap, protectedIdentifierIndex, builder);
                if (index < end && text[index] == '}')
                {
                    builder.Append('}');
                    index++;
                }

                continue;
            }

            if ((isTripleQuoted && StartsWithTripleQuote(text, index, end)) || (!isTripleQuoted && text[index] == '\''))
            {
                builder.Append(text, index, quoteLength);
                return index + quoteLength;
            }

            builder.Append(text[index]);
            index++;
        }

        return index;
    }

    private static int SkipStringLiteral(string text, int index, int end, bool isTripleQuoted)
    {
        var quoteLength = isTripleQuoted ? 3 : 1;
        while (index < end)
        {
            if (isTripleQuoted && StartsWithTripleQuote(text, index, end))
            {
                return index + quoteLength;
            }

            if (!isTripleQuoted && text[index] == '\'')
            {
                return index + quoteLength;
            }

            if (index + 1 < end && text[index] == '$' && text[index + 1] == '{')
            {
                index += 2;
                var depth = 1;
                while (index < end && depth > 0)
                {
                    if (StartsWithTripleQuote(text, index, end))
                    {
                        index = SkipStringLiteral(text, index + 3, end, true);
                        continue;
                    }

                    if (text[index] == '\'')
                    {
                        index = SkipStringLiteral(text, index + 1, end, false);
                        continue;
                    }

                    if (index + 1 < end && text[index] == '$' && text[index + 1] == '{')
                    {
                        depth++;
                        index += 2;
                        continue;
                    }

                    if (text[index] == '}')
                    {
                        depth--;
                    }

                    index++;
                }

                continue;
            }

            index++;
        }

        return index;
    }

    private static bool StartsWithTripleQuote(string text, int index, int end) =>
        index + 2 < end && text[index] == '\'' && text[index + 1] == '\'' && text[index + 2] == '\'';

    private static bool IsIdentifierStart(char character) =>
        character == '_' || char.IsLetter(character);

    private static bool IsIdentifierPart(char character) =>
        character == '_' || char.IsLetterOrDigit(character);

    private static void CollectUnresolvedReferences(
        ComposeInputFragment fragment,
        string line,
        List<ComposeUnresolvedReference> unresolvedReferences,
        HashSet<string> knownResourceIds,
        Dictionary<string, DeclarationState> declarations)
    {
        foreach (Match match in ResourceReferenceRegex.Matches(line))
        {
            var targetSymbol = match.Groups["name"].Value;
            var targetResourceId = fragment.Metadata.TryGetValue($"ref:{targetSymbol}", out var metadataTarget)
                ? metadataTarget
                : $"unknown:{targetSymbol}";

            if (knownResourceIds.Contains(targetResourceId))
            {
                continue;
            }

            var rewrittenSymbol = declarations.TryGetValue(targetSymbol, out var state) && state.Aliases.Length > 0
                ? state.Aliases[^1].Renamed
                : targetSymbol;

            unresolvedReferences.Add(new ComposeUnresolvedReference(
                SourceSymbol: rewrittenSymbol,
                SourceResourceId: fragment.SourceResourceIds.FirstOrDefault() ?? string.Empty,
                TargetResourceId: targetResourceId,
                ReferenceExpression: match.Value));
        }
    }

    private static string ReplaceFirstIdentifier(string line, string originalName, string renamed)
    {
        var pattern = $"\\b{Regex.Escape(originalName)}\\b";
        var match = Regex.Match(line, pattern, RegexOptions.None, TimeSpan.FromSeconds(1));
        if (!match.Success)
        {
            return line;
        }

        return string.Concat(
            line.AsSpan(0, match.Index),
            renamed,
            line.AsSpan(match.Index + match.Length));
    }

    private static string BuildMainFile(IEnumerable<ComposeInputFragment> orderedFragments)
    {
        var builder = new StringBuilder();
        builder.AppendLine("// Composed Bicep package.");
        builder.AppendLine();

        foreach (var fragment in orderedFragments)
        {
            var modulePath = $"modules/fragment_{fragment.BatchIndex:000}.bicep";
            builder.AppendLine($"module fragment_{fragment.BatchIndex:000} './{modulePath}' = {{");
            builder.AppendLine($"  name: 'fragment-{fragment.BatchIndex:000}'");
            builder.AppendLine("}");
            builder.AppendLine();
        }

        return builder.ToString();
    }

    private static IReadOnlyCollection<string> CollectCompilerDiagnostics(
        ComposeInputFragment fragment,
        string bicepText,
        string stage)
    {
        var parser = new Parser(bicepText);
        _ = parser.Program();
        var lineStarts = TextCoordinateConverter.GetLineStarts(bicepText);

        return parser.LexingErrorLookup
            .Concat(parser.ParsingErrorLookup)
            .Select(diagnostic => FormatCompilerDiagnostic(fragment, diagnostic, lineStarts, stage))
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    }

    private static string FormatCompilerDiagnostic(
        ComposeInputFragment fragment,
        IDiagnostic diagnostic,
        IReadOnlyList<int> lineStarts,
        string stage)
    {
        var (line, character) = TextCoordinateConverter.GetPosition(lineStarts, diagnostic.Span.Position);
        return $"Bicep compiler {stage} diagnostic in fragment {fragment.BatchIndex:000} at {line + 1}:{character + 1} [{diagnostic.Level}] {diagnostic.Code}: {diagnostic.Message}";
    }

    private sealed record DeclarationState(string Kind, string Body, Alias[] Aliases);

    private sealed record Alias(string Original, string Renamed);

    private sealed record ParsedDeclarations(
        Dictionary<int, SyntaxDeclaration> StartLines,
        HashSet<int> CoveredLines);

    private sealed record SyntaxDeclaration(
        string Kind,
        string Name,
        string Text,
        string Body,
        int StartLine,
        int EndLine);
}

public sealed record ComposeInputFragment(
    int BatchIndex,
    IReadOnlyCollection<string> SourceResourceIds,
    string BicepText,
    IReadOnlyDictionary<string, string> Metadata);

public sealed record ComposeOutputFile(string Path, string Content);

public sealed record ComposeStats(
    int FragmentCount,
    int DeduplicatedParams,
    int DeduplicatedVars,
    int UnresolvedReferenceCount);

public sealed record ComposeUnresolvedReference(
    string SourceSymbol,
    string SourceResourceId,
    string TargetResourceId,
    string ReferenceExpression);

public sealed record ComposeResult(
    string Status,
    string MergeMode,
    IReadOnlyCollection<ComposeOutputFile> Files,
    ComposeStats Stats,
    IReadOnlyCollection<ComposeUnresolvedReference> UnresolvedReferences,
    IReadOnlyCollection<string> Warnings);