namespace BicepComposition.Api.Contracts;

public sealed class ComposeRequest
{
    public string SubscriptionId { get; set; } = string.Empty;

    public string ResourceGroupName { get; set; } = string.Empty;

    public string AzureEnvironment { get; set; } = string.Empty;

    public List<ComposeFragment> Fragments { get; set; } = new();
}