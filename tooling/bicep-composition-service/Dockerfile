FROM mcr.microsoft.com/dotnet/sdk:10.0-preview AS build

WORKDIR /src

COPY BicepComposition.sln ./
COPY src/BicepComposition.Api/BicepComposition.Api.csproj src/BicepComposition.Api/
COPY src/BicepComposition.Core/BicepComposition.Core.csproj src/BicepComposition.Core/
COPY src/BicepComposition.Tests/BicepComposition.Tests.csproj src/BicepComposition.Tests/

RUN dotnet restore src/BicepComposition.Api/BicepComposition.Api.csproj

COPY . .

RUN dotnet publish src/BicepComposition.Api/BicepComposition.Api.csproj \
    --configuration Release \
    --output /app/publish \
    /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0-preview

WORKDIR /app

ENV ASPNETCORE_URLS=http://+:8080

COPY --from=build /app/publish ./

EXPOSE 8080

ENTRYPOINT ["dotnet", "BicepComposition.Api.dll"]