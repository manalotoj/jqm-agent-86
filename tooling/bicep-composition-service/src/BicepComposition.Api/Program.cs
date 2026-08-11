using BicepComposition.Api.DependencyInjection;
using BicepComposition.Api.Endpoints;
using Microsoft.Extensions.Logging.Console;

var builder = WebApplication.CreateBuilder(args);

builder.Logging.ClearProviders();
builder.Logging.AddJsonConsole(options =>
{
    options.IncludeScopes = false;
    options.TimestampFormat = "yyyy-MM-ddTHH:mm:ss.fffZ";
    options.JsonWriterOptions = new System.Text.Json.JsonWriterOptions
    {
        Indented = false,
    };
    options.UseUtcTimestamp = true;
});
builder.Logging.SetMinimumLevel(LogLevel.Information);
builder.Logging.AddFilter("Microsoft.AspNetCore", LogLevel.Warning);
builder.Logging.AddFilter("Microsoft.Hosting.Lifetime", LogLevel.Information);
builder.Logging.AddFilter("BicepComposition", LogLevel.Information);

builder.Services.AddBicepCompositionServices();

var app = builder.Build();

app.Logger.LogInformation(
    "Bicep composition sidecar started and listening for requests.");

app.MapHealthEndpoints();
app.MapCompositionEndpoints();

app.Run();

public partial class Program;