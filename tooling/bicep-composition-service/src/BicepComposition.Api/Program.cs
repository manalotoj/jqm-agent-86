using BicepComposition.Api.DependencyInjection;
using BicepComposition.Api.Endpoints;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddBicepCompositionServices();

var app = builder.Build();

app.MapHealthEndpoints();
app.MapCompositionEndpoints();

app.Run();

public partial class Program;