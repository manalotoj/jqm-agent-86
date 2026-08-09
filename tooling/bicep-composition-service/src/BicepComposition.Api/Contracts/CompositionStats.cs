namespace BicepComposition.Api.Contracts;

public sealed class CompositionStats
{
    public int FragmentCount { get; set; }

    public int DeduplicatedParams { get; set; }

    public int DeduplicatedVars { get; set; }

    public int UnresolvedReferenceCount { get; set; }
}