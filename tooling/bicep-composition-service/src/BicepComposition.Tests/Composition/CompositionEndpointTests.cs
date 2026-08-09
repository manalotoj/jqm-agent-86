using System.Net.Http.Json;
using BicepComposition.Api.Contracts;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

namespace BicepComposition.Tests.Composition;

public sealed class CompositionEndpointTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    public CompositionEndpointTests(WebApplicationFactory<Program> factory)
    {
        _factory = factory;
    }

    [Fact]
    public async Task Compose_returns_typed_contract_with_stats_warnings_and_unresolved_references_over_http()
    {
        var kestrelFactory = _factory.WithWebHostBuilder(builder =>
        {
            builder.UseKestrel();
            builder.UseUrls("http://127.0.0.1:0");
        });

        using var client = kestrelFactory.CreateClient();

        var response = await client.PostAsJsonAsync("/compose", new ComposeRequest
        {
            SubscriptionId = "sub-1",
            ResourceGroupName = "rg-1",
            AzureEnvironment = "AzureCloud",
            Fragments =
            [
                new ComposeFragment
                {
                    BatchIndex = 1,
                    SourceResourceIds =
                    [
                        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/stg1"
                    ],
                    BicepText = "resource stg 'Microsoft.Storage/storageAccounts@2023-01-01' = {}\nvar blobId = resourceId('Microsoft.Storage/storageAccounts', missing.name)",
                    Metadata =
                    {
                        ["ref:missing"] = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/missing"
                    }
                }
            ]
        });

        response.EnsureSuccessStatusCode();
        var payload = await response.Content.ReadFromJsonAsync<ComposeResponse>();

        Assert.NotNull(payload);
        Assert.Equal("ok", payload.Status);
        Assert.Equal("ast", payload.MergeMode);
        Assert.Equal(2, payload.Files.Count);
        Assert.Equal("main.bicep", payload.Files[0].Path);
        Assert.Equal("modules/fragment_001.bicep", payload.Files[1].Path);
        Assert.Equal(1, payload.Stats.FragmentCount);
        Assert.Equal(payload.Stats.UnresolvedReferenceCount, payload.UnresolvedReferences.Count);
        Assert.Single(payload.UnresolvedReferences);
        Assert.Equal("/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/missing", payload.UnresolvedReferences[0].TargetResourceId);
        Assert.Contains("resourceId('Microsoft.Storage/storageAccounts', missing.name)", payload.UnresolvedReferences[0].ReferenceExpression);
    }
}