using BicepComposition.Core.Composition;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace BicepComposition.Tests.Composition;

public sealed class BicepComposerTests
{
    private static BicepComposer CreateComposer() => new(NullLogger<BicepComposer>.Instance);

    [Fact]
    public void Compose_orders_fragments_by_batch_index_and_builds_main_file()
    {
        var composer = CreateComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(2, ["resource-2"], "resource two 'Type@1' = {}", new Dictionary<string, string>()),
            new ComposeInputFragment(1, ["resource-1"], "resource one 'Type@1' = {}", new Dictionary<string, string>())
        ]);

        var files = result.Files.ToArray();
        Assert.Equal("main.bicep", files[0].Path);
        Assert.Equal("modules/fragment_001_type.bicep", files[1].Path);
        Assert.Equal("modules/fragment_002_type.bicep", files[2].Path);
        Assert.Contains("module fragment_001_type './modules/fragment_001_type.bicep'", files[0].Content);
        Assert.Contains("module fragment_002_type './modules/fragment_002_type.bicep'", files[0].Content);
    }

    [Fact]
    public void Compose_partitions_single_fragment_into_multiple_domain_modules()
    {
        var composer = CreateComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                1,
                ["resource-1", "resource-2"],
                "resource stg 'Microsoft.Storage/storageAccounts@2023-01-01' = {}\nresource app 'Microsoft.Web/sites@2023-01-01' = {}",
                new Dictionary<string, string>())
        ]);

        Assert.Contains(result.Files, file => file.Path == "modules/fragment_001_storage.bicep");
        Assert.Contains(result.Files, file => file.Path == "modules/fragment_001_web.bicep");
        var main = result.Files.Single(file => file.Path == "main.bicep").Content;
        Assert.Contains("module fragment_001_storage './modules/fragment_001_storage.bicep'", main);
        Assert.Contains("module fragment_001_web './modules/fragment_001_web.bicep'", main);
    }

    [Fact]
    public void Compose_inlines_shared_param_declarations_into_domain_modules_so_they_are_self_contained()
    {
        var composer = CreateComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                1,
                ["resource-1"],
                "param storageName string = 'mystorage'\nresource stg 'Microsoft.Storage/storageAccounts@2023-01-01' = {\n  name: storageName\n  location: 'westus'\n}",
                new Dictionary<string, string>())
        ]);

        Assert.DoesNotContain(result.Files, file => file.Path == "modules/fragment_001_shared.bicep");
        var storageModule = result.Files.Single(file => file.Path == "modules/fragment_001_storage.bicep").Content;
        Assert.Contains("param storageName string = 'mystorage'", storageModule);
        Assert.Contains("name: storageName", storageModule);
    }

    [Fact]
    public void Compose_deduplicates_exact_match_params_and_vars()
    {
        var composer = CreateComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                1,
                ["resource-1"],
                "param location string = 'eastus'\nparam location string = 'eastus'\nvar suffix = '001'\nvar suffix = '001'",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_001_shared.bicep").Content;
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
        var composer = CreateComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                2,
                ["resource-2"],
                "param location string = 'eastus'\nparam location string = 'westus'\noutput picked string = location",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_002_shared.bicep").Content;
        Assert.Contains("param location string = 'eastus'", module);
        Assert.Contains("param location_batch2 string = 'westus'", module);
        Assert.Contains("output picked string = location_batch2", module);
        Assert.Contains(result.Warnings, warning => warning.Contains("Renamed param 'location' to 'location_batch2'", StringComparison.Ordinal));
    }

    [Fact]
    public void Compose_reports_unresolved_references_when_metadata_target_is_unknown()
    {
        var composer = CreateComposer();

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
        var composer = CreateComposer();

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
        var composer = CreateComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                4,
                ["resource-4"],
                "@description('primary location')\nparam location string = 'eastus'\n@description('primary location')\nparam location string = 'eastus'",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_004_shared.bicep").Content;
        Assert.Equal(1, result.Stats.DeduplicatedParams);
        Assert.Single(result.Warnings.Where(warning => warning.Contains("Deduplicated param 'location'", StringComparison.Ordinal)));
        Assert.Equal(1, module.Split("param location string = 'eastus'").Length - 1);
    }

    [Fact]
    public void Compose_uses_declaration_local_rename_rewriting_without_mutating_declaration_string_literals()
    {
        var composer = CreateComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                2,
                ["resource-2"],
                "param location string = 'eastus'\nvar suffix = location\nparam location string = 'westus'\nvar chosen = '${location}'\noutput named string = chosen",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_002_shared.bicep").Content;
        Assert.Contains("param location_batch2 string = 'westus'", module);
        Assert.Contains("var chosen = '${location_batch2}'", module);
        Assert.DoesNotContain("var chosen = '${location}'", module, StringComparison.Ordinal);
        Assert.Contains("output named string = chosen", module);
        Assert.Contains(result.Warnings, warning => warning.Contains("Renamed param 'location' to 'location_batch2'", StringComparison.Ordinal));
    }

    [Fact]
    public void Compose_rewrites_references_in_multiline_var_declarations_after_deterministic_rename()
    {
        var composer = CreateComposer();

        var result = composer.Compose(
        [
            new ComposeInputFragment(
                3,
                ["resource-3"],
                "param location string = 'eastus'\nparam location string = 'westus'\nvar settings = {\n  location: location\n  literal: 'location'\n}",
                new Dictionary<string, string>())
        ]);

        var module = result.Files.Single(file => file.Path == "modules/fragment_003_shared.bicep").Content;
        Assert.Contains("param location_batch3 string = 'westus'", module);
        Assert.Contains("location_batch3", module);
        Assert.Contains("  literal: 'location'", module);
    }
}