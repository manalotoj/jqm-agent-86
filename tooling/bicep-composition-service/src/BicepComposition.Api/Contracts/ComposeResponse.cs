namespace BicepComposition.Api.Contracts;

public sealed class ComposeResponse
{
    public string Status { get; set; } = "ok";

    public string MergeMode { get; set; } = "ast";

    public List<ComposedFileResponse> Files { get; set; } = new();

    public CompositionStats Stats { get; set; } = new();

    public List<UnresolvedReferenceResponse> UnresolvedReferences { get; set; } = new();

    public List<string> Warnings { get; set; } = new();
}


public sealed class ComposedFileResponse
{
    public string Path { get; set; } = string.Empty;

    public string Content { get; set; } = string.Empty;
}

public sealed class UnresolvedReferenceResponse
{
    public string SourceSymbol { get; set; } = string.Empty;

    public string SourceResourceId { get; set; } = string.Empty;

    public string TargetResourceId { get; set; } = string.Empty;

    public string ReferenceExpression { get; set; } = string.Empty;
}