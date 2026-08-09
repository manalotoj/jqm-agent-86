using BicepComposition.Core.Composition;
using Xunit;

namespace BicepComposition.Tests.Composition;

public sealed class BicepComposerTests
{
    [Fact]
    public void Compose_orders_fragments_by_batch_index_and_builds_main_file()
    {
        var composer = new BicepComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(2, ["resource-2"], "resource two 'Type@1' = {}", new Dictionary<string, string>()),
            new ComposeInputFragment(1, ["resource-1"], "resource one 'Type@1' = {}", new Dictionary<string, string>())
        ]);

        var files = result.Files.ToArray();
        Assert.Equal("main.bicep", files[0].Path);
        Assert.Equal("modules/fragment_001.bicep", files[1].Path);
        Assert.Equal("modules/fragment_002.bicep", files[2].Path);
        Assert.Contains("module fragment_001 './modules/fragment_001.bicep'", files[0].Content);
        Assert.Contains("module fragment_002 './modules/fragment_002.bicep'", files[0].Content);
    }

    [Fact]
    public void Compose_deduplicates_exact_match_params_and_vars()
    {
        var composer = new BicepComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                1,
                ["resource-1"],
                "param location string = 'eastus'\nparam location string = 'eastus'\nvar suffix = '001'\nvar suffix = '001'",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_001.bicep").Content;
        Assert.Equal(1, result.Stats.DeduplicatedParams);
        Assert.Equal(1, result.Stats.DeduplicatedVars);
        Assert.Equal(2, result.Warnings.Count(warning => warning.Contains("Deduplicated", StringComparison.Ordinal)));
        Assert.Equal(1, module.Split("param location string = 'eastus'").Length - 1);
        Assert.Equal(1, module.Split("var suffix = '001'").Length - 1);
        Assert.Contains("param location string = 'eastus'", module);
        Assert.Contains("var suffix = '001'", module);
    }

    [Fact]
    public void Compose_renames_semantic_collisions_and_rewrites_references()
    {
        var composer = new BicepComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                2,
                ["resource-2"],
                "param location string = 'eastus'\nparam location string = 'westus'\noutput picked string = location",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_002.bicep").Content;
        Assert.Contains("param location string = 'eastus'", module);
        Assert.Contains("param location_batch2 string = 'westus'", module);
        Assert.Contains("output picked string = location_batch2", module);
        Assert.Contains(result.Warnings, warning => warning.Contains("Renamed param 'location' to 'location_batch2'", StringComparison.Ordinal));
    }

    [Fact]
    public void Compose_reports_unresolved_references_when_metadata_target_is_unknown()
    {
        var composer = new BicepComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                1,
                ["/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/stg1"],
                "resource stg 'Microsoft.Storage/storageAccounts@2023-01-01' = {}\nvar blobId = resourceId('Microsoft.Storage/storageAccounts', missing.name)",
                new Dictionary<string, string>
                {
                    ["ref:missing"] = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/missing"
                })
        ]);

        Assert.Single(result.UnresolvedReferences);
        Assert.Equal(1, result.Stats.UnresolvedReferenceCount);
        Assert.Equal("/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/missing", result.UnresolvedReferences.Single().TargetResourceId);
    }

    [Fact]
    public void Compose_emits_compiler_warnings_for_invalid_bicep_input()
    {
        var composer = new BicepComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                7,
                ["resource-7"],
                "param location string = 'eastus'\nresource broken 'Microsoft.Storage/storageAccounts@2023-01-01' = {\n  name: 'oops'",
                new Dictionary<string, string>())
        ]);

        Assert.Contains(result.Warnings, warning => warning.Contains("Bicep compiler input diagnostic", StringComparison.Ordinal));
        Assert.Contains(result.Warnings, warning => warning.Contains("fragment 007", StringComparison.Ordinal));
    }

    [Fact]
    public void Compose_uses_syntax_backed_declaration_matching_for_multiline_param_deduplication()
    {
        var composer = new BicepComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                4,
                ["resource-4"],
                "@description('primary location')\nparam location string = 'eastus'\n@description('primary location')\nparam location string = 'eastus'",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_004.bicep").Content;
        Assert.Equal(1, result.Stats.DeduplicatedParams);
        Assert.Single(result.Warnings.Where(warning => warning.Contains("Deduplicated param 'location'", StringComparison.Ordinal)));
        Assert.Equal(1, module.Split("param location string = 'eastus'").Length - 1);
    }

    [Fact]
    public void Compose_uses_declaration_local_rename_rewriting_without_mutating_declaration_string_literals()
    {
        var composer = new BicepComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                2,
                ["resource-2"],
                "param location string = 'eastus'\nvar suffix = location\nparam location string = 'westus'\nvar chosen = '${location}'\noutput named string = chosen",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_002.bicep").Content;
        Assert.Contains("param location_batch2 string = 'westus'", module);
        Assert.Contains("var chosen = '${location_batch2}'", module);
        Assert.DoesNotContain("var chosen = '${location}'", module, StringComparison.Ordinal);
        Assert.Contains("output named string = chosen", module);
        Assert.Contains(result.Warnings, warning => warning.Contains("Renamed param 'location' to 'location_batch2'", StringComparison.Ordinal));
    }

    [Fact]
    public void Compose_rewrites_references_in_multiline_var_declarations_after_deterministic_rename()
    {
        var composer = new BicepComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                3,
                ["resource-3"],
                "param location string = 'eastus'\nparam location string = 'westus'\nvar settings = {\n  location: location\n  literal: 'location'\n}",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_003.bicep").Content;
        Assert.Contains("param location_batch3 string = 'westus'", module);
        Assert.Contains("location_batch3", module);
        Assert.Contains("  literal: 'location'", module);
    }
}