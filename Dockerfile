# Multi-stage build for the TourneyHub API (hosted-first deployment).
# Build: `docker build -t tourneyhub-api .`
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY global.json Directory.Build.props Directory.Packages.props ./
COPY src/ ./src/
RUN dotnet restore src/TourneyHub.Api/TourneyHub.Api.csproj
RUN dotnet publish src/TourneyHub.Api/TourneyHub.Api.csproj -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build /app ./
ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "TourneyHub.Api.dll"]
