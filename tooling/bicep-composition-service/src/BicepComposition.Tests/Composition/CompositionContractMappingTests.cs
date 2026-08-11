using BicepComposition.Api.Contracts;
using BicepComposition.Core.Composition;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace BicepComposition.Tests.Composition;

public sealed class CompositionContractMappingTests
{
    [Fact]
    public void Compose_result_maps_to_api_contract_with_stats_warnings_and_unresolved_references()
    {
        var composer = new BicepComposer(NullLogger<BicepComposer>.Instance);

        var composeResult = composer.Compose(
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

        var response = new ComposeResponse
        {
            Status = composeResult.Status,
            MergeMode = composeResult.MergeMode,
            Files = composeResult.Files
                .Select(file => new ComposedFileResponse
                {
                    Path = file.Path,
                    Content = file.Content,
                })
                .ToList(),
            Stats = new CompositionStats
            {
                FragmentCount = composeResult.Stats.FragmentCount,
                DeduplicatedParams = composeResult.Stats.DeduplicatedParams,
                DeduplicatedVars = composeResult.Stats.DeduplicatedVars,
                UnresolvedReferenceCount = composeResult.Stats.UnresolvedReferenceCount,
            },
            UnresolvedReferences = composeResult.UnresolvedReferences
                .Select(item => new UnresolvedReferenceResponse
                {
                    SourceSymbol = item.SourceSymbol,
                    SourceResourceId = item.SourceResourceId,
                    TargetResourceId = item.TargetResourceId,
                    ReferenceExpression = item.ReferenceExpression,
                })
                .ToList(),
            Warnings = composeResult.Warnings.ToList(),
        };

        Assert.Equal("ok", response.Status);
        Assert.Equal("ast", response.MergeMode);
        Assert.Equal(2, response.Files.Count);
        Assert.Equal("main.bicep", response.Files[0].Path);
        Assert.Equal("modules/fragment_001_storage.bicep", response.Files[1].Path);
        Assert.Equal(1, response.Stats.FragmentCount);
        Assert.Equal(response.Stats.UnresolvedReferenceCount, response.UnresolvedReferences.Count);
        Assert.Single(response.UnresolvedReferences);
        Assert.Equal("/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/missing", response.UnresolvedReferences[0].TargetResourceId);
        Assert.Contains("resourceId('Microsoft.Storage/storageAccounts', missing.name)", response.UnresolvedReferences[0].ReferenceExpression);
    }
}