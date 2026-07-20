using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Testcontainers.PostgreSql;
using TourneyHub.Application.Identity;
using TourneyHub.Domain.Common;
using TourneyHub.Domain.Identity;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

public sealed class NotificationIntegrationTests : IAsyncLifetime
{
    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_notif_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;

    public async Task InitializeAsync()
    {
        await _postgres.StartAsync();

        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("ConnectionStrings:Postgres", _postgres.GetConnectionString());
            });

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        await db.Database.MigrateAsync();
    }

    public async Task DisposeAsync()
    {
        if (_factory is not null) await _factory.DisposeAsync();
        await _postgres.DisposeAsync();
    }

    [Fact]
    public async Task Register_user_creates_outbox_message_with_UserRegisteredEvent()
    {
        var client = _factory.CreateClient();

        var response = await client.PostAsJsonAsync("/auth/register", new
        {
            Email = "test@example.com",
            Password = "4fO2zqJ9vR3bX1mK8wT",
            DisplayName = "Test User",
            ConsentPolicyVersion = "v1.0",
        });

        var bodyText = await response.Content.ReadAsStringAsync();
        Assert.True(response.IsSuccessStatusCode, $"Registration failed ({response.StatusCode}): {bodyText}");

        await Task.Delay(300);

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();

        var outboxMessages = await db.Set<OutboxMessage>()
            .Where(m => m.EventType == "TourneyHub.Domain.Identity.Events.UserRegisteredEvent")
            .ToListAsync();

        Assert.NotEmpty(outboxMessages);
        var msg = outboxMessages[0];

        using var doc = JsonDocument.Parse(msg.Payload);
        var root = doc.RootElement;
        Assert.Equal("test@example.com", root.GetProperty("email").GetString());
        Assert.Equal("Test User", root.GetProperty("displayName").GetString());
        Assert.NotNull(root.GetProperty("verificationToken").GetString());
        Assert.True(root.GetProperty("verificationToken").GetString()!.Length > 0);
    }

    [Fact]
    public async Task Password_reset_request_creates_outbox_message_with_PasswordResetEvent()
    {
        var client = _factory.CreateClient();

        var regResponse = await client.PostAsJsonAsync("/auth/register", new
        {
            Email = "reset-test@example.com",
            Password = "7gT3nP5qL2mX8vR1sW",
            DisplayName = "Reset User",
            ConsentPolicyVersion = "v1.0",
        });

        var regBody = await regResponse.Content.ReadAsStringAsync();
        Assert.True(regResponse.IsSuccessStatusCode, $"Registration failed ({regResponse.StatusCode}): {regBody}");

        await Task.Delay(300);

        var resetResponse = await client.PostAsJsonAsync("/auth/password-reset", new
        {
            Email = "reset-test@example.com",
            Token = (string?)null,
            NewPassword = (string?)null,
        });

        resetResponse.EnsureSuccessStatusCode();
        await Task.Delay(300);

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();

        var outboxMessages = await db.Set<OutboxMessage>()
            .Where(m => m.EventType == "TourneyHub.Domain.Identity.Events.PasswordResetRequestedEvent")
            .ToListAsync();

        Assert.NotEmpty(outboxMessages);
        var msg = outboxMessages[0];

        using var doc = JsonDocument.Parse(msg.Payload);
        var root = doc.RootElement;
        Assert.Equal("reset-test@example.com", root.GetProperty("email").GetString());
        Assert.NotNull(root.GetProperty("resetToken").GetString());
        Assert.True(root.GetProperty("resetToken").GetString()!.Length > 0);
    }
}
