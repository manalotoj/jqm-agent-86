using BicepComposition.Api.Contracts;
using BicepComposition.Core.Composition;
using System.Text.Json;

namespace BicepComposition.Api.Endpoints;

public static class CompositionEndpoints
{
    public static IEndpointRouteBuilder MapCompositionEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/compose", (
            ComposeRequest request,
            BicepComposer composer) =>
        {
            if (string.IsNullOrWhiteSpace(request.SubscriptionId))
            {
                return Results.ValidationProblem(new Dictionary<string, string[]>
                {
                    [nameof(request.SubscriptionId)] = ["SubscriptionId is required."],
                });
            }

            if (string.IsNullOrWhiteSpace(request.ResourceGroupName))
            {
                return Results.ValidationProblem(new Dictionary<string, string[]>
                {
                    [nameof(request.ResourceGroupName)] = ["ResourceGroupName is required."],
                });
            }

            var composeResult = composer.Compose(
                request.Fragments.Select(fragment => new ComposeInputFragment(
                    fragment.BatchIndex,
                    fragment.SourceResourceIds,
                    fragment.BicepText,
                    fragment.Metadata)).ToArray());

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

            return Results.Text(
                JsonSerializer.Serialize(response),
                "application/json");
        });

        return endpoints;
    }
}