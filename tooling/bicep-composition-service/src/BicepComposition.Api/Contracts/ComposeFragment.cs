namespace BicepComposition.Api.Contracts;

public sealed class ComposeFragment
{
    public int BatchIndex { get; set; }

    public List<string> SourceResourceIds { get; set; } = new();

    public string BicepText { get; set; } = string.Empty;

    public Dictionary<string, string> Metadata { get; set; } = new();
}