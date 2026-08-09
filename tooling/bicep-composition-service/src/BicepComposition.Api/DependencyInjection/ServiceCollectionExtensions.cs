using BicepComposition.Core.Composition;

namespace BicepComposition.Api.DependencyInjection;

public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddBicepCompositionServices(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.AddSingleton<BicepComposer>();
        return services;
    }
}