using BicepComposition.Api.Contracts;
using BicepComposition.Core.Composition;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;

namespace BicepComposition.Api.Endpoints;

public static class CompositionEndpoints
{
    public static IEndpointRouteBuilder MapCompositionEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/compose", (
            ComposeRequest request,
            BicepComposer composer,
            ILoggerFactory loggerFactory) =>
        {
            var logger = loggerFactory.CreateLogger("BicepComposition.Api.ComposeEndpoint");
            logger.LogInformation(
                "Received composition request for subscription {SubscriptionId}, resource group {ResourceGroupName}, environment {AzureEnvironment}, fragment count {FragmentCount}.",
                request.SubscriptionId,
                request.ResourceGroupName,
                request.AzureEnvironment,
                request.Fragments.Count);

            if (string.IsNullOrWhiteSpace(request.SubscriptionId))
            {
                logger.LogWarning("Composition request rejected because SubscriptionId was missing.");
                return Results.ValidationProblem(new Dictionary<string, string[]>
                {
                    [nameof(request.SubscriptionId)] = ["SubscriptionId is required."],
                });
            }

            if (string.IsNullOrWhiteSpace(request.ResourceGroupName))
            {
                logger.LogWarning("Composition request rejected because ResourceGroupName was missing.");
                return Results.ValidationProblem(new Dictionary<string, string[]>
                {
                    [nameof(request.ResourceGroupName)] = ["ResourceGroupName is required."],
                });
            }

            try
            {
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

                logger.LogInformation(
                    "Composition request succeeded for resource group {ResourceGroupName}. Files={FileCount}, Warnings={WarningCount}, UnresolvedReferences={UnresolvedReferenceCount}.",
                    request.ResourceGroupName,
                    response.Files.Count,
                    response.Warnings.Count,
                    response.UnresolvedReferences.Count);

                return Results.Ok(response);
            }
            catch (Exception ex)
            {
                logger.LogError(
                    ex,
                    "Composition request failed for subscription {SubscriptionId}, resource group {ResourceGroupName}, fragment count {FragmentCount}.",
                    request.SubscriptionId,
                    request.ResourceGroupName,
                    request.Fragments.Count);

                return Results.Problem(
                    title: "Composition failed",
                    detail: ex.Message,
                    statusCode: StatusCodes.Status500InternalServerError);
            }
        });

        return endpoints;
    }
}